"""
3점법 워크 좌표계 — 카메라 좌표 → 로봇 좌표 변환 (고정 거치 / eye-to-hand)
==========================================================================

🎯 목적 = **9/5 판정("로봇이 한 개를 집는다")까지 가는 가장 짧은 경로.**

⭐ 왜 기존 `hand_eye_calibration.py`를 쓰지 않는가 (중요)
---------------------------------------------------------
같은 폴더에 1155줄짜리 `hand_eye_calibration.py`가 이미 있다. **버리지 않는다.**
다만 **이번 목적에는 맞지 않는다**. 세 가지가 다르다.

  1. ⭐ **전제가 eye-in-hand**(카메라를 로봇 팔에 장착)다. 파일 헤더에 그렇게 적혀 있고,
     `transform_to_base()`가 **매 촬영마다 현재 로봇 포즈**(`T_gripper_to_base`)를 요구한다.
     그런데 W34 방침은 *"eye-in-hand 전환 — **고정 거치로 먼저 성공시킨 뒤**"*(WEEK_PLAN:22).
     ⇒ 지금은 카메라가 **안 움직인다**. 로봇 포즈를 매번 읽을 필요가 없다.
  2. ⭐⭐ **체커보드 + `cv2.calibrateHandEye()` (AX=XB) 방식**이라 **로봇 자세 15개 전후를
     티칭해 촬영**해야 한다. 금요일 현장 시간이 그만큼 없다(1~5번 항목을 하루에 뚫어야 한다).
  3. 🚨 **로봇 포즈를 Modbus로 읽는 전제**인데, 우리 검증된 경로는 **소켓(801건)**이다.

⇒ 🎯 **이 파일 = 3점법 전용.** 체커보드 없이 **로봇으로 3점을 찍어** 좌표계를 세운다.
   한화 매뉴얼이 이것을 **표준**이라고 부른다:

     `rodi_script_api_manual_ko.pdf:114` — *"3 개의 측정 점으로부터 좌표계를 정의합니다.
     … **3 점 좌표계 정의는 워크 좌표계 설정의 표준적인 방법**입니다."*
     사용 시나리오에 *"**비전 보정에서 캘리브레이션 좌표 결정**"* 이 명시돼 있다.

📌 **둘은 배타가 아니다.** 고정 거치로 먼저 성공시킨 뒤 eye-in-hand로 갈 때
   `hand_eye_calibration.py`가 그대로 살아난다. 이 파일은 **그 앞 단계**다.

원리 — 왜 3점이면 충분한가
---------------------------
강체 변환(회전+평행이동)은 자유도가 6이다. 3점이면 **평면과 그 위의 방향**이 정해지므로
6자유도가 모두 결정된다. 우리가 하는 일은:

    같은 물리적 3점을  ①카메라로 본 좌표  ②로봇으로 찍은 좌표
    양쪽에서 얻어 → 두 좌표계 사이의 변환 T_cam→base 를 푼다

  P1 = 원점       (빈의 한 모서리)
  P2 = X축 방향   (P1에서 한 변을 따라)
  P3 = 평면 결정  (P1P2 위에 있지 않은 점)

  X = normalize(P2 - P1)
  Z = normalize(X × (P3 - P1))
  Y = Z × X                      ← 오른손 좌표계

🚨 이 방법은 **평면 가정**이다. 빈 안에서 부품이 쌓여 높이가 다르면 z를 따로 줘야 하는데,
   ⭐ **그 z를 우리 depth가 준다.** (= 3점법은 xy 평면을, depth는 높이를 담당)

두 가지 방식을 다 넣었다
-------------------------
  A. `WorkCoordinate.from_three_points()`  — 3점으로 좌표계 하나를 세운다.
     ⭐ 한화 `getCoordinate()`(ko:114)와 **같은 계산**이다. 로봇 쪽에서 할 수도, 여기서 할 수도 있다.
  B. `solve_rigid_transform()`             — **대응점 N쌍**(N≥3)으로 최소제곱 변환을 푼다(Kabsch).
     ⭐⭐ **이쪽이 실제로 더 안전하다.** 점을 4~6개 찍으면 **오차가 평균화**되고,
        무엇보다 **잔차(residual)가 나와서 "티칭이 잘못됐다"를 즉시 안다.**
        A는 점 하나가 1mm 틀려도 **조용히 기울어진 좌표계**를 만든다.

🔴 제1원칙 = "조용히 틀리지 말고 크게 실패하라"
------------------------------------------------
`pick_socket_server.py`가 이미 이 원칙으로 쓰여 있다(z=3136mm 단위 버그를 막는다).
이 파일도 같다 — **의심스러우면 예외를 던지고 로봇에 좌표를 보내지 않는다.**
검증 4종을 넣었다: 퇴화(degenerate) 3점 · 직교성 · 스케일 · 잔차.

단위
-----
🚨 **이 파일은 전부 mm 다.** (`hand_eye_calibration.py`는 m 를 쓴다 — 섞으면 1000배 사고)
   로봇(`createPose`)도 mm, `pick_encoder`의 범위 검증도 mm 이므로 mm 으로 통일한다.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

# ============================================================
# 검증 상수 — 왜 이 값인가를 같이 적는다
# ============================================================

# 3점이 너무 가까우면 방향 추정이 불안정하다.
# 빈이 대략 300~400mm 급이므로 변 하나가 최소 이 정도는 되어야 한다.
MIN_POINT_SPACING_MM = 50.0

# P3가 P1P2 직선에 가까우면 평면이 정해지지 않는다(퇴화).
# sin(각) 이 이 값보다 작으면 거부. 10° ≈ 0.17
MIN_TRIANGLE_SIN = 0.17

# 카메라와 로봇이 같은 물리 거리를 재고 있으므로 두 좌표계의 스케일 비는 1에 가까워야 한다.
# 5% 넘게 벗어나면 단위 실수(m/mm)나 점 대응 어긋남을 의심한다.
SCALE_TOLERANCE = 0.05

# Kabsch 잔차 허용치. 티칭 정밀도 + 카메라 노이즈를 합쳐 이 정도가 상한.
# 🚨 이 값을 넘으면 "점을 잘못 찍었다"로 보고 다시 티칭한다.
MAX_RESIDUAL_MM = 5.0

# 회전행렬이 정말 회전인지(직교·det=+1) 확인하는 수치 허용오차
ORTHONORMAL_TOL = 1e-6


class WorkCoordError(Exception):
    """좌표계 구성/검증 실패. 🚨 이 예외가 나면 로봇에 좌표를 보내면 안 된다."""


# ============================================================
# 기본 도구
# ============================================================

def _as_xyz(p: Sequence[float], name: str) -> np.ndarray:
    """3원소 벡터로 변환 + 유한값 검사."""
    a = np.asarray(p, dtype=np.float64).reshape(-1)
    if a.size != 3:
        raise WorkCoordError(f"{name}: 3원소(x,y,z)여야 하는데 {a.size}개가 왔다")
    if not np.all(np.isfinite(a)):
        raise WorkCoordError(f"{name}: NaN/Inf 가 들어있다 — {a}")
    return a


def _check_rotation(R: np.ndarray, where: str) -> None:
    """R이 진짜 회전행렬인지. 반사(det=-1)면 좌우가 뒤집힌다.

    🚨 8/14에 `r_guide_a_l`↔`r_guide_a_r`로 **좌우가 뒤바뀌는데 무경고**였던 사고가 있었다.
       반사행렬은 정확히 그 사고를 만드는 형태라 반드시 잡는다.
    """
    if R.shape != (3, 3):
        raise WorkCoordError(f"{where}: 회전행렬 shape={R.shape}")
    err = np.max(np.abs(R.T @ R - np.eye(3)))
    if err > 1e-4:
        raise WorkCoordError(f"{where}: 직교성 위반 (오차 {err:.2e}) — 좌표계가 찌그러졌다")
    det = float(np.linalg.det(R))
    if det < 0:
        raise WorkCoordError(
            f"{where}: det(R)={det:.4f} < 0 = **반사행렬**. "
            "좌우가 뒤집힌다 — 점 순서(P1→P2→P3)나 대응이 어긋났을 가능성이 높다"
        )
    if abs(det - 1.0) > 1e-4:
        raise WorkCoordError(f"{where}: det(R)={det:.6f} (1이어야 한다) — 스케일이 섞였다")


def make_transform(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    """R(3,3), t(3,) → 동차변환 T(4,4)."""
    T = np.eye(4, dtype=np.float64)
    T[:3, :3] = R
    T[:3, 3] = np.asarray(t, dtype=np.float64).reshape(3)
    return T


def invert_transform(T: np.ndarray) -> np.ndarray:
    """동차변환의 역. R^T, -R^T t (일반 역행렬보다 안정적이고 빠르다)."""
    R = T[:3, :3]
    t = T[:3, 3]
    Ti = np.eye(4, dtype=np.float64)
    Ti[:3, :3] = R.T
    Ti[:3, 3] = -R.T @ t
    return Ti


def apply_transform(T: np.ndarray, points: np.ndarray) -> np.ndarray:
    """(N,3) 점들에 T를 적용. (3,)도 받는다."""
    pts = np.asarray(points, dtype=np.float64)
    single = pts.ndim == 1
    if single:
        pts = pts.reshape(1, 3)
    if pts.shape[1] != 3:
        raise WorkCoordError(f"points shape={pts.shape} — (N,3)이어야 한다")
    out = (T[:3, :3] @ pts.T).T + T[:3, 3]
    return out[0] if single else out


# ============================================================
# A. 3점법 — 한화 getCoordinate(ko:114)와 같은 계산
# ============================================================

@dataclass
class WorkCoordinate:
    """3점으로 정의된 워크 좌표계.

    `T` = 워크 좌표계 → 기준 좌표계 변환.
    즉 워크 좌표 p 를 기준 좌표로: `apply_transform(wc.T, p)`
    """
    T: np.ndarray
    origin: np.ndarray
    source: str = "three_points"

    @classmethod
    def from_three_points(
        cls,
        p1: Sequence[float],
        p2: Sequence[float],
        p3: Sequence[float],
        source: str = "three_points",
    ) -> "WorkCoordinate":
        """P1=원점 / P2=X축 방향 / P3=평면 결정.

        한화 `getCoordinate(p1, p2, p3)`(ko:114)와 동일한 규약이다.
        ⭐ 그래서 **로봇에서 만든 좌표계와 여기서 만든 것이 일치**해야 하고,
           일치하는지 확인하는 것 자체가 좋은 검산이 된다.
        """
        a = _as_xyz(p1, "p1")
        b = _as_xyz(p2, "p2")
        c = _as_xyz(p3, "p3")

        v12 = b - a
        v13 = c - a
        n12 = float(np.linalg.norm(v12))
        n13 = float(np.linalg.norm(v13))

        # --- 검증 ① 점 간격 ---
        if n12 < MIN_POINT_SPACING_MM or n13 < MIN_POINT_SPACING_MM:
            raise WorkCoordError(
                f"점이 너무 가깝다 (|P1P2|={n12:.1f}mm, |P1P3|={n13:.1f}mm, "
                f"최소 {MIN_POINT_SPACING_MM}mm). 방향 추정이 불안정해진다 — 넓게 잡을 것"
            )

        # --- 검증 ② 퇴화(세 점이 일직선) ---
        cross = np.cross(v12, v13)
        sin_theta = float(np.linalg.norm(cross)) / (n12 * n13)
        if sin_theta < MIN_TRIANGLE_SIN:
            raise WorkCoordError(
                f"세 점이 거의 일직선이다 (sin={sin_theta:.3f} < {MIN_TRIANGLE_SIN}, "
                f"≈{np.degrees(np.arcsin(max(sin_theta, 1e-9))):.1f}°). "
                "P3를 P1P2 선에서 벗어나게 잡을 것"
            )

        x_axis = v12 / n12
        z_axis = cross / np.linalg.norm(cross)
        y_axis = np.cross(z_axis, x_axis)          # 오른손 좌표계

        R = np.column_stack([x_axis, y_axis, z_axis])
        _check_rotation(R, "from_three_points")
        return cls(T=make_transform(R, a), origin=a, source=source)

    def to_base(self, p_work: Sequence[float]) -> np.ndarray:
        """워크 좌표 → 기준(로봇 베이스) 좌표."""
        return apply_transform(self.T, _as_xyz(p_work, "p_work"))

    def to_work(self, p_base: Sequence[float]) -> np.ndarray:
        """기준(로봇 베이스) 좌표 → 워크 좌표."""
        return apply_transform(invert_transform(self.T), _as_xyz(p_base, "p_base"))


# ============================================================
# B. 대응점 N쌍 최소제곱 (Kabsch) — ⭐ 실제 운용 권장
# ============================================================

@dataclass
class RigidTransformResult:
    """카메라→로봇 변환 + **품질 지표**.

    ⭐⭐ `residual_mm`이 이 클래스의 존재 이유다.
       3점법(A)은 점을 잘못 찍어도 **말없이** 기울어진 좌표계를 준다.
       Kabsch는 **잔차로 그것을 드러낸다.**
    """
    T: np.ndarray                    # (4,4) camera → base
    residual_mm: float               # RMS 잔차
    max_error_mm: float              # 최악 점 오차
    per_point_mm: np.ndarray         # 점별 오차
    scale_ratio: float               # 로봇쪽 거리 / 카메라쪽 거리 (1.0 이어야)
    n_points: int

    def report(self) -> str:
        lines = [
            f"대응점 {self.n_points}쌍",
            f"  RMS 잔차   = {self.residual_mm:.2f} mm",
            f"  최대 오차  = {self.max_error_mm:.2f} mm",
            f"  스케일 비  = {self.scale_ratio:.4f}  (1.0 이어야 한다)",
        ]
        for i, e in enumerate(self.per_point_mm):
            mark = "  🔴" if e > MAX_RESIDUAL_MM else "  🟢"
            lines.append(f"{mark} P{i + 1}: {e:.2f} mm")
        return "\n".join(lines)


def solve_rigid_transform(
    points_camera: np.ndarray,
    points_robot: np.ndarray,
    max_residual_mm: float = MAX_RESIDUAL_MM,
    strict: bool = True,
) -> RigidTransformResult:
    """대응점 N쌍(N≥3)에서 카메라→로봇 강체변환을 푼다 (Kabsch/SVD).

    Args:
        points_camera: (N,3) 카메라 좌표계에서 본 점들 [mm]
        points_robot:  (N,3) 같은 점을 로봇으로 찍은 좌표 [mm]
        strict: True면 검증 실패 시 예외. False면 결과만 돌려주고 판단은 호출자에게.
                🚨 **운영 경로에서는 반드시 True.** False는 진단용이다.

    🚨 스케일은 풀지 않는다(강체 = 회전+평행이동만). 카메라와 로봇이 같은 물리 세계를
       재고 있으므로 스케일은 1이어야 하고, **1이 아니면 그것 자체가 버그 신호**다.
       그래서 추정하지 않고 **검사만** 한다.
    """
    A = np.asarray(points_camera, dtype=np.float64)
    B = np.asarray(points_robot, dtype=np.float64)

    if A.ndim != 2 or A.shape[1] != 3:
        raise WorkCoordError(f"points_camera shape={A.shape} — (N,3)이어야 한다")
    if B.shape != A.shape:
        raise WorkCoordError(f"점 개수/모양 불일치: camera{A.shape} vs robot{B.shape}")
    if A.shape[0] < 3:
        raise WorkCoordError(f"대응점이 {A.shape[0]}개 — 최소 3개 필요")
    if not (np.all(np.isfinite(A)) and np.all(np.isfinite(B))):
        raise WorkCoordError("대응점에 NaN/Inf 가 있다")

    n = A.shape[0]

    # --- 스케일 검사: 모든 점쌍 거리 비교 ---
    # 🚨 단위 실수(m vs mm)를 여기서 잡는다. 1000배면 즉시 드러난다.
    dists_a, dists_b = [], []
    for i in range(n):
        for j in range(i + 1, n):
            dists_a.append(np.linalg.norm(A[i] - A[j]))
            dists_b.append(np.linalg.norm(B[i] - B[j]))
    da = np.asarray(dists_a)
    db = np.asarray(dists_b)
    if np.any(da < 1e-6):
        raise WorkCoordError("카메라 점 중 겹치는 것이 있다 (거리 0)")
    scale_ratio = float(np.mean(db / da))

    if strict and abs(scale_ratio - 1.0) > SCALE_TOLERANCE:
        hint = ""
        if 0.5 < scale_ratio < 2.0:
            hint = " — 점 대응이 어긋났을 가능성"
        elif scale_ratio > 100 or scale_ratio < 0.01:
            hint = " — 🚨 단위 실수 의심 (m ↔ mm 는 1000배)"
        raise WorkCoordError(
            f"스케일 비 {scale_ratio:.4f} 가 1.0에서 {SCALE_TOLERANCE:.0%} 넘게 벗어났다{hint}"
        )

    # --- Kabsch ---
    ca = A.mean(axis=0)
    cb = B.mean(axis=0)
    H = (A - ca).T @ (B - cb)
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    # 🚨 반사 보정: 이 한 줄이 없으면 좌우가 뒤집힌 해가 나올 수 있다
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    _check_rotation(R, "solve_rigid_transform")
    t = cb - R @ ca
    T = make_transform(R, t)

    # --- 잔차 ---
    pred = (R @ A.T).T + t
    per_point = np.linalg.norm(pred - B, axis=1)
    rms = float(np.sqrt(np.mean(per_point ** 2)))
    max_err = float(np.max(per_point))

    result = RigidTransformResult(
        T=T,
        residual_mm=rms,
        max_error_mm=max_err,
        per_point_mm=per_point,
        scale_ratio=scale_ratio,
        n_points=n,
    )

    if strict and rms > max_residual_mm:
        raise WorkCoordError(
            f"잔차 RMS {rms:.2f}mm > 허용 {max_residual_mm}mm.\n{result.report()}\n"
            "⇒ 티칭 점이 잘못됐거나 점 대응 순서가 어긋났다. **다시 티칭할 것**"
        )
    return result


# ============================================================
# 저장/불러오기 — 결과는 파일로 남긴다
# ============================================================

DEFAULT_CALIB_PATH = "config/work_coord_0829.json"


def save_calibration(
    result: RigidTransformResult,
    filepath: str = DEFAULT_CALIB_PATH,
    meta: Optional[dict] = None,
) -> str:
    """변환 + 품질지표 + 메타를 JSON으로.

    ⭐ **품질지표를 같이 저장하는 것이 핵심**이다.
       나중에 "이 캘리브 믿을 만한가"를 파일만 보고 판단할 수 있어야 한다.
       (8/21 교훈 = 평가기가 자기 sha256을 결과에 남기게 한 것과 같은 계열)
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "T_cam_to_base": result.T.tolist(),
        "units": "mm",
        "quality": {
            "residual_rms_mm": result.residual_mm,
            "max_error_mm": result.max_error_mm,
            "per_point_mm": result.per_point_mm.tolist(),
            "scale_ratio": result.scale_ratio,
            "n_points": result.n_points,
        },
        "meta": meta or {},
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)


