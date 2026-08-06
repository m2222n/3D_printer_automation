#!/usr/bin/env python3
"""grasp_database.yaml에 파지 가능성 태그(`pickability`)를 삽입한다.

⭐ 왜 태그인가 (공정 범위 재정의로 확정된 구조):
  경영진 방침 = **"그리퍼로 못 잡는 제품은 공정에서 제외"**.
  그런데 **학습에서 빼면 안 된다** — 제외해도 카메라엔 보이므로 모델이 다른 부품으로
  오인하고, 그러면 잘못된 벌림으로 집으려다 부품·그리퍼가 손상된다.
  (전례: 7/9 `roll_cover` 병합이 F1 0.684 → 0.669로 오히려 떨어졌다.)
  → **학습은 전 종수 유지, 로봇 동작만 태그로 가른다.** 이 파일이 그 경계다.

태그 3종:
  pickable      : 좌표를 로봇에 전송한다 (정상 파지)
  needs_review  : 인식은 하되 **좌표를 전송하지 않는다** (실물 파지 확인 전)
  not_pickable  : 인식은 하되 전송하지 않고 **사람에게 알린다** (사출 전환 후보)

⚠️ YAML 전체를 재작성하면 주석이 다 날아간다(원본에 설계 근거 주석이 많다).
   → **줄 단위 삽입**으로 주석을 보존한다.

사용법:
  python apply_pickability_tags.py --survey <graspability.json>            # 미리보기
  python apply_pickability_tags.py --survey <graspability.json> --apply    # 실제 수정
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

DB_DEFAULT = "/home/jtm/3D_printer_automation/bin_picking/config/grasp_database.yaml"

TAG_COMMENT = {
    "pickable": "좌표 전송 O",
    "needs_review": "인식만 — 좌표 전송 X (실물 파지 확인 전)",
    "not_pickable": "인식만 — 사람에게 알림 (사출 전환 후보)",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--survey", required=True, help="survey_graspability.py --json 출력")
    ap.add_argument("--db", default=DB_DEFAULT)
    ap.add_argument("--apply", action="store_true", help="실제로 파일을 수정한다")
    args = ap.parse_args()

    survey = json.loads(Path(args.survey).read_text(encoding="utf-8"))
    verdicts = {p["name"]: p for p in survey["parts"]}
    crit = survey["criteria"]

    db_path = Path(args.db)
    lines = db_path.read_text(encoding="utf-8").splitlines()

    # `parts:` 블록 안에서 2칸 들여쓴 `<이름>:` 를 찾는다.
    # ⚠️ 인용부호로 감싼 키가 섞여 있다(`"14_13":` — 숫자로 시작해 YAML이 요구).
    #    따옴표를 허용하지 않으면 조용히 1종을 빠뜨린다(8/6에 실제로 밟았다).
    part_re = re.compile(r"""^  ["']?([A-Za-z0-9_]+)["']?:\s*$""")
    in_parts = False
    out: list[str] = []
    inserted: list[tuple[str, str]] = []
    skipped_existing: list[str] = []
    missing: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.rstrip() == "parts:":
            in_parts = True
            out.append(line)
            i += 1
            continue

        m = part_re.match(line) if in_parts else None
        if not m:
            out.append(line)
            i += 1
            continue

        name = m.group(1)
        out.append(line)
        i += 1

        # 이 부품 블록(4칸 들여쓰기 또는 빈 줄)을 그대로 옮기며 태그 유무를 본다
        block: list[str] = []
        while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
            block.append(lines[i])
            i += 1

        has_tag = any(re.match(r"^    pickability:", b) for b in block)
        v = verdicts.get(name)

        if v is None:
            missing.append(name)
            out.extend(block)
            continue
        if has_tag:
            skipped_existing.append(name)
            out.extend(block)
            continue

        # ⭐ 블록의 마지막 내용 줄 뒤에 삽입한다(뒤따르는 빈 줄은 유지).
        last_content = max(
            (k for k, b in enumerate(block) if b.strip()), default=-1
        )
        tag_lines = [
            f"    pickability: \"{v['verdict']}\"    # {TAG_COMMENT[v['verdict']]}",
            f"    grip_span_flat_mm: {v['span_flat_mm']}   # ⭐ 눕힌 자세에서 그리퍼가 무는 변",
            f"    lying_height_mm: {v['span_thin_mm']}   # 눕혔을 때 높이 (조우 진입 공간)",
        ]
        for why in v["reasons"][:2]:
            tag_lines.append(f"    # 근거: {why}")

        out.extend(block[: last_content + 1])
        out.extend(tag_lines)
        out.extend(block[last_content + 1 :])
        inserted.append((name, v["verdict"]))

    # 헤더에 판정 기준을 남긴다 — 기준선이 [미확인]이므로 나중에 재판정 근거가 된다
    header = [
        "# ============================================================",
        "# 파지 가능성 태그 (pickability) — 2026-08-06 STL 전수 실측",
        "# ------------------------------------------------------------",
        "# 방침 = 그리퍼로 못 잡는 부품은 공정 대상에서 제외한다.",
        "#   ⭐ 단 학습에서는 빼지 않는다 — 빼면 다른 부품으로 오인해 잘못된",
        "#      벌림으로 집으려다 손상된다(7/9 병합이 F1 0.684→0.669 전례).",
        "#   → 학습은 전 종수 유지, 로봇 동작만 이 태그로 가른다.",
        "#",
        "# ✅ 그리퍼 확정 = 주강로보테크 JEGB-4285P-3MA (협력사 회신, 8/6)",
        "#   스트로크 85mm · 개폐 0~85mm(완전히 닫힘) · 파지력 15~150N 프로그래머블",
        "#   RS-485 + 디지털 I/O(입력5/출력3) · 위치·속도·힘 최대 15점 등록 · Self-lock",
        "#",
        f"# 판정 기준선: 벌림 {crit['min_span_mm']}~{crit['max_span_mm']}mm · "
        f"조우 진입 최소 높이 {crit['min_height_mm']}mm",
        "#   ⭐ 0mm까지 닫히므로 '얇아서 못 문다'는 제약이 없다 → 실질 제약은 두 개:",
        "#      ① 무는 변이 스트로크 85mm 안인가  ② 조우가 진입할 높이가 있는가",
        "#   ⚠️ [미확인] = 조우(finger) 실물 두께 → 확인 후 --min-height 로 재판정",
        "#   ✅ min_height 5~6mm 구간에서 제외 종수가 동일하고, 실측 높이 분포에",
        "#      4.8mm와 6.0mm 사이 간극이 있어 5mm 경계는 안정적이다.",
        "#",
        "# 판정 전제: 부품은 빈에 **눕혀 있다**(태민님 확정 8/6).",
        "#   무작위 적재는 안정 자세로 수렴하므로 가장 얇은 면이 바닥에 닿는다.",
        "#   ⇒ 무는 변 = 두 번째로 작은 변 / 조우 진입 높이 = 가장 작은 변.",
        "#   ⇒ '세워서 두께를 문다'는 경로는 이 전제에서 존재하지 않는다.",
        "#",
        "# ⚠️ 아래 `gripper_width_mm`(기존 값)은 방향이 섞여 작성돼 있다",
        "#   (20종은 중간변+여유, 7종은 최소변+여유). 눕힘 전제와 어긋나는 7종은",
        "#   티칭 때 실물로 교정할 것 — `grip_span_flat_mm`가 눕힘 기준 값이다.",
        "# ============================================================",
        "",
    ]

    # ⭐ 반대 방향 검증 = DB에 있는데 태그가 안 달린 부품을 잡는다.
    #   8/6에 `"14_13"`(인용부호 키)을 정규식이 놓쳐 28/29만 처리됐고,
    #   survey 쪽만 보는 검사로는 이것이 안 잡혔다. 태그 없는 부품은 로봇 동작에서
    #   기본값으로 흘러가므로(= 조용히 못 잡을 것을 집으러 감) 반드시 막아야 한다.
    import yaml  # 지연 import — 미리보기에도 검증이 걸리게 한다

    db_all = set((yaml.safe_load(db_path.read_text(encoding="utf-8")) or {}).get("parts", {}))
    handled = {n for n, _ in inserted} | set(skipped_existing)
    untouched = sorted(db_all - handled)

    print("=" * 78)
    print(f"삽입 대상: {len(inserted)}종 / 이미 태그 있음: {len(skipped_existing)}종 / "
          f"survey에 없음: {len(missing)}종")
    print(f"DB 총 {len(db_all)}종 / 처리 {len(handled)}종")
    if missing:
        print(f"⚠️ survey에 없어 태그를 못 단 부품: {missing}")
    if untouched:
        print(f"🚨 DB에 있는데 손대지 못한 부품: {untouched}")
    print("-" * 78)
    for v in ("not_pickable", "needs_review", "pickable"):
        sel = [n for n, vv in inserted if vv == v]
        icon = {"pickable": "🟢", "needs_review": "🟡", "not_pickable": "🔴"}[v]
        print(f"{icon} {v} ({len(sel)}종): {', '.join(sel) if sel else '-'}")
    print("=" * 78)

    if not args.apply:
        print("\n(미리보기 — 실제 수정하려면 --apply)")
        return 0

    # 조용히 일부만 태그하면 "태그 없는 부품"이 기본 동작으로 흘러간다 → 크게 실패시킨다
    if missing:
        print("🔴 survey에 없는 부품이 있어 중단한다. 전체를 실측한 survey를 쓸 것.",
              file=sys.stderr)
        return 1
    if untouched:
        print(f"🔴 DB {len(untouched)}종을 손대지 못했다 → 중단. 파서가 키를 놓치고 있다: "
              f"{untouched}", file=sys.stderr)
        return 1

    backup = db_path.with_suffix(".yaml.bak_0806")
    shutil.copy2(db_path, backup)
    db_path.write_text("\n".join(header + out) + "\n", encoding="utf-8")
    print(f"\n✅ 적용 완료 → {db_path}")
    print(f"   백업: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
