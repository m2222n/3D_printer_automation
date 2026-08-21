#!/usr/bin/env python3
"""입력·출력 게이트 검증 — 실측 데이터로 대조한다(합성 케이스만으로 끝내지 않는다).

⭐ 8/5에 `edge`로 벌림을 검산하려던 설계가 **실측 801건에서 오경보 309건**을 내며 폐기됐다.
   그때 잡아준 것이 "실측 전수 대조"였으므로, 게이트도 같은 방식으로 검증한다.

핵심 질문 3개:
  ① 게이트가 **c1(실운영 조건)의 정상 검출을 버리지 않는가** ← 가장 중요
  ② 게이트가 **c2·c3의 오검출을 실제로 잡는가**
  ③ 유효율 판정이 **학습 분포를 통과시키고 c3를 잡는가**
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from bin_picking.src.pipeline import input_gate as IG  # noqa: E402
from bin_picking.src.pipeline import depth_track_to_6elements as SIX  # noqa: E402

PASS = FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  🔴 {name}" + (f" — {detail}" if detail else ""))


CS_DIR = Path("/data/jtm/blaze_crosssession_0731")
TRAIN_NPY = Path("/data/jtm/synth_out/real_capture100/npy")
PRED_0805 = Path("/data/jtm/synth_out/reports/crosssession_30shot_eval_0805/all_predictions.json")

print("=" * 72)
print("입력·출력 게이트 검증")
print("=" * 72)

# ---------------------------------------------------------------------------
print("\n[1] 임계값이 실측 근거와 맞는가")
# ---------------------------------------------------------------------------
check("부품 최대변 상한 = 230px", IG.MAX_PART_SIDE_PX == 230,
      "진짜 TP 예측 최대 223px + 여유 (⚠️GT 최대 148px로 잡으면 TP를 버린다)")
check("유효율 상한 25% > 학습 실측 최대 23.8%", IG.VALID_RATIO_TRAIN_MAX > 23.8,
      f"상한 {IG.VALID_RATIO_TRAIN_MAX}%")
check("유효율 경고선 10% > 학습 p99 8.8%", IG.VALID_RATIO_WARN > 8.8,
      f"경고선 {IG.VALID_RATIO_WARN}%")

# ---------------------------------------------------------------------------
print("\n[2] 유효율 판정 — 학습 분포는 통과, c3는 차단")
# ---------------------------------------------------------------------------
if TRAIN_NPY.exists():
    verdicts = {}
    for p in sorted(TRAIN_NPY.glob("*.npy")):
        v = IG.check_scene(np.load(p))["verdict"]
        verdicts[v] = verdicts.get(v, 0) + 1
    ood = verdicts.get("out_of_distribution", 0)
    check("학습세션 100장이 out_of_distribution으로 안 잡힘", ood == 0,
          f"판정 분포 {verdicts}")
else:
    print("  ⏭️ 학습세션 npy 없음 — 건너뜀")

if CS_DIR.exists():
    per_cond: dict[str, list[str]] = {}
    ratios: dict[str, list[float]] = {}
    for c in ("c1", "c2", "c3"):
        vs, rs = [], []
        for p in sorted(CS_DIR.glob(f"shot*_{c}.npy")):
            r = IG.check_scene(np.load(p))
            vs.append(r["verdict"])
            rs.append(r["valid_ratio_pct"])
        per_cond[c] = vs
        ratios[c] = rs

    # ⭐ 가장 중요 = c1(실운영 조건)을 막지 않는다
    c1_ood = sum(1 for v in per_cond["c1"] if v == "out_of_distribution")
    check("⭐ c1(실운영·빈 안) 10장이 차단되지 않음", c1_ood == 0,
          f"유효율 {min(ratios['c1']):.1f}~{max(ratios['c1']):.1f}% → {set(per_cond['c1'])}")

    # c3 = 8/5에 TP 0 / FP 96으로 완전 실패한 조건 → 전부 잡아야 한다
    c3_ood = sum(1 for v in per_cond["c3"] if v == "out_of_distribution")
    check("🔴 c3(땅바닥) 10장 전부 out_of_distribution", c3_ood == 10,
          f"유효율 {min(ratios['c3']):.1f}~{max(ratios['c3']):.1f}% → {c3_ood}/10 차단")

    # c2 = 경계 조건 → 최소한 in_distribution은 아니어야 한다
    c2_flagged = sum(1 for v in per_cond["c2"] if v != "in_distribution")
    check("🟠 c2(박스 테두리) 10장이 최소 경고 이상", c2_flagged == 10,
          f"유효율 {min(ratios['c2']):.1f}~{max(ratios['c2']):.1f}% → {c2_flagged}/10 플래그")
else:
    print("  ⏭️ cross-session npy 없음 — 건너뜀")

# ---------------------------------------------------------------------------
print("\n[3] 크기 게이트 — 8/5 예측 실측 대조")
# ---------------------------------------------------------------------------
if PRED_0805.exists():
    preds = json.loads(PRED_0805.read_text())

    def sides(cond: str, key: str = "predictions") -> list[float]:
        out = []
        for k, v in preds.items():
            if not k.endswith(f"_{cond}"):
                continue
            for p in v.get(key, []):
                b = p["bbox_xyxy"]
                out.append(max(b[2] - b[0], b[3] - b[1]))
        return out

    # ⭐⭐⭐ 가장 중요 = **진짜 TP 예측**을 한 건도 버리지 않는가
    #   🚨 8/6에 이 검사를 GT bbox로 했다가 실패했다 — 예측 bbox는 마스크 기반이라 GT보다
    #      크게 나오고(GT 최대 148px / 정답 예측 최대 223px), 게이트가 판정하는 것은 예측이다.
    #      GT만 보고 200px으로 잡아 c1 F1이 0.3882→0.3494로 떨어졌다.
    #      ⭐ 교훈 = **게이트가 실제로 판정하는 값의 분포로 검증할 것.**
    def canon(s: str) -> str:
        return str(s or "").replace(".stl", "").split("__")[0]

    def _iou(a, b):
        ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
        ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
        ua = (a[2] - a[0]) * (a[3] - a[1])
        ub = (b[2] - b[0]) * (b[3] - b[1])
        return inter / max(ua + ub - inter, 1e-9)

    tp_sides, fp_sides = [], []
    for v in preds.values():
        for p in v.get("predictions", []):
            b = p["bbox_xyxy"]
            s = max(b[2] - b[0], b[3] - b[1])
            best, bg = 0.0, None
            for g in v.get("ground_truth", []):
                i = _iou(b, g["bbox_xyxy"])
                if i > best:
                    best, bg = i, g
            gl = canon(bg.get("cad_name") or bg.get("raw_label")) if bg else ""
            if best >= 0.25 and canon(p.get("cad_id")) == gl:
                tp_sides.append(s)
            else:
                fp_sides.append(s)

    lost = [s for s in tp_sides if s > IG.MAX_PART_SIDE_PX]
    check("⭐⭐⭐ 진짜 TP 예측을 한 건도 버리지 않음", len(lost) == 0,
          f"TP 최대 {max(tp_sides):.0f}px ≤ 임계 {IG.MAX_PART_SIDE_PX}px "
          f"(TP {len(tp_sides)}건 중 손실 {len(lost)}건)")

    cut = [s for s in fp_sides if s > IG.MAX_PART_SIDE_PX]
    check("FP를 의미 있게 제거함", len(cut) / max(len(fp_sides), 1) >= 0.30,
          f"FP {len(fp_sides)}건 중 {len(cut)}건 제거 ({len(cut)/max(len(fp_sides),1):.0%})")

    # GT 크기도 참고로 본다(임계보다 작아야 하는 것은 당연하나, 근거 기록용)
    gt_all = []
    for cond in ("c1", "c2", "c3"):
        gt_all += sides(cond, "ground_truth")
    check("GT 부품 크기는 임계 안", max(gt_all) <= IG.MAX_PART_SIDE_PX,
          f"GT 최대 {max(gt_all):.0f}px (⚠️판정 대상은 예측이므로 이것만으로는 부족)")

    # c1 예측 = 실운영 조건이므로 대부분 통과해야 한다
    c1 = sides("c1")
    c1_drop = sum(1 for s in c1 if s > IG.MAX_PART_SIDE_PX)
    check("⭐ c1 예측이 대부분 통과", c1_drop / max(len(c1), 1) < 0.15,
          f"{c1_drop}/{len(c1)}건 제거 ({c1_drop/max(len(c1),1):.0%})")

    # c2·c3 = 오검출이 많은 조건이므로 실제로 잡혀야 한다
    for cond, expect_min in (("c2", 0.25), ("c3", 0.5)):
        a = sides(cond)
        drop = sum(1 for s in a if s > IG.MAX_PART_SIDE_PX)
        check(f"{cond} 오검출이 실제로 제거됨", drop / max(len(a), 1) >= expect_min,
              f"{drop}/{len(a)}건 제거 ({drop/max(len(a),1):.0%}), 최대 {max(a):.0f}px")

    # -----------------------------------------------------------------------
    print("\n[3-b] 🚨 F1 회귀 검사 — 게이트가 실운영 성능을 떨어뜨리지 않는가")
    #   ⭐ 이것이 8/6에 200px 실수를 잡은 검사다. "테스트 통과"와 "성과가 있다"는 다르다.
    # -----------------------------------------------------------------------
    def evaluate(scenes, max_side):
        tp = fp = fn = stp = sfp = sfn = 0
        for v in scenes:
            gts = list(v.get("ground_truth", []))
            prs = [p for p in v.get("predictions", [])
                   if max_side is None or
                   max(p["bbox_xyxy"][2] - p["bbox_xyxy"][0],
                       p["bbox_xyxy"][3] - p["bbox_xyxy"][1]) <= max_side]
            for strict in (True, False):
                used = set()
                t = f = 0
                for p in sorted(prs, key=lambda x: -x.get("score", 0)):
                    best, bi = 0.0, -1
                    for i, g in enumerate(gts):
                        if i in used:
                            continue
                        s = _iou(p["bbox_xyxy"], g["bbox_xyxy"])
                        if s > best:
                            best, bi = s, i
                    ok = bi >= 0 and best >= 0.25
                    if ok and strict:
                        ok = canon(p.get("cad_id")) == canon(
                            gts[bi].get("cad_name") or gts[bi].get("raw_label"))
                    if ok:
                        t += 1
                        used.add(bi)
                    else:
                        f += 1
                if strict:
                    tp += t; fp += f; fn += len(gts) - len(used)
                else:
                    stp += t; sfp += f; sfn += len(gts) - len(used)

        def prf(t, f, n):
            p = t / max(t + f, 1); r = t / max(t + n, 1)
            return p, 2 * p * r / max(p + r, 1e-9)
        _, f1 = prf(tp, fp, fn)
        pp, _ = prf(stp, sfp, sfn)
        return f1, pp

    c1_scenes = [v for k, v in preds.items() if k.endswith("_c1")]
    c2_scenes = [v for k, v in preds.items() if k.endswith("_c2")]
    f1_base, pp_base = evaluate(c1_scenes, None)
    f1_gate, pp_gate = evaluate(c1_scenes, IG.MAX_PART_SIDE_PX)
    check("🚨⭐ c1(실운영) F1이 떨어지지 않음", f1_gate >= f1_base - 1e-9,
          f"{f1_base:.4f} → {f1_gate:.4f} ({f1_gate-f1_base:+.4f})")
    check("c1 위치 precision이 오르거나 유지", pp_gate >= pp_base - 1e-9,
          f"{pp_base:.3f} → {pp_gate:.3f} ({pp_gate-pp_base:+.3f})")

    _, pp2_base = evaluate(c2_scenes, None)
    _, pp2_gate = evaluate(c2_scenes, IG.MAX_PART_SIDE_PX)
    check("⭐ c2 위치 precision이 실제로 개선", pp2_gate > pp2_base + 0.10,
          f"{pp2_base:.3f} → {pp2_gate:.3f} ({pp2_gate-pp2_base:+.3f})")
else:
    print("  ⏭️ 8/5 예측 JSON 없음 — 건너뜀")

# ---------------------------------------------------------------------------
print("\n[4] apply() 동작 — 6요소 실데이터 왕복")
# ---------------------------------------------------------------------------
pred_dir = Path("/data/jtm/synth_out/reports/crosssession_30shot_eval_0805/predictions")
cand = sorted(pred_dir.glob("*c1*.json")) if pred_dir.exists() else []
if cand:
    pj = json.loads(cand[0].read_text())
    npy = CS_DIR / (cand[0].stem.replace("_pred", "") + ".npy")
    if not npy.exists():
        stem = cand[0].stem.split("_pred")[0]
        npy = CS_DIR / f"{stem}.npy"

    if npy.exists():
        depth = np.load(npy)
        six = SIX.convert(pj, depth=depth)
        n_before = len(six["detections"])

        gated = IG.apply(six, depth=depth)
        check("apply()가 원본을 변경하지 않음", len(six["detections"]) == n_before,
              f"원본 {n_before}건 유지")
        check("gate_scene·gate_summary 필드 생성",
              "gate_scene" in gated and "gate_summary" in gated,
              f"장면 판정 {gated['gate_scene']['verdict']}"
              f" (유효율 {gated['gate_scene']['valid_ratio_pct']}%)")
        check("모든 통과 검출에 gate 필드",
              all("gate" in d for d in gated["detections"]),
              f"{len(gated['detections'])}건")
        check("6요소 필수 키 보존",
              all(all(k in d for k in ("x", "y", "z", "edge", "angle", "label"))
                  for d in gated["detections"]),
              "x·y·z·edge·angle·label")
        s = gated["gate_summary"]
        check("합계가 맞음(통과+제거=입력)", s["n_kept"] + s["n_dropped"] == s["n_in"],
              f"{s['n_kept']}+{s['n_dropped']}={s['n_in']}")

        # 🚨 장면 차단 옵션은 명시적으로 켤 때만 동작해야 한다
        strict = IG.apply(six, depth=depth, drop_untrusted_scene=True)
        if gated["gate_scene"]["trusted"]:
            check("신뢰 장면은 strict 모드에서도 유지",
                  len(strict["detections"]) == len(gated["detections"]),
                  "c1은 학습 분포 안이라 차단되지 않음")
    else:
        print(f"  ⏭️ npy 못 찾음: {npy}")
else:
    print("  ⏭️ 예측 JSON 디렉토리 없음 — 건너뜀")

# ---------------------------------------------------------------------------
print("\n[6] 공정 화이트리스트 — 빈에 없는 부품 이름을 버리는가 (2026-08-21 신설)")
# ---------------------------------------------------------------------------
# 🎯 근거 = 모델은 27종을 학습했지만 빈에는 21종만 들어온다(8/14 제외 6종).
#    8/18 90장 GT 630개에 제외 6종이 **0건** → 그 이름으로 나온 예측은 100% 오답.
# 🚨 이 게이트는 **precision 전용**이다(평가기 TP는 라벨 일치가 조건).

# --- 목록의 출처가 DB인가 (폴백이 조용히 쓰이면 목록이 낡아도 모른다) ---
check("제외 목록을 DB에서 읽었다", IG.PROCESS_EXCLUDED_SOURCE.startswith("db("),
      IG.PROCESS_EXCLUDED_SOURCE[:60])

# --- DB와 코드가 갈라지지 않았는가 (8/20 "주석은 옳았는데 코드가 안 따랐다"의 방어) ---
_db_excl, _src = IG.load_excluded_parts()
check("DB의 not_pickable과 모듈 상수가 일치", _db_excl == IG.PROCESS_EXCLUDED_PARTS,
      f"{len(_db_excl)}종")

# 🚨 리터럴로 못박는다 — 상수끼리 비교하면 동어반복이라 목록이 비어도 통과한다(8/20 교훈).
for _name in ("11_sw_block", "17_mks_holder", "main_body",
              "bracket_case", "bracket_sensor2", "top_inner_sheet"):
    check(f"제외 6종에 {_name} 포함", _name in IG.PROCESS_EXCLUDED_PARTS)

# 🟢 공정 대상은 절대 버려지면 안 된다 (여기가 깨지면 부품을 영구히 못 찾는다)
for _name in ("brkt_switch", "15_roller_bracket", "13_variant",
              "09_guide_paper_r", "r_guide_a_r", "01_sol_block_a"):
    check(f"공정 21종 {_name}은 통과", _name not in IG.PROCESS_EXCLUDED_PARTS)

# --- 실제 필터 동작 ---
_dets = [
    {"label": "brkt_switch", "bbox_pixel": {"w": 40, "h": 30}},        # 유지
    {"label": "11_sw_block", "bbox_pixel": {"w": 40, "h": 30}},        # 제외
    {"cad_id": "main_body__b87d6063", "bbox_pixel": {"w": 40, "h": 30}},  # 제외(해시 붙은 형태)
    {"label": "15_roller_bracket", "bbox_pixel": {"w": 40, "h": 30}},  # 유지
]
_kept, _drop = IG.filter_excluded_parts(_dets)
check("제외종만 버린다", len(_kept) == 2 and len(_drop) == 2,
      f"kept={[d['label'] if 'label' in d else d['cad_id'] for d in _kept]}")
check("해시 붙은 cad_id도 잡는다",
      any(d["gate"].get("excluded_part") == "main_body" for d in _drop))
check("버린 이유를 남긴다", all("reason" in d["gate"] for d in _drop))

# ⚠️ 판정 근거가 없으면 버리지 않는다(크기 게이트와 같은 원칙)
_kept2, _drop2 = IG.filter_excluded_parts([{"bbox_pixel": {"w": 40, "h": 30}}])
# ⚠️ 인덱싱을 조건 안에 두지 않는다 — 게이트가 잘못 버리면 IndexError로 죽어서
#    "실패 1건"이 아니라 "테스트 전체 중단"이 된다(뒤 검사가 안 돌아 원인이 가려진다).
check("이름 없는 검출은 통과시킨다", len(_kept2) == 1 and len(_drop2) == 0,
      f"kept={len(_kept2)} dropped={len(_drop2)}")
_kept3, _drop3 = IG.filter_excluded_parts([{"label": "class_7"}])
check("class_N 폴백 라벨은 판정 불가로 통과", len(_kept3) == 1 and len(_drop3) == 0)

# --- apply()에 물려 있는가 + 끌 수 있는가(되돌림 경로) ---
_six = {"detections": [
    {"label": "11_sw_block", "bbox_pixel": {"w": 40, "h": 30}},
    {"label": "brkt_switch", "bbox_pixel": {"w": 40, "h": 30}},
]}
_out = IG.apply(_six)
check("apply()가 기본적으로 화이트리스트를 적용", len(_out["detections"]) == 1,
      f"dropped={_out['gate_summary']['excluded_parts_dropped']}")
check("gate_summary에 출처를 남긴다",
      _out["gate_summary"]["excluded_parts_source"].startswith("db("))
_off = IG.apply(_six, drop_excluded_parts=False)
check("drop_excluded_parts=False로 끌 수 있다(되돌림 경로)",
      len(_off["detections"]) == 2 and _off["gate_summary"]["excluded_parts_enabled"] is False)

# --- ⭐⭐ 실측 대조 = 8/18 90장에서 22건이 잡히는가 (변이 실험의 대상) ---
PRED_0818 = Path("/data/jtm/synth_out/blaze_capture_0818_eval/all_predictions.json")
GT_0818 = Path("/data/jtm/synth_out/blaze_capture_0818/label_png/labelme_json")
if PRED_0818.exists():
    _scenes = json.loads(PRED_0818.read_text())
    _tot = _ex = 0
    for _sc in _scenes.values():
        for _p in _sc.get("predictions", []):
            _tot += 1
            if str(_p.get("cad_id", "")).split("__")[0] in IG.PROCESS_EXCLUDED_PARTS:
                _ex += 1
    # 🚨 기록값을 리터럴로 박는다 — 나중에 "도구가 바뀐 건지 데이터가 바뀐 건지" 가르기 위해
    check("8/18 90장 예측 527건 (8/21 기록값 재현)", _tot == 527, f"{_tot}건")
    check("그중 제외종 22건 (8/21 기록값 재현)", _ex == 22, f"{_ex}건 ({_ex/_tot*100:.1f}%)")
else:
    print("  ⏭️ 8/18 예측 JSON 없음 — 건너뜀")

if GT_0818.exists():
    # 🎯 이 게이트의 전제 = "제외 6종은 빈에 없다". GT로 직접 확인한다.
    #    🚨 여기가 깨지면 게이트를 끄는 것이 맞다(8/14 표의 B 함정).
    _gt_ex = 0
    _gt_tot = 0
    for _f in sorted(GT_0818.glob("*.json")):
        for _sh in json.loads(_f.read_text()).get("shapes", []):
            _gt_tot += 1
            if str(_sh.get("label", "")).split("__")[0] in IG.PROCESS_EXCLUDED_PARTS:
                _gt_ex += 1
    check("GT 630개 재현", _gt_tot == 630, f"{_gt_tot}개")
    check("⭐전제 검증 = GT에 제외 6종이 0건", _gt_ex == 0,
          f"{_gt_ex}건 — 0이 아니면 게이트를 끌 것(8/14 B 함정)")
else:
    print("  ⏭️ 8/18 GT 라벨 없음 — 건너뜀")

# ---------------------------------------------------------------------------
print("\n[5] 경계·이상 입력에 조용히 실패하지 않는가")
# ---------------------------------------------------------------------------
kept, dropped = IG.filter_detections([])
check("빈 목록 처리", kept == [] and dropped == [])

kept, dropped = IG.filter_detections([{"x": 1, "y": 2}])
check("bbox 없는 검출은 버리지 않고 통과", len(kept) == 1 and len(dropped) == 0,
      f"gate={kept[0]['gate'].get('size_checked')}")

big = {"bbox_pixel": {"w": 500, "h": 30}}
kept, dropped = IG.filter_detections([big])
check("한 변만 큰 것도 제거(최대변 기준)", len(dropped) == 1,
      f"{dropped[0]['gate']['max_side_px']}px")

r = IG.check_scene(np.zeros((480, 848), dtype=np.uint16))
check("전부 무효인 장면은 out_of_distribution", r["verdict"] == "out_of_distribution",
      r["note"][:50])

r = IG.check_scene(np.full((480, 848), 3000, dtype=np.uint16))
check("전부 유효인 장면(=c3 극단)도 차단", r["verdict"] == "out_of_distribution",
      f"유효율 {r['valid_ratio_pct']}%")

print("\n" + "=" * 72)
print(f"결과: {PASS} 통과 / {FAIL} 실패")
print("=" * 72)
sys.exit(1 if FAIL else 0)