def load_calibration(filepath: str = DEFAULT_CALIB_PATH) -> tuple[np.ndarray, dict]:
    """저장된 변환을 읽는다. 🚨 단위가 mm 인지 확인한다."""
    data = json.loads(Path(filepath).read_text(encoding="utf-8"))
    if data.get("units") != "mm":
        raise WorkCoordError(f"단위가 mm 가 아니다: {data.get('units')!r}")
    T = np.asarray(data["T_cam_to_base"], dtype=np.float64)
    if T.shape != (4, 4):
        raise WorkCoordError(f"T shape={T.shape}")
    _check_rotation(T[:3, :3], f"load_calibration({filepath})")
    return T, data.get("quality", {})


# ============================================================
# 운영 경로 — 인식 결과를 로봇 좌표로
# ============================================================

def camera_point_to_robot(
    T_cam_to_base: np.ndarray,
    xyz_camera_mm: Sequence[float],
    z_range_mm: tuple[float, float] = (200.0, 1500.0),
    xy_limit_mm: float = 1500.0,
) -> np.ndarray:
    """인식이 준 카메라 좌표 1점 → 로봇 베이스 좌표 [mm]. 범위 검증 포함.

    ⭐ 범위 상수는 `pick_encoder.py`의 `Z_PLAUSIBLE_MM`·`XY_PLAUSIBLE_MM`과 **같은 값**이다.
       거기서 한 번 더 검증되지만, **여기서 먼저 막는 편이 원인을 찾기 쉽다.**

    🚨 7/29에 z=3136mm 단위 버그가 실제로 있었다. 로봇 클라이언트에는 검증이 없어서
       그대로 보내면 그 높이로 뻗는다 — 그래서 두 겹으로 막는다.
    """
    p = _as_xyz(xyz_camera_mm, "xyz_camera_mm")
    out = apply_transform(T_cam_to_base, p)
    z = float(out[2])
    if not (z_range_mm[0] <= z <= z_range_mm[1]):
        raise WorkCoordError(
            f"변환 결과 z={z:.1f}mm 가 물리 범위 {z_range_mm} 밖 — "
            "depth 단위 변환이나 캘리브를 의심할 것"
        )
    for name, v in zip("xy", out[:2]):
        if abs(float(v)) > xy_limit_mm:
            raise WorkCoordError(f"변환 결과 {name}={float(v):.1f}mm 가 ±{xy_limit_mm}mm 밖")
    return out


