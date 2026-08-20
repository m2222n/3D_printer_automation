#!/usr/bin/env python3
"""grasp_plan 검증 — edge·label 전달 경로.

실행:
  PYTHONPATH=/home/jtm/3D_printer_automation /usr/bin/python3 \
    bin_picking/tests/test_grasp_plan.py
  (⚠️ PyYAML 필요. 추론 venv엔 없어 시스템 python 사용)
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from bin_picking.src.communication import grasp_plan as GP
from bin_picking.src.communication.grasp_plan import GraspPlanError

PASS, FAIL = 0, 0


def check(name: str, cond: bool, note: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}" + (f" — {note}" if note else ""))
    else:
        FAIL += 1
        print(f"  🔴 {name}" + (f" — {note}" if note else ""))


def det(label="01_sol_block_a", z=450.0, angle=30.0, reliable=True,
        edge=None, cam=True):
    d = {"label": label, "angle": angle, "angle_reliable": reliable,
         "z": z, "edge": edge or [[0, 0], [40, 0], [40, 100], [0, 100]]}
    if cam:
        d["camera_3d"] = {"Xc": 10.0, "Yc": -20.0, "Zc": z}
    return d


print("=" * 60)
print("grasp_plan 검증 — edge·label 전달 경로")
print("=" * 60)

# ── 1. DB 로드 ──
print("\n=== 1. 그래스프 DB ===")
db = GP.load_grasp_db()
parts = db["parts"]
check("DB 로드", len(parts) > 0, f"{len(parts)}종 정의")
widths = sorted({v.get("gripper_width_mm") for v in parts.values()
                 if v.get("gripper_width_mm")})
check("벌림이 라벨마다 다름", len(widths) > 5,
      f"{len(widths)}가지 {widths[0]}~{widths[-1]}mm → label 필수 근거")

# ── 2. 정상 경로 ──
print("\n=== 2. 정상 계획 생성 ===")
p = GP.plan_for_detection(det(), 0, db=db, fx=309.3)
check("계획 생성", p.label == "01_sol_block_a")
# ⭐ 8/20 계약 변경 — DB 값은 **부품의 진짜 무는 변**이고, 로봇이 벌리는 값은
#   거기에 **안전여유가 얹힌 값**이다. 둘을 따로 검사한다.
_base = parts["01_sol_block_a"]["gripper_width_mm"]
check("DB 원값 보존", p.base_width_mm == _base, f"base {p.base_width_mm}mm")
# 🚨 상수와 비교하면 **동어반복**이다(상수를 7로 바꿔도 통과한다 — 실제로 확인함).
#   8/18 90장 실측이 최적점으로 지목한 **10.0** 이라는 값 자체를 못박는다.
#   ⭐ 바꾸려면 근거(실측)를 새로 대고 이 숫자도 함께 고쳐야 한다.
check("안전여유 = 실측이 정한 10.0mm", GP.GRASP_SAFETY_MARGIN_MM == 10.0,
      f"현재 {GP.GRASP_SAFETY_MARGIN_MM}mm — 파지 95.5%의 근거값")
check("안전여유 적용", p.safety_margin_mm == 10.0, f"+{p.safety_margin_mm}mm")
check("로봇 벌림 = DB + 여유",
      abs(p.gripper_width_mm - (_base + 10.0)) < 1e-6,
      f"{p.gripper_width_mm}mm = {_base} + 10.0 (기본 40이 아님)")
# 🚨 여유 0을 명시하면 DB 원값 그대로여야 한다 — 여유가 **실제로 인자로** 동작하는지
#    (상수를 읽기만 하는 게 아니라) 확인. 이게 없으면 위 검사는 항상 통과한다.
_p0 = GP.plan_for_detection(det(), 0, db=db, fx=309.3, safety_margin_mm=0.0)
check("여유 0이면 DB 원값", _p0.gripper_width_mm == _base,
      f"{_p0.gripper_width_mm}mm — 여유는 인자로 끌 수 있다")
check("width_source=db", p.width_source == "db")
check("실측 폭 계산됨", p.measured_width_mm is not None,
      f"{p.measured_width_mm}mm (edge 짧은변 → mm)")

# ── 3. 조용히 기본값으로 넘어가지 않는다 ──
print("\n=== 3. 미등록 라벨 = 거부 (조용한 기본값 금지) ===")
try:
    GP.plan_for_detection(det(label="없는부품_xyz"), 0, db=db)
    check("미등록 라벨 예외", False, "예외가 나야 하는데 통과함")
except GraspPlanError as e:
    check("미등록 라벨 예외", True, str(e)[:52])
p2 = GP.plan_for_detection(det(label="없는부품_xyz"), 0, db=db,
                           allow_db_default=True)
check("명시하면 허용 + 경고", p2.width_source == "db_default" and p2.warnings,
      p2.warnings[0][:44] if p2.warnings else "")

# ── 4. edge 검산 ──
print("\n=== 4. edge 실측 폭 검산 ===")
short = GP.edge_short_side_px([[0, 0], [40, 0], [40, 100], [0, 100]])
check("짧은 변 선택", abs(short - 40.0) < 1e-6, f"{short}px (긴변 100 아님)")
mm = GP.px_to_mm_at_z(40.0, 450.0, 309.3)
check("px→mm 변환", 55 < mm < 62, f"{mm:.1f}mm @z=450 fx=309.3")
# 🚨 DB 벌림 비교는 폐기됨(8/5) — 두께가 시선 방향이라 오경보 309건.
check("DB 벌림 비교 기본 비활성", GP.WIDTH_CHECK_ENABLED is False,
      "01_sol_block_a: STL 11.5mm 두께가 top-down에 안 보임 → edge 45mm는 다른 변")
p3 = GP.plan_for_detection(
    det(label="01_sol_block_a", edge=[[0, 0], [60, 0], [60, 120], [0, 120]]),
    0, db=db, fx=309.3)
check("정상 크기는 경고 없음", not p3.warnings, f"경고 {len(p3.warnings)}건")
check("DB 값을 덮어쓰지 않음(edge가 아니라 DB+여유가 근거)",
      p3.base_width_mm == parts["01_sol_block_a"]["gripper_width_mm"]
      and p3.gripper_width_mm == p3.base_width_mm + p3.safety_margin_mm,
      "벌림 근거는 DB(티칭 때 실물 교정) + 런타임 여유")
# ⭐ 유효한 판정 = 보이는 변조차 최대 벌림을 넘으면 거부
try:
    GP.plan_for_detection(
        det(label="01_sol_block_a", z=900.0,
            edge=[[0, 0], [500, 0], [500, 900], [0, 900]]),
        0, db=db, fx=309.3)
    check("보이는 변 > 최대 벌림 → 거부", False, "예외가 나야 함")
except GraspPlanError as e:
    check("보이는 변 > 최대 벌림 → 거부", "물 수 없다" in str(e), str(e)[:50])

# ── 5. 인덱스 정합 (핵심) ──
print("\n=== 5. 포즈 ↔ 계획 인덱스 정합 ===")
labels = [k for k in list(parts)[:4]]
dets = [det(label=l) for l in labels]
# 중간에 거부될 건을 섞는다 (angle 신뢰불가)
dets.insert(2, det(label=labels[0], reliable=False))
poses, plans, rej = GP.build_poses_and_plans(dets, fx=309.3)
check("거부 건이 양쪽에서 함께 빠짐", len(poses) == len(plans),
      f"포즈 {len(poses)} = 계획 {len(plans)}, 거부 {len(rej)}")
check("거부 사유 기록", len(rej) == 1 and "angle" in rej[0], rej[0][:48] if rej else "")
ok = all(plans[i].label == poses_label
         for i, poses_label in enumerate([d["label"] for d in dets
                                          if d.get("angle_reliable") is not False]))
check("라벨 순서 일치", ok, "포즈 i번 ↔ 계획 i번이 같은 부품")
check("포즈는 6원소 유지", all(len(p_) == 6 for p_ in poses),
      "로봇이 poses[i][0..5]를 위치로 읽으므로 불변")

# ── 6. 실측 801건 전수 ──
print("\n=== 6. 실측 데이터 전수 (7/29~7/30 산출물) ===")
pred_dir = Path("/data/jtm/synth_out/eval_cpu_0730_angle/predictions")
npy_dir = Path("/data/jtm/synth_out/real_capture100/npy")
if not pred_dir.exists():
    print(f"  ⏭️ 건너뜀 — {pred_dir} 없음")
else:
    import numpy as np
    sys.path.insert(0, str(REPO / "bin_picking" / "src"))
    from bin_picking.src.pipeline import depth_track_to_6elements as SIX
    fx = None
    intr = SIX._load_blaze_intr()
    if intr:
        fx = intr["fx"]
    files = sorted(pred_dir.glob("shot*.json"))
    tot_det = tot_pose = 0
    label_hist: dict[str, int] = {}
    rej_kinds: dict[str, int] = {}
    warn_n = 0
    missing_labels: set[str] = set()
    for f in files:
        pj = json.loads(f.read_text())
        npy = npy_dir / (f.stem + ".npy")
        if not npy.exists():
            continue
        six = SIX.convert(pj, depth=np.load(npy))
        ds = six["detections"]
        tot_det += len(ds)
        for d in ds:
            label_hist[d["label"]] = label_hist.get(d["label"], 0) + 1
            if d["label"] not in parts:
                missing_labels.add(d["label"])
        ps, pl, rj = GP.build_poses_and_plans(
            ds, fx=fx, allow_db_default=True)   # 전수 파악이 목적이라 허용
        tot_pose += len(ps)
        warn_n += sum(1 for x in pl if x.warnings)
        for r in rj:
            k = r.split(":")[-1].strip()[:34]
            rej_kinds[k] = rej_kinds.get(k, 0) + 1
    print(f"  검출 {tot_det}건 → 포즈+계획 {tot_pose}건 / 거부 {tot_det - tot_pose}건")
    check("801건 규모 재현", tot_det >= 790, f"{tot_det}건 (7/29 기록 801)")
    check("라벨 종류", len(label_hist) >= 20, f"{len(label_hist)}종 검출")
    check("⭐ DB 미등록 라벨 없음", not missing_labels,
          "전부 DB에 있음" if not missing_labels
          else f"🔴 {len(missing_labels)}종 누락: {sorted(missing_labels)[:4]}")
    check("⭐ 오경보 없음(폐기된 벌림 비교)", warn_n == 0,
          f"경고 {warn_n}건 — 8/5 이전 설계에선 309건 오경보였음")
    if rej_kinds:
        print("  거부 유형:")
        for k, v in sorted(rej_kinds.items(), key=lambda x: -x[1])[:4]:
            print(f"    {v:4d}건  {k}")
    # 벌림이 실제로 여러 값으로 갈리는지 = label 전달의 실익
    ws = {}
    for f in files[:20]:
        pj = json.loads(f.read_text())
        npy = npy_dir / (f.stem + ".npy")
        if not npy.exists():
            continue
        six = SIX.convert(pj, depth=np.load(npy))
        _, pl, _ = GP.build_poses_and_plans(six["detections"], fx=fx,
                                            allow_db_default=True)
        for x in pl:
            ws[x.gripper_width_mm] = ws.get(x.gripper_width_mm, 0) + 1
    check("⭐ 벌림이 여러 값으로 갈림", len(ws) >= 5,
          f"{len(ws)}가지 {sorted(ws)} → 기본값 40 하나로는 파지 불가")

print("\n" + "=" * 60)
print(f"결과: {PASS} 통과 / {FAIL} 실패")
print("=" * 60)
sys.exit(1 if FAIL else 0)
