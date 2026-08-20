#!/usr/bin/env python3
"""6요소의 `edge`·`label` → 그리퍼 파라미터 전달 경로.

⭐ 왜 이 파일이 필요한가 (8/5)
------------------------------
6요소는 `(x, y, z, edge, angle, label)`인데 소켓으로 로봇에 가는 것은
**포즈 6개 `[x,y,z,rx,ry,rz]`뿐**이다. 즉 `edge`·`label`이 **버려지고 있었다.**

🔴 버리면 안 되는 이유 = **`label`이 그리퍼 벌림을 결정한다.**
   `grasp_database.yaml`에 29종·**벌림 19가지(12~99mm)**가 정의돼 있다.
   7/29 대칭쌍 분석에서 `07/09_guide_paper`가 **width 80 ↔ 60(20mm 차)**였고,
   69mm 부품을 60mm로 벌리면 **물리적으로 안 들어간다**. 라벨을 안 보내면
   기본값 40mm로 집게 되고 → **29종 대부분에서 파지 실패**한다.

🚨 설계를 가둔 제약 = 로봇 클라이언트 코드 (협력사 제공 예시, 원본 확인)
-------------------------------------------------------------------
```js
var poses = JSON.parse(line);
for (i = 0; i < poses.length; i++) {
    receivedPose = poses[i];
    targetPose = createPose(receivedPose[0], ..., receivedPose[5]);  // ← 위치 인덱싱
    moveLinear("tcp", targetPose, 20, 100);
}
```
⭐ 로봇은 `poses[i][0..5]`를 **위치로 읽는다.**
   → **포즈 배열에 7번째 원소를 붙이거나 dict로 바꾸면 로봇 스크립트가 깨진다.**
   (`receivedPose[0]`이 숫자가 아니게 되거나, 길이 가정이 어긋난다.)
   ⚠️ 로봇 스크립트는 **"외부 텍스트 편집 후 로봇 적용 불가"**(협력사 명시)라
   우리가 마음대로 고칠 수 없다 → **포즈 배열의 형태는 건드리지 않는다.**

## 그래서 채택한 방식 = "포즈는 그대로, 계획은 따로"

`edge`·`label`은 **모션 좌표가 아니라 그리퍼 제어 정보**다. 성격이 다르므로
같은 배열에 섞지 않고 **별도 산출물(GraspPlan)** 로 뽑는다.

  전송(소켓)      : `[[x,y,z,rx,ry,rz], ...]`        ← 형태 불변. 로봇이 그대로 읽음
  그리퍼(별도경로): `GraspPlan[i]`(벌림·파지력·라벨)  ← 순서가 포즈와 1:1 대응

⭐ **핵심 = 인덱스 정합.** 포즈 i번과 GraspPlan i번이 같은 부품을 가리킨다.
   그래서 이 모듈은 **포즈와 계획을 같은 함수에서 함께 만든다**(따로 만들면
   한쪽이 거부됐을 때 순서가 어긋나 **엉뚱한 부품 벌림으로 집는다**).

## 그리퍼 값을 로봇에 실제로 전달하는 경로 (2안, 확정은 실기에서)

  🅰️ **Modbus 레지스터**(권장) — 이송 8단계가 이미 Modbus이고 `pymodbus`도 있다.
     좌표는 Modbus 금지지만(협력사 7/31) **그리퍼 벌림은 좌표가 아니다** →
     금지 대상이 아니다. ⚠️단 레지스터 번지는 **협력사 합의 필요**(130~255가
     이송용 배정이라 침범하면 공정이 깨진다).
  🅱️ **포즈 배열을 2배로 보내기** — 부품마다 `[벌림, 0,0,0,0,0]`을 끼워 넣는 편법.
     🔴 로봇이 그걸 `moveLinear`로 실행해버리므로 **위험**. 채택하지 않는다.

⏸️ **현 단계에서는 GraspPlan을 JSON으로 남기는 것까지** 한다. 실제 그리퍼 구동은
   ①그리퍼 모델·제어 방식 확정 ②Modbus 번지 합의 후. **[미확인]** 두 건이라
   지금 코드를 짜면 7/30 레지스터 설계처럼 무효가 될 수 있다.

## edge는 무엇에 쓰나 — 🚨 벌림 검산으로는 쓸 수 없다 (8/5 실측으로 판정)

`edge` = 회전 OBB 4코너(7/30 신설). 처음에 **벌림 검산**에 쓰려 했으나
**실측 801건을 돌려보고 폐기**했다. 기록을 남긴다(같은 실수 반복 방지).

시도: `edge` 짧은 변 → mm 변환 → DB 벌림과 비교 → 어긋나면 경고.
결과: **309건이 "실측 > DB 벌림"** 경고. 그런데 **경고가 틀렸다.**

| 부품 | STL 실측 | DB 벌림 | edge 실측 |
|---|---|---|---|
| `01_sol_block_a` | 11.5 × 45 × 55 | 20mm | **42.9~56.0mm** |
| `18_button_function_niro` | 15.7 × 44 × 110 | 55mm | 69.7mm |

🚨 **원인 = 그리퍼가 무는 변은 카메라에 안 보인다.**
   `01_sol_block_a`의 최소변 **11.5mm(두께)** 는 **시선 방향**이라 top-down
   영상에서 보이지 않는다. 카메라가 보는 건 **45×55 면**이고, `edge` 짧은 변은
   그 중 **45mm**다. DB의 20mm는 11.5mm + 여유로 **원래 맞는 값**이었다.

⭐ **즉 `edge`의 짧은 변 ≠ 그리퍼가 물 폭.** 2D 실루엣으로는 두께를 알 수 없다.
   → **벌림 검산은 `edge`로 불가**(`WIDTH_CHECK_ENABLED=False`로 기본 비활성).

✅ **그래서 `edge`의 실제 용도는 아래 둘로 좁힌다**:
   1. **집을 수 있는지 사전 판정** — 보이는 짧은 변이 **그리퍼 최대 벌림보다
      크면** 애초에 못 문다(이건 시선 방향과 무관하게 유효한 판정).
   2. **파지 여유 확인** — 이웃 부품과의 간격(향후 충돌 회피용, 미구현).

⚠️ 벌림의 진짜 근거는 **DB 값이고, 그 DB는 STL bbox 추정치**다
   (`grasp_database.yaml:22-23` *"로봇 티칭 후 실측 교정 필요"*).
   → **교정은 티칭 때 실물로** 한다. 카메라로 대체할 수 없다.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Optional, Sequence

# ─────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────
_DB_PATH = Path(__file__).resolve().parents[2] / "config" / "grasp_database.yaml"

# 🚨 edge로 벌림을 검산하려던 시도는 8/5 실측으로 폐기(위 docstring 참조).
#    그리퍼가 무는 변이 시선 방향이라 2D 실루엣에 안 나타난다. 기본 비활성.
WIDTH_CHECK_ENABLED = False
WIDTH_MISMATCH_WARN_MM = 10.0     # WIDTH_CHECK_ENABLED=True일 때만 의미

# 그리퍼 물리 한계 — DB `robot.safety`와 어긋나면 예외
GRIPPER_WIDTH_RANGE_MM = (0.0, 110.0)
GRIPPER_FORCE_MAX_N = 40.0        # SLA 레진 보호 (DB robot.safety와 동일)

# ⭐⭐ 안전여유 (2026-08-20 신설) — **DB 값이 아니라 런타임 동작이다**
# ─────────────────────────────────────────────────────────────
# DB `gripper_width_mm`은 8/20 교정으로 **부품의 진짜 무는 변**(`grip_span_flat_mm`,
# 눕힌 자세의 중간변)이 됐다. 여기에 로봇이 **실제로 더 벌리는 양**을 얹는다.
#
# 🚨 왜 DB에 안 박고 여기서 더하는가 = 8/10·8/20에 두 번 밟은 함정:
#    모든 부품 값에 같은 상수를 더하면 `used`와 `need`가 같이 올라가
#    **차이가 그대로**다(동어반복). 여유는 *"예측한 벌림보다 N mm 더 벌린다"*는
#    뜻이므로 **로봇이 벌리는 쪽에만** 적용돼야 의미가 있다.
#
# 📊 실측 근거 (8/18 90장 · 위치매칭 514쌍, `decompose_fatal_grasp_0820.py`):
#      +0mm  치명 80 · 파지 84.4%
#      +5mm  치명 46 · 파지 91.1%
#    ⭐+10mm 치명 23 · 파지 **95.5%**  ← 채택 (8/7에도 최적점으로 판정)
#      +15mm 치명  7 · 파지 98.6% (헐거움 77)
#      +20mm 치명  3 · 파지 99.4% 이나 **헐거움 466건으로 폭증** = 미끄러짐 위험
#
# ✅ 물리 검산 = pickable 20종의 (span_flat + 10mm) 최대값 **79.0mm** ≤ 스트로크 85mm.
#    85mm를 넘는 `17_mks_holder`(92.5)·`top_inner_sheet004`(99.0)는 둘 다
#    `not_pickable`이라 로봇에 좌표가 나가지 않는다.
#
# ⚠️ 실물 티칭 때 재교정 대상 — DB 값이 STL 계산치이므로 여유도 함께 재본다.
GRASP_SAFETY_MARGIN_MM = 10.0

# ⭐ edge의 유효한 용도 ①: 보이는 짧은 변이 최대 벌림보다 크면 애초에 못 문다.
#    (시선 방향과 무관하게 성립하는 판정 — 보이는 변조차 안 들어가는 경우)
GRIPPER_MAX_OPEN_MM = 110.0


class GraspPlanError(ValueError):
    """그리퍼 계획 생성 실패. ⭐ 조용히 기본값으로 넘어가지 않는다."""


@dataclass
class GraspPlan:
    """포즈 1건에 대응하는 그리퍼 계획. 포즈 배열과 **인덱스가 1:1**."""
    index: int                      # 포즈 배열에서의 위치 — 정합의 근거
    label: str                      # 부품 종류 (6요소 label)
    gripper_width_mm: float         # ⭐ 로봇이 실제로 벌릴 값 = base + safety
    gripper_force_N: float
    approach_axis: list[float] = field(default_factory=lambda: [0.0, 0.0, -1.0])
    grasp_depth_mm: float = 15.0
    width_source: str = "db"        # db | db_default
    measured_width_mm: Optional[float] = None   # edge에서 실측한 폭
    # ⭐ 8/20 신설 — 여유가 얼마나·어디에 붙었는지 **값 옆에 남긴다**.
    #   이번 사고의 본질이 *"어떤 기준의 값인지 아무도 몰랐던 것"*이었으므로,
    #   내려보내는 값에 근거를 동봉한다.
    base_width_mm: Optional[float] = None       # DB 원값(= grip_span_flat_mm)
    safety_margin_mm: float = 0.0               # 여기에 더해진 여유
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────
# DB 로드
# ─────────────────────────────────────────────────────────────
_DB_CACHE: Optional[dict] = None


def load_grasp_db(path: Optional[Path] = None, force: bool = False) -> dict:
    """`grasp_database.yaml` 로드.

    🚨 폴백 금지 — 파일이 없거나 깨지면 **예외**를 던진다. 기본 벌림 40mm로
       조용히 넘어가면 29종 대부분에서 파지 실패하는데 에러가 없다.
       ⭐ [[deprecated-design-must-be-marked]] / "조용히 틀리지 말고 크게 실패하라".
    """
    global _DB_CACHE
    if _DB_CACHE is not None and not force:
        return _DB_CACHE
    p = Path(path) if path else _DB_PATH
    if not p.exists():
        raise GraspPlanError(
            f"그래스프 DB가 없다: {p} — 라벨별 벌림을 알 수 없으므로 "
            f"파지를 진행하면 안 된다(기본값으로 넘어가지 않는다)")
    try:
        import yaml
    except ImportError as e:   # pragma: no cover
        raise GraspPlanError(
            "PyYAML이 없다 — 그래스프 DB를 읽을 수 없다. "
            "추론 venv에 설치하거나 시스템 python으로 실행할 것") from e
    db = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(db, dict) or "parts" not in db:
        raise GraspPlanError(f"DB 형식이 예상과 다르다(키: {list(db or {})})")
    _DB_CACHE = db
    return db


# ─────────────────────────────────────────────────────────────
# edge → 실측 폭
# ─────────────────────────────────────────────────────────────
def edge_short_side_px(edge: Sequence[Sequence[float]]) -> Optional[float]:
    """회전 OBB 4코너 → **짧은 변** 길이(픽셀).

    ⭐ 그리퍼는 **짧은 변을 물어야** 한다(긴 변을 물면 벌림이 부족하거나 부품이
       빠진다). 7/30 조사에서 27종 중 22종이 종횡비 1.5 초과였다.
    """
    if not edge or len(edge) != 4:
        return None
    pts = [(float(p[0]), float(p[1])) for p in edge]
    sides = []
    for i in range(4):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % 4]
        sides.append(math.hypot(x2 - x1, y2 - y1))
    if min(sides) <= 0:
        return None
    # 마주보는 변 평균 2개 중 작은 쪽
    a = (sides[0] + sides[2]) / 2.0
    b = (sides[1] + sides[3]) / 2.0
    return min(a, b)


def px_to_mm_at_z(length_px: float, z_mm: float, fx: float) -> float:
    """픽셀 길이 → mm (핀홀, 해당 깊이에서).

    mm = px × z / fx.  ⚠️ z와 fx 단위가 맞아야 한다(z=mm, fx=px).
    """
    if fx <= 0 or z_mm <= 0:
        raise GraspPlanError(f"px→mm 변환 불가 (fx={fx}, z={z_mm})")
    return float(length_px) * float(z_mm) / float(fx)


# ─────────────────────────────────────────────────────────────
# 핵심 — 검출 1건 → GraspPlan
# ─────────────────────────────────────────────────────────────
def plan_for_detection(
    det: dict,
    index: int,
    db: Optional[dict] = None,
    fx: Optional[float] = None,
    allow_db_default: bool = False,
    safety_margin_mm: float = GRASP_SAFETY_MARGIN_MM,
) -> GraspPlan:
    """6요소 검출 1건 → GraspPlan.

    🚨 `allow_db_default=False`(기본)면 **DB에 없는 라벨은 예외**다.
       ⭐ 기본 벌림 40mm로 조용히 집으면 파지 실패의 원인이 안 보인다.

    Args:
        safety_margin_mm: ⭐ DB 원값에 더해 **로봇이 실제로 더 벌리는 양**(기본 10mm).
            8/18 90장 실측에서 파지 가능률 84.4%→**95.5%**를 만드는 값이다.
            🚨 DB에 박지 말 것 — 모든 값에 더하면 동어반복이 된다(위 상수 주석 참조).
            `0.0`을 넘기면 여유 없이 DB 원값 그대로 벌린다(비교·회귀 검사용).
    """
    db = db if db is not None else load_grasp_db()
    label = det.get("label")
    if not label:
        raise GraspPlanError(f"[{index}] label 없음 — 벌림을 결정할 수 없다")

    parts = db.get("parts") or {}
    defaults = db.get("defaults") or {}
    entry = parts.get(label)
    warnings: list[str] = []

    if entry is None:
        if not allow_db_default:
            raise GraspPlanError(
                f"[{index}] label '{label}'이 그래스프 DB에 없다 "
                f"(정의된 {len(parts)}종). 기본 벌림으로 집으면 파지 실패 위험이 "
                f"있어 거부한다 — DB에 추가하거나 allow_db_default=True로 명시할 것")
        entry = {}
        warnings.append(f"DB에 '{label}' 없음 → defaults 사용(파지 실패 위험)")
        width_source = "db_default"
    else:
        width_source = "db"

    width = entry.get("gripper_width_mm", defaults.get("gripper_width_mm"))
    force = entry.get("gripper_force_N", defaults.get("gripper_force_N"))
    if width is None or force is None:
        raise GraspPlanError(
            f"[{index}] '{label}' 벌림/파지력을 DB에서 얻지 못했다")

    base_width = float(width)
    force = float(force)

    # ── ⭐ 안전여유 적용 (2026-08-20) ──
    # DB 값은 **부품의 진짜 무는 변**이고, 로봇은 거기에 여유를 얹어 벌린다.
    # 🚨 여유를 더한 **뒤에** 물리 한계를 본다 — 실제로 벌리는 값이 한계를
    #    넘는지가 중요하지, DB 원값이 넘는지는 중요하지 않다.
    width = round(base_width + safety_margin_mm, 1)

    # ── 물리 한계 검증 (조용히 클램프하지 않는다) ──
    lo, hi = GRIPPER_WIDTH_RANGE_MM
    if not (lo <= width <= hi):
        raise GraspPlanError(
            f"[{index}] '{label}' 벌림 {width}mm(= DB {base_width} + 여유 "
            f"{safety_margin_mm})가 그리퍼 범위 {lo}~{hi}mm 밖")
    if force > GRIPPER_FORCE_MAX_N:
        raise GraspPlanError(
            f"[{index}] '{label}' 파지력 {force}N > 한계 {GRIPPER_FORCE_MAX_N}N "
            f"(SLA 레진 손상)")

    # ── edge로 실측 폭 검산 (경고만, 덮어쓰지 않음) ──
    measured: Optional[float] = None
    short_px = edge_short_side_px(det.get("edge") or [])
    cam = det.get("camera_3d") or {}
    z_mm = None
    if isinstance(cam, dict):
        z_mm = cam.get("Zc")
    if z_mm is None:
        z_mm = det.get("z")
    if short_px and fx and z_mm:
        try:
            measured = round(px_to_mm_at_z(short_px, float(z_mm), float(fx)), 1)
        except GraspPlanError:
            measured = None
    if measured is not None:
        # ⭐ 유효한 판정 ① — 보이는 짧은 변조차 최대 벌림을 넘으면 못 문다.
        #    (두께가 안 보이는 것과 무관하게 성립한다)
        if measured > GRIPPER_MAX_OPEN_MM:
            raise GraspPlanError(
                f"[{index}] '{label}' 보이는 짧은 변이 {measured}mm로 그리퍼 "
                f"최대 벌림 {GRIPPER_MAX_OPEN_MM}mm를 넘는다 — 물 수 없다")
        # 🚨 DB 벌림과의 비교는 기본 비활성 — 8/5 실측에서 309건이 오경보였다.
        #    그리퍼가 무는 변(두께)이 시선 방향이라 edge에 나타나지 않는다.
        if WIDTH_CHECK_ENABLED and abs(width - measured) > WIDTH_MISMATCH_WARN_MM:
            warnings.append(
                f"실측(보이는 짧은변) {measured}mm vs DB 벌림 {width}mm — "
                f"차이 큼. ⚠️단 두께는 시선 방향이라 안 보이므로 "
                f"오경보일 수 있다(8/5 실측에서 309건 오경보)")

    return GraspPlan(
        index=index,
        label=str(label),
        gripper_width_mm=width,
        gripper_force_N=force,
        approach_axis=list(entry.get("approach_axis", [0.0, 0.0, -1.0])),
        grasp_depth_mm=float(entry.get("grasp_depth_mm", 15.0)),
        width_source=width_source,
        measured_width_mm=measured,
        base_width_mm=base_width,
        safety_margin_mm=safety_margin_mm,
        warnings=warnings,
    )


# ─────────────────────────────────────────────────────────────
# 포즈 + 계획을 함께 만든다 (인덱스 정합의 유일한 보장)
# ─────────────────────────────────────────────────────────────
def build_poses_and_plans(
    detections: Sequence[dict],
    *,
    require_reliable_angle: bool = True,
    allow_db_default: bool = False,
    fx: Optional[float] = None,
    skip_rejected: bool = True,
    safety_margin_mm: float = GRASP_SAFETY_MARGIN_MM,
) -> tuple[list[list[float]], list[GraspPlan], list[str]]:
    """검출 목록 → (포즈 배열, 그리퍼 계획, 거부 사유).

    ⭐⭐ **포즈와 계획을 반드시 같은 루프에서 만든다.** 따로 만들면 한쪽이
        거부됐을 때 인덱스가 어긋나 **엉뚱한 부품의 벌림으로 집는다**
        (= 조용히 틀리는 종류. 8/4에 "한 건 거부에 전체 폐기" 버그를 이미 밟았다).

    ⚠️ 포즈 형태는 `[x,y,z,rx,ry,rz]` 6개 그대로다 — 로봇이 위치 인덱싱하므로
       원소를 늘리면 안 된다.
    """
    from .pick_socket_server import six_elements_to_pose, PickEncodeError

    poses: list[list[float]] = []
    plans: list[GraspPlan] = []
    rejected: list[str] = []
    db = load_grasp_db()

    for det in detections:
        label = det.get("label", "?")
        try:
            pose = six_elements_to_pose(
                det, require_reliable_angle=require_reliable_angle)
            plan = plan_for_detection(
                det, index=len(poses), db=db, fx=fx,
                allow_db_default=allow_db_default,
                safety_margin_mm=safety_margin_mm)
        except (PickEncodeError, GraspPlanError) as e:
            rejected.append(f"{label}: {e}")
            if skip_rejected:
                continue
            raise
        # ⭐ 둘 다 성공한 뒤에 append — 한쪽만 들어가는 상태를 만들지 않는다.
        poses.append(pose)
        plans.append(plan)

    if len(poses) != len(plans):   # 방어 (도달 불가여야 정상)
        raise GraspPlanError(
            f"인덱스 정합 깨짐: 포즈 {len(poses)} vs 계획 {len(plans)}")
    return poses, plans, rejected


def dump_plans(plans: Sequence[GraspPlan], path: str | Path) -> Path:
    """GraspPlan 목록을 JSON으로 저장(그리퍼 경로 확정 전 임시 산출물)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "note": ("포즈 배열과 index가 1:1 대응한다. 그리퍼 실제 구동 경로"
                 "(Modbus 번지 등)는 협력사 합의 후 확정 — [미확인]"),
        "count": len(plans),
        "plans": [p_.to_dict() for p_ in plans],
    }
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                 encoding="utf-8")
    return p