# ============================================================
# 자기검증 — 카메라·로봇 없이 지금 돌려볼 수 있다
# ============================================================

def _self_test() -> None:
    """⭐ 합성 데이터로 왕복 검증. **금요일 전에 코드가 맞는지 확인하는 용도.**

    8/24 교훈 = *"변이 실험으로 판정이 실패할 수 있는지 확인"* 을 여기에도 적용해
    **틀린 입력이 정말 걸리는지**까지 본다(통과만 확인하면 검증이 아니다).
    """
    rng = np.random.default_rng(0)

    # 알려진 변환을 하나 만든다 (30° 회전 + 평행이동)
    th = np.radians(30.0)
    R_true = np.array([[np.cos(th), -np.sin(th), 0],
                       [np.sin(th),  np.cos(th), 0],
                       [0, 0, 1]], dtype=np.float64)
    t_true = np.array([500.0, -200.0, 300.0])
    T_true = make_transform(R_true, t_true)

    cam_pts = np.array([
        [0.0, 0.0, 450.0], [200.0, 0.0, 450.0],
        [0.0, 150.0, 450.0], [200.0, 150.0, 460.0],
        [100.0, 75.0, 455.0],
    ])
    rob_pts = apply_transform(T_true, cam_pts)

    # ① 잡음 없는 완전 데이터 → 잔차 ~0
    r = solve_rigid_transform(cam_pts, rob_pts)
    assert r.residual_mm < 1e-6, f"잔차가 커야 할 이유가 없다: {r.residual_mm}"
    assert np.allclose(r.T, T_true, atol=1e-6), "복원된 변환이 원본과 다르다"
    print(f"① 완전 데이터   RMS={r.residual_mm:.2e}mm  🟢")

    # ② 현실적 잡음(±0.5mm) → 잔차가 작지만 0은 아니다
    noisy = rob_pts + rng.normal(0, 0.5, rob_pts.shape)
    r2 = solve_rigid_transform(cam_pts, noisy)
    assert 0 < r2.residual_mm < 2.0, f"잡음 잔차가 이상하다: {r2.residual_mm}"
    print(f"② 잡음 ±0.5mm   RMS={r2.residual_mm:.3f}mm  🟢")

    # ③ 🚨 변이: 점 하나를 20mm 어긋내면 **반드시 걸려야** 한다
    bad = rob_pts.copy()
    bad[2] += np.array([20.0, 0.0, 0.0])
    try:
        solve_rigid_transform(cam_pts, bad)
        raise AssertionError("🔴 20mm 오차가 통과했다 — 검증이 작동하지 않는다")
    except WorkCoordError:
        print("③ 점 하나 20mm 어긋 → 거부  🟢")

    # ④ 🚨 변이: 단위를 m로 준 경우(1/1000) → 스케일 검사가 잡아야 한다
    try:
        solve_rigid_transform(cam_pts / 1000.0, rob_pts)
        raise AssertionError("🔴 단위 실수가 통과했다")
    except WorkCoordError:
        print("④ 단위 m/mm 혼동 → 거부  🟢")

    # ⑤ 3점법이 Kabsch와 같은 답을 주는가 (같은 3점이면 일치해야 한다)
    wc_cam = WorkCoordinate.from_three_points(cam_pts[0], cam_pts[1], cam_pts[2])
    wc_rob = WorkCoordinate.from_three_points(rob_pts[0], rob_pts[1], rob_pts[2])
    T_3pt = wc_rob.T @ invert_transform(wc_cam.T)
    assert np.allclose(T_3pt, T_true, atol=1e-6), "3점법과 Kabsch 결과가 다르다"
    print("⑤ 3점법 ≡ Kabsch (동일 3점)  🟢")

    # ⑥ 🚨 변이: 퇴화(일직선) 3점 → 거부
    try:
        WorkCoordinate.from_three_points([0, 0, 0], [100, 0, 0], [200, 0, 0])
        raise AssertionError("🔴 일직선 3점이 통과했다")
    except WorkCoordError:
        print("⑥ 일직선 3점 → 거부  🟢")

    # ⑦ 🚨 변이: 너무 가까운 점 → 거부
    try:
        WorkCoordinate.from_three_points([0, 0, 0], [10, 0, 0], [0, 10, 0])
        raise AssertionError("🔴 10mm 간격이 통과했다")
    except WorkCoordError:
        print("⑦ 점 간격 10mm → 거부  🟢")

    # ⑧ 운영 경로: 범위 밖 z 거부 (7/29 z=3136mm 사고 형태)
    try:
        camera_point_to_robot(np.eye(4), [0.0, 0.0, 3136.0])
        raise AssertionError("🔴 z=3136mm 가 통과했다")
    except WorkCoordError:
        print("⑧ z=3136mm(7/29 사고 형태) → 거부  🟢")

    print("\n✅ 8/8 통과 — 통과 3건 + **거부되어야 할 5건이 실제로 거부됨**")


if __name__ == "__main__":
    _self_test()
