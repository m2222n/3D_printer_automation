#!/usr/bin/env python3
"""
topology.yaml -> PostgreSQL 동기화 CLI

  python topo_sync.py --check   검증만
  python topo_sync.py --plan    변경 계획 출력
  python topo_sync.py --apply   실제 반영

원칙
  - 멱등: 같은 파일로 여러 번 돌려도 결과가 같다
  - 비파괴: YAML에서 사라진 노드는 DELETE 하지 않고 is_active=false
  - 게이트 우선: 검증을 모두 통과해야 커밋한다
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from collections import defaultdict, deque

import psycopg
from psycopg.types.json import Json
import yaml

# 비번은 DSN 에 두지 않는다(git 에 올라간다). LINE_DSN 환경변수가 있으면 그것, 없으면 사용자만 적고
# 비번은 libpq 관례대로 PGPASSWORD 또는 ~/.pgpass 에서 (tools/dev_reset.sh 가 PGPASSWORD 를 export 한다).
DSN = os.environ.get("LINE_DSN", "postgresql://mes@localhost:5432/factory")
# 프린터 시리얼의 유일한 출처. topology.yaml 엔 번호(legacy_target_printer)만 있고 시리얼은 여기서 주입한다.
ENV_FILE = str(Path(__file__).resolve().parents[1] / "web-api" / ".env")


def load_serial_map(env_path):
    """PRINTER_SERIAL_MAP — 환경변수 우선, 없으면 .env 의 그 줄 하나만 읽는다(dotenv 의존 없이)."""
    raw = os.environ.get("PRINTER_SERIAL_MAP")
    if not raw and os.path.exists(env_path):
        for line in open(env_path, encoding="utf-8"):
            if line.startswith("PRINTER_SERIAL_MAP="):
                raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not raw:
        return {}
    return {int(k): v for k, v in json.loads(raw).items()}


def inject_serials(nodes, serial_map):
    """external_ref.legacy_target_printer → printer_serial. 반환 = 채운 노드 수."""
    filled = 0
    for n in nodes:
        ref = n["external_ref"].obj if n["external_ref"] is not None else None
        if not ref or "legacy_target_printer" not in ref:
            continue
        serial = serial_map.get(int(ref["legacy_target_printer"]))
        if serial:
            ref["printer_serial"] = serial
            filled += 1
    return filled


def as_list(v):
    return v if isinstance(v, list) else [v]


def load(path):
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    doc = yaml.safe_load(raw)
    doc["_hash"] = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return doc


def resolve(ref, doc):
    """"@GROUP" 을 멤버 목록으로 펼친다. 일반 ID 는 그대로."""
    out = []
    for x in as_list(ref):
        if isinstance(x, str) and x.startswith("@"):
            name = x[1:]
            if name not in doc.get("groups", {}):
                raise KeyError(f"정의되지 않은 그룹: @{name}")
            out.extend(doc["groups"][name])
        else:
            out.append(x)
    return out


def merge_attrs(type_attrs, node_attrs):
    """
    타입 기본값 위에 노드 값을 얹는다. **최상위 키 단위 교체**(1단 얕은 병합)다.

    왜 얕은가 — 기존 expand_nodes 가 키 단위 교체(`n.get(k, t.get(k))`)이고,
    attrs 만 재귀 병합하면 규칙이 두 가지가 된다.
    재귀로 하면 measure 같은 중첩 값의 일부만 덮을 수 있는데,
    그러면 최종값이 두 곳에 흩어져 "지금 유효한 값이 무엇인가"를 읽기 어려워진다.

      타입 {measure:{key:h}, x:1} + 노드 {measure:{key:w}}
        -> {measure:{key:w}, x:1}      measure 는 통째 교체, x 는 남는다

    통째 교체(노드 attrs 가 타입 attrs 를 전부 대체)로 하지 않은 이유는
    타입 기본값을 쓰면서 키 하나만 더하는 것이 흔한 경우이기 때문이다.
    """
    if not type_attrs and not node_attrs:
        return None
    merged = dict(type_attrs or {})
    merged.update(node_attrs or {})
    return merged or None


def expand_nodes(doc):
    """
    타입 기본값을 노드에 채워 넣고 칸(slots)을 펼친다.
    node_type 테이블은 없다 — 기본값은 여기서 병합되어 node 컬럼으로 들어간다.
    """
    types = doc["node_types"]
    nodes, slots = [], []
    for n in doc["nodes"]:
        t = types[n["type"]]
        slot_caps = n.get("slots")
        if isinstance(slot_caps, int):
            slot_caps = [n["slot_capacity"]] * slot_caps
        if slot_caps:
            capacity = sum(slot_caps)
            for i, c in enumerate(slot_caps, 1):
                slots.append((n["id"], i, c))
        else:
            capacity = n.get("capacity", t.get("default_capacity", 1))
        nodes.append({
            "node_id": n["id"],
            "node_kind": t["kind"],
            "node_type": n["type"],
            "label": n["label"],
            "capacity": capacity,
            "std_cycle_s": n.get("std_cycle_s", t.get("default_cycle_s")),
            "id_prefix": n.get("id_prefix", t.get("id_prefix")),
            "post_delay_s": n.get("post_delay_s", t.get("post_delay_s", 0)),
            "slot_access": n.get("slot_access", t.get("slot_access", "FIFO")),
            "slot_fill": n.get("slot_fill", t.get("slot_fill", "SEQUENTIAL")),
            "count_by_group": n.get("count_by_group", t.get("count_by_group", False)),
            "splits_batch": n.get("splits_batch", t.get("splits_batch", False)),
            "ui_kind": n.get("ui_kind", t.get("ui_kind", "MONITOR")),
            "group_label": n.get("group_label", t.get("group_label")),
            "attrs": (lambda a: Json(a) if a else None)(merge_attrs(t.get("attrs"), n.get("attrs"))),
            # 식별자는 노드마다 고유하므로 타입 기본값이 있을 이유가 없다 — 병합하지 않는다.
            "external_ref": Json(n.get("external_ref")) if n.get("external_ref") else None,
            "transporter_id": None,          # 아래 assign_transporters 가 채운다
        })
    return nodes, slots


def expand_routes(doc):
    """from/to 배열을 엣지로. (line_id, from, to, priority, edge_kind)"""
    edges = []
    for line_id, specs in doc["routes"].items():
        for spec in specs:
            kind = spec.get("kind", "MAIN")
            for f in resolve(spec["from"], doc):
                for t in resolve(spec["to"], doc):
                    edges.append((line_id, f, t, spec.get("priority", 0), kind))
    return edges


def assign_transporters(doc, nodes):
    """
    transporters[].nodes 에 적힌 노드에 담당을 붙인다.
    노드별 담당이다 — 엣지별로 달라지는 경우는 폐기뿐이고 폐기는 담당을 두지 않는다.
    """
    by_id = {n["node_id"]: n for n in nodes}
    conflicts, unknown = [], []
    for tr in doc["transporters"]:
        for node_id in resolve(tr.get("nodes", []), doc):
            if node_id not in by_id:
                unknown.append((tr["id"], node_id))
                continue
            prev = by_id[node_id]["transporter_id"]
            if prev and prev != tr["id"]:
                conflicts.append((node_id, prev, tr["id"]))
            by_id[node_id]["transporter_id"] = tr["id"]
    return conflicts, unknown


def validate(doc, nodes, slots, edges, tr_conflicts, tr_unknown, cur):
    errs = []
    node_ids = {n["node_id"] for n in nodes}

    # 프린터 노드에 시리얼이 안 채워졌으면 막는다 — 적재해 두면 Spawn 이 조용히 LINE_UNTRACKED 로 빠진다.
    for n in nodes:
        ref = n["external_ref"].obj if n["external_ref"] is not None else None
        if ref and "legacy_target_printer" in ref and not ref.get("printer_serial"):
            errs.append(f"[시리얼] {n['node_id']} 번호 {ref['legacy_target_printer']} 의 시리얼이 없음 — "
                        f"web-api/.env PRINTER_SERIAL_MAP 확인 (--env 로 경로 지정)")
    line_ids = {l["id"] for l in doc["lines"]}
    kind_of = {n["node_id"]: n["node_kind"] for n in nodes}

    # 참조 무결성
    for line_id, f, t, _, _ in edges:
        for x in (f, t):
            if x not in node_ids:
                errs.append(f"[참조] route 가 없는 노드를 가리킴: {x}")
        if line_id not in line_ids:
            errs.append(f"[참조] 정의되지 않은 라인: {line_id}")
    for tr_id, node_id in tr_unknown:
        errs.append(f"[참조] {tr_id} 가 없는 노드를 담당: {node_id}")

    # 순환 — 라인별 · MAIN 만
    for line_id in {e[0] for e in edges}:
        adj, indeg, members = defaultdict(list), defaultdict(int), set()
        for l, f, t, _, k in edges:
            if l == line_id and k == "MAIN":
                adj[f].append(t); indeg[t] += 1; members |= {f, t}
        q = deque(n for n in members if indeg[n] == 0)
        seen = 0
        while q:
            cur_n = q.popleft(); seen += 1
            for nxt in adj[cur_n]:
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    q.append(nxt)
        if seen < len(members):
            stuck = sorted(n for n in members if indeg[n] > 0)
            errs.append(f"[순환] {line_id} MAIN 경로에 순환: {', '.join(stuck)} "
                        f"— 되주차/재작업이면 kind: DETOUR 로")

    # 고립 — 전역
    used = {x for _, f, t, _, _ in edges for x in (f, t)}
    for n in sorted(node_ids - used):
        errs.append(f"[고립] 어떤 route 에도 없는 노드: {n}")

    # 재고 있는 노드 제거
    cur.execute("""SELECT ps.node_id, count(*) FROM product_state ps
                     JOIN node n USING (node_id) WHERE n.is_active GROUP BY ps.node_id""")
    for node_id, qty in cur.fetchall():
        if node_id not in node_ids:
            errs.append(f"[재고] {node_id} 에 {qty}개가 남아 있습니다. draining: true 로 먼저 소진하세요")

    # 칸 재고 — 칸을 줄이면 그 칸에 있던 개체가 조용히 사라진다.
    # apply 가 node_slot 을 지우고 다시 넣는데 product_state.slot_no 에는 FK 가 없어서
    # 에러 없이 통과하고, 사라진 칸의 개체는 v_rack_slot/v_slot_map 에서만 안 보이게 된다.
    keep_slots = {(s[0], s[1]) for s in slots}
    cur.execute("SELECT node_id, slot_no, count(*) FROM product_state "
                "WHERE slot_no IS NOT NULL GROUP BY node_id, slot_no")
    for node_id, slot_no, qty in cur.fetchall():
        # 노드째 사라진 경우는 위 [재고] 가 이미 잡는다
        if node_id in node_ids and (node_id, slot_no) not in keep_slots:
            errs.append(f"[재고] {node_id} 의 {slot_no}번 칸에 {qty}개가 남아 있습니다. "
                        f"비우고 나서 칸을 줄이세요")

    # 담당 — MAIN/DETOUR 엣지가 나가는 노드는 담당이 있어야 한다. EXIT 는 제외.
    needs = {f for _, f, _, _, k in edges if k != "EXIT"}
    for n in nodes:
        if n["node_id"] in needs and not n["transporter_id"]:
            errs.append(f"[담당] 반송 담당이 없는 노드: {n['node_id']}")
    for node_id, a, b in tr_conflicts:
        errs.append(f"[중복] {node_id} 를 {a}, {b} 가 함께 담당")

    # 칸 정합
    slotted = {s[0] for s in slots}
    for n in nodes:
        if n["node_kind"] == "RACK" and n["node_id"] not in slotted:
            errs.append(f"[칸] 랙에 slots 가 없습니다: {n['node_id']}")
        if n["node_kind"] == "STATION" and n["node_id"] in slotted:
            errs.append(f"[칸] 설비에는 칸을 둘 수 없습니다: {n['node_id']}")
        if n["slot_access"] not in ("FIFO", "LIFO", "RANDOM"):
            errs.append(f"[칸] slot_access 오류: {n['node_id']} -> {n['slot_access']}")
        if n["slot_fill"] not in ("SEQUENTIAL", "BALANCED"):
            errs.append(f"[칸] slot_fill 오류: {n['node_id']} -> {n['slot_fill']}")
        if n["ui_kind"] not in ("BATCH_SPLIT", "PART_JUDGE", "MONITOR", "TRANSPORT"):
            errs.append(f"[화면] ui_kind 오류: {n['node_id']} -> {n['ui_kind']}")
        if n["splits_batch"] and n["ui_kind"] != "BATCH_SPLIT":
            errs.append(f"[화면] 분해 노드는 ui_kind=BATCH_SPLIT 이어야 합니다: {n['node_id']}")
    return errs


def apply(doc, nodes, slots, edges, cur):
    summary = defaultdict(int)

    for line in doc["lines"]:
        cur.execute("""
            INSERT INTO line (line_id, label, process_family, plate_count, is_active)
            VALUES (%s,%s,%s,%s,%s)
            ON CONFLICT (line_id) DO UPDATE SET label=EXCLUDED.label,
              process_family=EXCLUDED.process_family, plate_count=EXCLUDED.plate_count,
              is_active=EXCLUDED.is_active
        """, (line["id"], line["label"], line["process_family"],
              line.get("plate_count", 999), line.get("active", True)))

    for tr in doc["transporters"]:
        cur.execute("""
            INSERT INTO transporter (transporter_id, kind, label, auto_dispatch, attrs, is_active)
            VALUES (%s,%s,%s,%s,%s,true)
            ON CONFLICT (transporter_id) DO UPDATE SET kind=EXCLUDED.kind,
              label=EXCLUDED.label, auto_dispatch=EXCLUDED.auto_dispatch,
              attrs=EXCLUDED.attrs, is_active=true
        """, (tr["id"], tr["kind"], tr["label"], "endpoint" in tr,
              # commands 가 없으면 NULL. Json(None) 은 jsonb 'null' 이 되어 IS NOT NULL 에 걸린다.
              # endpoint(protocol · ref)도 attrs 에 함께 — R11 이 protocol 을 낸다. 컬럼을 늘리지 않는다
              Json({**(tr.get("attrs") or {}), **({"endpoint": tr["endpoint"]} if tr.get("endpoint") else {})})
              if (tr.get("attrs") or tr.get("endpoint")) else None))
        cur.execute("INSERT INTO transporter_state (transporter_id, status) VALUES (%s,'OFFLINE') "
                    "ON CONFLICT DO NOTHING", (tr["id"],))
    cur.execute("UPDATE transporter SET is_active=false WHERE transporter_id <> ALL(%s)",
                ([t["id"] for t in doc["transporters"]],))

    for n in nodes:
        cur.execute("""
            INSERT INTO node (node_id, node_kind, node_type, label, capacity, std_cycle_s,
                              id_prefix, post_delay_s, slot_access, slot_fill,
                              count_by_group, splits_batch, ui_kind, group_label,
                              attrs, external_ref, transporter_id, is_active)
            VALUES (%(node_id)s,%(node_kind)s,%(node_type)s,%(label)s,%(capacity)s,
                    %(std_cycle_s)s,%(id_prefix)s,%(post_delay_s)s,%(slot_access)s,
                    %(slot_fill)s,%(count_by_group)s,%(splits_batch)s,%(ui_kind)s,
                    %(group_label)s,%(attrs)s,%(external_ref)s,%(transporter_id)s,true)
            ON CONFLICT (node_id) DO UPDATE SET node_kind=EXCLUDED.node_kind,
              node_type=EXCLUDED.node_type, label=EXCLUDED.label, capacity=EXCLUDED.capacity,
              std_cycle_s=EXCLUDED.std_cycle_s, id_prefix=EXCLUDED.id_prefix,
              post_delay_s=EXCLUDED.post_delay_s, slot_access=EXCLUDED.slot_access,
              slot_fill=EXCLUDED.slot_fill, count_by_group=EXCLUDED.count_by_group,
              splits_batch=EXCLUDED.splits_batch, ui_kind=EXCLUDED.ui_kind,
              group_label=EXCLUDED.group_label,
              attrs=EXCLUDED.attrs, external_ref=EXCLUDED.external_ref,
              transporter_id=EXCLUDED.transporter_id, is_active=true
        """, n)
        summary["nodes"] += 1
        if n["id_prefix"]:
            cur.execute("INSERT INTO id_counter (prefix) VALUES (%s) ON CONFLICT DO NOTHING",
                        (n["id_prefix"],))
    cur.execute("UPDATE node SET is_active=false WHERE node_id <> ALL(%s)",
                ([n["node_id"] for n in nodes],))
    summary["deactivated"] = cur.rowcount

    cur.execute("DELETE FROM node_slot WHERE node_id = ANY(%s)", ([n["node_id"] for n in nodes],))
    for node_id, slot_no, cap in slots:
        cur.execute("INSERT INTO node_slot VALUES (%s,%s,%s)", (node_id, slot_no, cap))
    summary["slots"] = len(slots)

    cur.execute("DELETE FROM route")
    for line_id, f, t, prio, kind in edges:
        cur.execute("INSERT INTO route VALUES (%s,%s,%s,%s,%s)", (line_id, f, t, prio, kind))
    summary["routes"] = len(edges)
    return dict(summary)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(Path(__file__).resolve().parent / "topology.yaml"))
    ap.add_argument("--dsn", default=DSN)
    ap.add_argument("--env", default=ENV_FILE, help="PRINTER_SERIAL_MAP 을 읽을 .env (기본 web-api/.env)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--plan", action="store_true")
    g.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    doc = load(a.file)
    nodes, slots = expand_nodes(doc)
    n_serial = inject_serials(nodes, load_serial_map(a.env))
    print(f"시리얼 주입: 프린터 노드 {n_serial}개 ({a.env})")
    edges = expand_routes(doc)
    conflicts, unknown = assign_transporters(doc, nodes)

    with psycopg.connect(a.dsn) as conn, conn.cursor() as cur:
        errs = validate(doc, nodes, slots, edges, conflicts, unknown, cur)
        if errs:
            print(f"검증 실패 — {len(errs)}건\n" + "\n".join("  " + e for e in errs))
            sys.exit(1)
        from collections import Counter
        kc = Counter(e[4] for e in edges)
        print(f"검증 통과: 노드 {len(nodes)}, 라인 {len(doc['lines'])}, 칸 {len(slots)}, "
              f"엣지 {len(edges)}({' / '.join(f'{k} {v}' for k,v in sorted(kc.items()))}), "
              f"반송자원 {len(doc['transporters'])}")
        if a.check:
            return
        if a.plan:
            for n in nodes:
                print(f"  {n['node_id']:<16} {n['node_kind']:<8} 담당={n['transporter_id'] or '-'}")
            conn.rollback(); return
        summary = apply(doc, nodes, slots, edges, cur)
        conn.commit()
        print(f"반영 완료 ({doc['_hash']}): {summary}")


if __name__ == "__main__":
    main()
