"""
카메라 좌표 → 로봇 base 좌표 변환 계층 (hand-eye 결과를 소켓 서버에 물린다)
=====================================================================

🎯 왜 있는가 (9/16 코드 확인 → 9/17 신설)
------------------------------------------
9/16 저녁 코드 전수 확인 결과 **이 계층이 없었다.**
  - `pick_socket_server.six_elements_to_pose()` 는 `camera_3d`(Blaze 카메라 좌표 mm)를 **그대로** 포즈로 만들고
  - `depth_track_to_6elements.py` 는 notes 에 스스로 *"로봇 Base 변환(hand-eye)은 미착수"* 라 적어 두었고
  - `work_coord_3point.py`(8/8 자체검증 통과)를 **부르는 코드가 0건**이었다.
⇒ 9/1 소켓 왕복 *"서버가 보낸 것 == 로봇이 읽은 것"* 은 **카메라 좌표가 그대로 왕복한 것**이다.
   그 값을 로봇에 보내면 로봇은 카메라 좌표를 base 좌표로 읽고 **엉뚱한 곳으로 간다.**
⇒ 📌 ***"짜여 있다"≠"호출된다"*** 의 네 번째 사례(각도 주입 9/1 · 게이트 8/6 · depth_units 8/5).

이 파일이 하는 일 = 정확히 세 가지
-----------------------------------
  ① **캘리브 파일**을 만든다·읽는다·검증한다  (`build_calibration` / `save_calibration` / `load_calibration`)
  ② 6요소 검출 1건 → **base 좌표 파지 포즈** [x,y,z,rx,ry,rz]  (`det_to_base_pose`)
  ③ 캘리브 파일이 **없으면 거부**한다 — 카메라 좌표를 조용히 보내는 길을 막는다

좌표계·단위 (섞이면 1000배 사고 — 전부 mm · deg)
------------------------------------------------
  camera : Blaze 광학 좌표. x = 화면 오른쪽 · y = 화면 아래 · z = 광축 앞(부품 방향). `pixel_to_camera_3d` 규약.
  base   : 로봇 베이스. 펜던트가 보여주는 TCP 좌표와 같은 프레임. **z 위**(P_capture Z=+413 · 툴이 아래를 봄).
  T_cam_to_base (4×4) : p_base = T @ [p_cam, 1]

🚨 유효 조건 = **촬영 자세가 하나로 고정**(P_capture · `capture_test`) — 카메라가 팔에 달려 있어도 항상 같은 자세에서
   찍으면 카메라는 사실상 고정이고 T 는 상수다(HAND_EYE_CARD §8 "더 짧은 길" · 9/10).
   ⇒ P_capture 를 다시 티칭하면(9/22 브라켓 v2 장착 후) **이 파일도 다시 만든다**. 파일에 P_capture 를 함께 적어 대조한다.

🔴 제1원칙 = "조용히 틀리지 말고 크게 실패하라" — 거부하는 경우 (전부 테스트에 있다)
--------------------------------------------------------------------------
  - 캘리브 파일이 없다 / 스키마·단위(mm)가 다르다 / 4×4 가 SE(3) 가 아니다(반사·스케일)
  - 잔차 RMS > MAX_RESIDUAL_MM · 스케일 비가 1 에서 5% 초과 (파일을 손으로 고쳤거나 점 대응이 어긋난 것)
  - 검출에 camera_3d 가 없다 / 각도 신뢰불가(angle 모드일 때)
  - 변환 결과가 **작업영역 밖** — 작업영역은 캘리브에 쓴 로봇 쪽 점들의 상자 ± 여유. 변환이 틀렸으면 여기서 거의 반드시 걸린다
  - 변환 결과가 로봇 도달 밖(|p| > REACH_MM) 또는 원점 100mm 안(m 단위 의심)

회전 (rz) — 🚨 위치와 분리했다
-------------------------------
  9/22 첫 시험 = **위치만**(*"인식 좌표로 이동 1회 · 집기 없이"* · 9/16 지시). 그래서 기본 `rz_mode='fixed'` 는
  캘리브 파일의 `grasp.rz_ref_deg`(티칭에서 쓴 rz)를 그대로 쓴다 — 각도 체인에 미확정이 둘 있어 첫 시험에 섞지 않는다.
  `rz_mode='angle'` = 부품 긴 축(이미지 각 `angle`)을 R_cam_to_base 로 돌려 base yaw 를 얻고
      rz = rz_sign × (yaw_long + 90) + rz_offset   (조우는 짧은 변을 문다 ⇒ 긴 축에 수직 = +90)
  🚨 `rz_sign`(±1 · HCR 오일러 규약이 ZYX 인지에 따라 부호가 뒤집힌다 · 9/8 §8 "조용히 틀릴 자리 ②")와
     `rz_offset_deg`(조우가 툴 X 축인지 Y 축인지 = 0 또는 90)는 **문서로 확정 불가 · 현장 시험 1회로 정한다**
     (부품을 30° 돌려 놓고 rz 변화가 +30 인지 −30 인지 · 조우가 짧은 변에 오나). 파일에 [실측필요] 로 남긴다.
  조우는 180° 대칭이라 rz 는 mod 180 으로 접고, rz_ref 에 가장 가까운 대표값을 골라 손목 회전을 최소화한다.

사용
----
  # ① 캘리브 파일 만들기 (3점법 · 카메라 점 = find_calib_blobs.py 출력 · 로봇 점 = 같은 블록 윗면에 TCP 대고 읽은 값)
  python -m bin_picking.src.communication.cam_to_base build \
      --blobs shot.blobs.json --robot-points "x,y,z; x,y,z; x,y,z; x,y,z" \
      --capture-pose X Y Z RX RY RZ --rz-ref RZ --out bin_picking/config/calibration/cam_to_base_0922.json
  (로봇 점은 @robot_points.txt 로도 받는다 — 한 줄에 x,y,z · 펜던트 값을 메모장에 적어 넘길 때)
  # ② 파일만으로 검산 (로봇 안 움직임) — six.json 을 base 포즈로 바꿔 보여준다
  python -m bin_picking.src.communication.cam_to_base check --calib <file> --six <six.json> [--hover-mm 50]
  # ③ 서버가 쓴다
  python -m bin_picking.src.communication.pick_socket_server --mode vision --six-json … --calib <file> --hover-mm 50
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

try:
    from ..acquisition.work_coord_3point import (
        MAX_RESIDUAL_MM, SCALE_TOLERANCE, WorkCoordError,
        apply_transform, solve_rigid_transform, RigidTransformResult,
    )
except ImportError:  # 단독 실행 대비
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))
    from acquisition.work_coord_3point import (  # type: ignore
        MAX_RESIDUAL_MM, SCALE_TOLERANCE, WorkCoordError,
        apply_transform, solve_rigid_transform, RigidTransformResult,
    )

SCHEMA = "orinu_cam_to_base_v1"

# --- 로봇 물리 한계 (base 좌표 결과의 1차 관문) ---
REACH_MM = 1800.0            # HCR-10L 공식 도달 1,800(9/4 라벨) · DH 합 1,834
MIN_FROM_ORIGIN_MM = 100.0   # TCP 가 베이스 원점 100mm 안에 올 수 없다 — m 단위(0.4 같은 값)를 여기서 잡는다
BASE_Z_RANGE_MM = (-500.0, 1200.0)   # 테이블이 베이스보다 낮을 수 있어 음수 허용 · 위는 팔 길이

# --- 작업영역(캘리브 점 상자 ± 여유) 기본 여유 ---
WORKSPACE_XY_MARGIN_MM = 150.0   # 블록을 빈 모서리에 놓으면 빈 전체가 상자 안 · 안쪽에만 놓았을 때를 위한 여유
WORKSPACE_Z_BELOW_MM = 80.0      # 블록 윗면(TCP 를 댄 점) 아래 = 바닥. 블록 높이 ≤30 + 골판지 바닥 처짐·P_capture 기울기(RY −2.6° ⇒ 화면 끝 ±14)
                                 #   + 헐거운 마스크가 바닥 픽셀을 섞는 몫(9/16 실물 Zc 482·518 = 바닥 450 보다 깊음). 목적은 수백 mm 오류 검출이라 80 이어도 잃는 것이 없다
WORKSPACE_Z_ABOVE_MM = 150.0     # 부품 윗면 최대(눕힘 높이 ≤ 35) + 겹침 여유

# --- P_capture 대조 허용 (같은 자세인가) ---
CAPTURE_POSE_TOL_MM = 5.0
CAPTURE_POSE_TOL_DEG = 2.0


class CamToBaseError(RuntimeError):
    """캘리브 파일·변환 결과가 신뢰 조건에 못 미친다. 🚨 이 예외가 나면 로봇에 좌표를 보내지 않는다."""


# ============================================================
# 캘리브 파일 = dataclass
# ============================================================
@dataclass
class GraspFrame:
    """로봇에 보낼 자세 파라미터 — 위치(xyz)는 변환이 주고, 이 넷은 사람이 정한다."""
    rx_deg: float = 180.0          # 툴이 아래를 보는 자세. 9/16 P_capture 실측 RX −178.85 ≈ 180 · pick_test 도 같은 부류 [확인필요]
    ry_deg: float = 0.0            # 9/16 P_capture RY −2.6 ≈ 0
    rz_ref_deg: float = -90.0      # 'fixed' 모드가 그대로 쓰는 rz · 9/16 P_capture RZ −90.03 (pick_test P_grip rz 로 바꿀 것 [확인필요])
    rz_sign: int = 1               # 🚨 [실측필요] +1 | −1 — HCR rx,ry,rz 규약(ZYX?)에 따라 yaw 부호가 뒤집힌다
    rz_offset_deg: float = 0.0     # 🚨 [실측필요] 조우 닫힘 방향이 툴 X 축이면 0 · 툴 Y 축이면 90
    z_offset_mm: float = 0.0       # 파지 깊이 — camera_3d.Zc 는 부품 **윗면** · 조우가 잡으려면 이만큼 더 내려가야 할 수 있다(음수) [실측필요]


@dataclass
class Workspace:
    """캘리브에 쓴 로봇 쪽 점들로 만든 상자. 변환 결과가 이 밖이면 변환이 틀렸다고 본다."""
    xy_min: list[float]
    xy_max: list[float]
    z_min: float
    z_max: float

    @classmethod
    def from_robot_points(cls, rob: np.ndarray, xy_margin: float = WORKSPACE_XY_MARGIN_MM,
                          z_below: float = WORKSPACE_Z_BELOW_MM, z_above: float = WORKSPACE_Z_ABOVE_MM) -> "Workspace":
        rob = np.asarray(rob, dtype=np.float64)
        return cls(
            xy_min=[float(rob[:, 0].min() - xy_margin), float(rob[:, 1].min() - xy_margin)],
            xy_max=[float(rob[:, 0].max() + xy_margin), float(rob[:, 1].max() + xy_margin)],
            z_min=float(rob[:, 2].min() - z_below),
            z_max=float(rob[:, 2].max() + z_above),
        )

    def contains(self, p: Sequence[float]) -> tuple[bool, str]:
        x, y, z = (float(v) for v in p[:3])
        if not (self.xy_min[0] <= x <= self.xy_max[0]):
            return False, f"x={x:.1f} 가 작업영역 {self.xy_min[0]:.0f}~{self.xy_max[0]:.0f} 밖"
        if not (self.xy_min[1] <= y <= self.xy_max[1]):
            return False, f"y={y:.1f} 가 작업영역 {self.xy_min[1]:.0f}~{self.xy_max[1]:.0f} 밖"
        if not (self.z_min <= z <= self.z_max):
            return False, f"z={z:.1f} 가 작업영역 {self.z_min:.0f}~{self.z_max:.0f} 밖(바닥−{WORKSPACE_Z_BELOW_MM:.0f}~블록윗면+{WORKSPACE_Z_ABOVE_MM:.0f})"
        return True, ""


@dataclass
class Calibration:
    T_cam_to_base: np.ndarray
    quality: dict
    capture_pose_tcp: list[float]          # [x,y,z,rx,ry,rz] mm·deg — 이 자세에서 찍은 장면에만 유효
    workspace: Workspace
    grasp: GraspFrame
    points_camera: np.ndarray
    points_robot: np.ndarray
    method: str = "3point_kabsch_fixed_capture_pose"
    created_at: str = ""
    source: dict = field(default_factory=dict)
    notes: str = ""
    path: Optional[str] = None

    @property
    def R(self) -> np.ndarray:
        return self.T_cam_to_base[:3, :3]

    def report(self) -> str:
        q = self.quality
        t = self.T_cam_to_base[:3, 3]
        lines = [
            f"캘리브 {self.path or '(메모리)'}  ·  {self.method}  ·  {self.created_at}",
            f"  T 이동 = [{t[0]:.1f}, {t[1]:.1f}, {t[2]:.1f}] mm  ·  점 {q.get('n_points')}쌍",
            f"  잔차 RMS {q.get('residual_rms_mm', float('nan')):.2f} mm · 최대 {q.get('max_error_mm', float('nan')):.2f} mm"
            f" · 스케일 비 {q.get('scale_ratio', float('nan')):.4f}",
            f"  P_capture = {[round(v, 2) for v in self.capture_pose_tcp]}  🚨 이 자세에서 찍은 장면에만 유효",
            f"  작업영역 x {self.workspace.xy_min[0]:.0f}~{self.workspace.xy_max[0]:.0f} · y {self.workspace.xy_min[1]:.0f}~{self.workspace.xy_max[1]:.0f}"
            f" · z {self.workspace.z_min:.0f}~{self.workspace.z_max:.0f}",
            f"  자세 rx {self.grasp.rx_deg} · ry {self.grasp.ry_deg} · rz_ref {self.grasp.rz_ref_deg}"
            f" · rz_sign {self.grasp.rz_sign:+d} · rz_offset {self.grasp.rz_offset_deg} · z_offset {self.grasp.z_offset_mm} [실측필요 표시는 파일 notes]",
        ]
        return "\n".join(lines)


# ============================================================
# ① 만들기 · 저장 · 로드
# ============================================================
def build_calibration(
    points_camera: Sequence[Sequence[float]],
    points_robot: Sequence[Sequence[float]],
    capture_pose_tcp: Sequence[float],
    grasp: Optional[GraspFrame] = None,
    *,
    source: Optional[dict] = None,
    notes: str = "",
    xy_margin_mm: float = WORKSPACE_XY_MARGIN_MM,
) -> Calibration:
    """대응점 N쌍(N≥3) + P_capture → Calibration. 실패하면 WorkCoordError/CamToBaseError (파일을 만들지 않는다)."""
    cam = np.asarray(points_camera, dtype=np.float64)
    rob = np.asarray(points_robot, dtype=np.float64)
    cap = _as_pose6(capture_pose_tcp, "capture_pose_tcp")
    # 🚨 P_capture 가 카메라 좌표계 값이면(z≈450·x,y 작음) 로봇 도달 검사가 잡지 못할 수 있어 원점 거리로 본다
    if np.linalg.norm(cap[:3]) < MIN_FROM_ORIGIN_MM:
        raise CamToBaseError(f"capture_pose_tcp xyz={cap[:3]} 가 원점 {MIN_FROM_ORIGIN_MM}mm 안 — m 단위나 빈 값 의심")

    r: RigidTransformResult = solve_rigid_transform(cam, rob, strict=True)   # 잔차·스케일·반사 검사 포함(8/8 검증)
    ws = Workspace.from_robot_points(rob, xy_margin=xy_margin_mm)
    return Calibration(
        T_cam_to_base=r.T,
        quality={
            "residual_rms_mm": r.residual_mm, "max_error_mm": r.max_error_mm,
            "per_point_mm": r.per_point_mm.tolist(), "scale_ratio": r.scale_ratio, "n_points": r.n_points,
        },
        capture_pose_tcp=cap.tolist(),
        workspace=ws,
        grasp=grasp or GraspFrame(),
        points_camera=cam, points_robot=rob,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        source=source or {},
        notes=notes,
    )


def save_calibration(calib: Calibration, path: str | Path) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    g = calib.grasp
    payload = {
        "schema": SCHEMA,
        "units": "mm_deg",
        "method": calib.method,
        "valid_only_at_capture_pose": True,
        "capture_pose_tcp_mm_deg": calib.capture_pose_tcp,
        "T_cam_to_base": calib.T_cam_to_base.tolist(),
        "quality": calib.quality,
        "points": {"camera_mm": calib.points_camera.tolist(), "robot_mm": calib.points_robot.tolist()},
        "workspace": {"xy_min": calib.workspace.xy_min, "xy_max": calib.workspace.xy_max,
                      "z_min": calib.workspace.z_min, "z_max": calib.workspace.z_max},
        "grasp": {
            "rx_deg": g.rx_deg, "ry_deg": g.ry_deg, "rz_ref_deg": g.rz_ref_deg,
            "rz_sign": g.rz_sign, "rz_offset_deg": g.rz_offset_deg, "z_offset_mm": g.z_offset_mm,
            "_unverified": ["rz_sign", "rz_offset_deg", "z_offset_mm", "rx_deg", "ry_deg"],
            "_how_to_verify": "부품 하나를 30° 돌려 놓고 rz_mode=angle 로 이동 → rz 변화 부호(rz_sign) · 조우가 짧은 변에 오나(rz_offset)",
        },
        "created_at": calib.created_at,
        "source": calib.source,
        "notes": calib.notes,
    }
    p.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    calib.path = str(p)
    return str(p)


def load_calibration(path: str | Path, *, max_residual_mm: float = MAX_RESIDUAL_MM) -> Calibration:
    """파일 → Calibration. 🚨 스키마·단위·SE(3)·품질 넷 중 하나라도 어긋나면 예외(조용히 쓰지 않는다)."""
    p = Path(path)
    if not p.exists():
        raise CamToBaseError(
            f"캘리브 파일이 없다: {p}\n"
            "  → hand-eye(3점법)를 먼저 한다: find_calib_blobs.py → cam_to_base build\n"
            "  🚨 파일 없이 카메라 좌표를 로봇에 보내면 엉뚱한 곳으로 간다 — 이 계층이 그것을 막는다"
        )
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CamToBaseError(f"{p}: JSON 파싱 실패 — {e}") from e
    if d.get("schema") != SCHEMA:
        raise CamToBaseError(f"{p}: schema={d.get('schema')!r} — 기대 {SCHEMA!r} (work_coord_3point.save_calibration 파일이면 build 로 다시 만들 것)")
    if d.get("units") != "mm_deg":
        raise CamToBaseError(f"{p}: units={d.get('units')!r} — mm_deg 만 받는다(m 파일은 1000배 사고)")

    T = np.asarray(d.get("T_cam_to_base"), dtype=np.float64)
    if T.shape != (4, 4) or not np.all(np.isfinite(T)):
        raise CamToBaseError(f"{p}: T_cam_to_base 가 4×4 유한행렬이 아니다 (shape={T.shape})")
    _check_se3(T, str(p))

    q = d.get("quality") or {}
    rms = float(q.get("residual_rms_mm", float("inf")))
    if not (rms <= max_residual_mm):
        raise CamToBaseError(f"{p}: 잔차 RMS {rms:.2f}mm > 허용 {max_residual_mm}mm — 이 캘리브로 로봇을 보내지 않는다(다시 티칭)")
    sc = float(q.get("scale_ratio", float("nan")))
    if not (abs(sc - 1.0) <= SCALE_TOLERANCE):
        raise CamToBaseError(f"{p}: 스케일 비 {sc} — 1.0±{SCALE_TOLERANCE:.0%} 밖(단위 혼동·점 대응 어긋남)")
    if int(q.get("n_points", 0)) < 3:
        raise CamToBaseError(f"{p}: n_points={q.get('n_points')} < 3")

    ws_d = d.get("workspace")
    pts = d.get("points") or {}
    cam = np.asarray(pts.get("camera_mm", []), dtype=np.float64)
    rob = np.asarray(pts.get("robot_mm", []), dtype=np.float64)
    if ws_d:
        ws = Workspace(xy_min=list(map(float, ws_d["xy_min"])), xy_max=list(map(float, ws_d["xy_max"])),
                       z_min=float(ws_d["z_min"]), z_max=float(ws_d["z_max"]))
    elif rob.size:
        ws = Workspace.from_robot_points(rob)
    else:
        raise CamToBaseError(f"{p}: workspace 도 points.robot_mm 도 없다 — 작업영역 검사를 할 수 없어 거부")

    # ⭐ 점이 들어 있으면 T 로 다시 재서 저장된 잔차와 맞는지 본다 — 파일 일부만 고친 것을 잡는다(extrinsic_io 의 baseline 재계산과 같은 형태)
    if cam.size and rob.size and cam.shape == rob.shape and cam.ndim == 2:
        pred = apply_transform(T, cam)
        rms2 = float(np.sqrt(np.mean(np.sum((pred - rob) ** 2, axis=1))))
        if abs(rms2 - rms) > 0.5:
            raise CamToBaseError(f"{p}: 저장 잔차 {rms:.2f} vs T 로 재계산 {rms2:.2f}mm — 파일이 부분 수정된 것으로 보인다")

    g_d = d.get("grasp") or {}
    g = GraspFrame(
        rx_deg=float(g_d.get("rx_deg", 180.0)), ry_deg=float(g_d.get("ry_deg", 0.0)),
        rz_ref_deg=float(g_d.get("rz_ref_deg", -90.0)),
        rz_sign=int(g_d.get("rz_sign", 1)), rz_offset_deg=float(g_d.get("rz_offset_deg", 0.0)),
        z_offset_mm=float(g_d.get("z_offset_mm", 0.0)),
    )
    if g.rz_sign not in (1, -1):
        raise CamToBaseError(f"{p}: grasp.rz_sign={g.rz_sign} — +1 또는 -1")

    cap = d.get("capture_pose_tcp_mm_deg")
    if cap is None:
        raise CamToBaseError(f"{p}: capture_pose_tcp_mm_deg 가 없다 — 어느 자세의 캘리브인지 모르면 쓸 수 없다")
    cap6 = _as_pose6(cap, "capture_pose_tcp_mm_deg")

    return Calibration(
        T_cam_to_base=T, quality=q, capture_pose_tcp=cap6.tolist(), workspace=ws, grasp=g,
        points_camera=cam, points_robot=rob, method=str(d.get("method", "?")),
        created_at=str(d.get("created_at", "")), source=d.get("source") or {}, notes=str(d.get("notes", "")),
        path=str(p),
    )


def check_capture_pose(calib: Calibration, actual_tcp: Sequence[float],
                       tol_mm: float = CAPTURE_POSE_TOL_MM, tol_deg: float = CAPTURE_POSE_TOL_DEG) -> tuple[bool, str]:
    """지금 로봇 자세가 캘리브 때 P_capture 와 같은가. 펜던트 값을 사람이 읽어 넣는다(소켓 프로토콜엔 아직 없다)."""
    a = _as_pose6(actual_tcp, "actual_tcp")
    c = np.asarray(calib.capture_pose_tcp, dtype=np.float64)
    d_mm = float(np.linalg.norm(a[:3] - c[:3]))
    d_deg = float(max(abs(_wrap180(a[i] - c[i])) for i in range(3, 6)))
    ok = d_mm <= tol_mm and d_deg <= tol_deg
    return ok, f"위치 차 {d_mm:.1f}mm(허용 {tol_mm}) · 각도 차 {d_deg:.2f}°(허용 {tol_deg})" + ("" if ok else " ⇒ 🚨 P_capture 가 다르다 — 캘리브를 다시 만들거나 capture_test 로 돌아갈 것")


# ============================================================
# ② 검출 1건 → base 파지 포즈
# ============================================================
def camera_xyz_to_base(calib: Calibration, xyz_cam_mm: Sequence[float]) -> np.ndarray:
    """카메라 점 1개 → base 점. 도달·원점·작업영역 3중 검사. 실패 = CamToBaseError."""
    p = np.asarray(xyz_cam_mm, dtype=np.float64).reshape(-1)
    if p.size != 3 or not np.all(np.isfinite(p)):
        raise CamToBaseError(f"camera xyz 가 유한한 3원소가 아니다: {xyz_cam_mm!r}")
    out = apply_transform(calib.T_cam_to_base, p)
    check_base_point_physical(out)
    ok, why = calib.workspace.contains(out)
    if not ok:
        raise CamToBaseError(
            f"변환 결과 base=({out[0]:.1f}, {out[1]:.1f}, {out[2]:.1f}) 가 캘리브 작업영역 밖 — {why}. "
            "⇒ P_capture 가 캘리브 때와 다르거나 캘리브 파일이 낡았다(카메라 좌표 원값: "
            f"{p[0]:.1f}, {p[1]:.1f}, {p[2]:.1f})"
        )
    return out


def check_base_point_physical(p_base: Sequence[float]) -> None:
    """로봇 물리 한계 — 작업영역보다 거친 1차 관문. pick_socket_server.validate_pose(frame='base') 와 같은 기준."""
    x, y, z = (float(v) for v in p_base[:3])
    n = math.sqrt(x * x + y * y + z * z)
    if n > REACH_MM:
        raise CamToBaseError(f"base 점 |p|={n:.0f}mm > 도달 {REACH_MM:.0f}mm — 변환/단위 오류(7/29 z=3136 사고 형태)")
    if n < MIN_FROM_ORIGIN_MM:
        raise CamToBaseError(f"base 점 |p|={n:.1f}mm < {MIN_FROM_ORIGIN_MM}mm — m 단위 의심(로봇 원점 안에 TCP 가 올 수 없다)")
    if not (BASE_Z_RANGE_MM[0] <= z <= BASE_Z_RANGE_MM[1]):
        raise CamToBaseError(f"base z={z:.1f}mm 가 {BASE_Z_RANGE_MM} 밖")


def part_yaw_base_deg(calib: Calibration, angle_img_deg: float) -> float:
    """이미지 평면 긴 축 각 → base 평면 yaw(deg · [0,180)). 카메라 자세를 R 로 정확히 반영한다(추측 없음).

    d_cam = [cos a, sin a, 0] (이미지 x 오른쪽 · y 아래 · `mask_to_angle._normalize_angle` 규약) → R d_cam → xy 투영 → atan2.
    🚨 광축이 base z 와 평행이 아니면(카메라가 기울면) 투영이 줄어들 뿐 방향은 유지된다. 긴 축은 180° 대칭이라 [0,180).
    """
    a = math.radians(float(angle_img_deg))
    d_cam = np.array([math.cos(a), math.sin(a), 0.0])
    d_base = calib.R @ d_cam
    if math.hypot(d_base[0], d_base[1]) < 1e-6:
        raise CamToBaseError("긴 축이 base 수직으로 투영됨 — 카메라가 옆을 보고 있다(P_capture 아님)")
    yaw = math.degrees(math.atan2(d_base[1], d_base[0])) % 180.0
    if yaw > 180.0 - 1e-9:      # −ε 가 180−ε 로 접히는 수치 잔재 → 0 으로 정규화(긴 축은 0 ≡ 180)
        yaw = 0.0
    return yaw


def _wrap180(deg: float) -> float:
    return (deg + 180.0) % 360.0 - 180.0


def rz_for_grasp(calib: Calibration, angle_img_deg: float) -> float:
    """rz_mode='angle' 의 rz. 조우는 짧은 변을 문다 ⇒ 닫힘 방향 = 긴 축 + 90.
    rz = rz_sign × (yaw_long + 90) + rz_offset · 180° 대칭이라 rz_ref 에 가장 가까운 대표값."""
    g = calib.grasp
    yaw_close = part_yaw_base_deg(calib, angle_img_deg) + 90.0
    rz_raw = g.rz_sign * yaw_close + g.rz_offset_deg
    # 180 주기 대표값 중 rz_ref 에 가장 가까운 것 (손목 회전 최소 · J6 한계 회피)
    k = round((g.rz_ref_deg - rz_raw) / 180.0)
    return float(rz_raw + 180.0 * k)


def det_to_base_pose(
    det: dict,
    calib: Calibration,
    *,
    hover_mm: float = 0.0,
    rz_mode: str = "fixed",
    require_reliable_angle: bool = True,
) -> list[float]:
    """6요소 검출 1건 → 로봇 base 파지 포즈 [x, y, z, rx, ry, rz] (mm · deg).

    hover_mm  : 결과 z 에 더한다(위로). 9/22 "집기 없이 이동 1회" = 50 권장 — 펜던트 pickOne 은 이 z 를 목표로 하강·닫기·상승하므로
                띄운 만큼 위에서 허공을 물고 끝난다(부품 안 건드림). 0 이면 실제 파지 높이(+ grasp.z_offset_mm).
    rz_mode   : 'fixed' = calib.grasp.rz_ref_deg 그대로(위치만 시험) / 'angle' = 부품 각도 반영(부호·오프셋 [실측필요])
    """
    if calib is None:
        raise CamToBaseError("캘리브가 None — 카메라 좌표를 그대로 보내는 경로는 없다")
    cam = det.get("camera_3d")
    if not cam:
        raise CamToBaseError("camera_3d 없음 — 픽셀 좌표(x,y)만으로는 로봇을 못 움직인다")
    if isinstance(cam, dict):
        try:
            xyz = [cam["Xc"], cam["Yc"], cam["Zc"]]
        except KeyError as e:
            raise CamToBaseError(f"camera_3d dict 에 {e} 키가 없다 (받은 키: {list(cam)})") from e
    else:
        xyz = list(cam)
        if len(xyz) != 3:
            raise CamToBaseError(f"camera_3d 가 3개여야 하는데 {len(xyz)}개")
    zc = float(xyz[2])
    if not (200.0 <= zc <= 1500.0):
        # 카메라 z 는 변환 전에도 물리 범위가 있다(7/29 실측 99% 400~600) — 여기서 먼저 잡으면 원인이 카메라 쪽임을 안다
        raise CamToBaseError(f"camera_3d.Zc={zc}mm 가 카메라 물리 범위 200~1500 밖 — depth 단위(raw×10/65535=m) 의심")

    p_base = camera_xyz_to_base(calib, xyz)
    g = calib.grasp

    if rz_mode == "fixed":
        rz = float(g.rz_ref_deg)
    elif rz_mode == "angle":
        angle = det.get("angle")
        if angle is None:
            raise CamToBaseError("angle 없음 — rz_mode=angle 은 각도가 필요하다")
        if require_reliable_angle and det.get("angle_reliable") is False:
            raise CamToBaseError(f"angle_reliable=False ({det.get('angle_note', '')}) — 각도를 신뢰할 수 없어 거부")
        rz = rz_for_grasp(calib, float(angle))
    else:
        raise CamToBaseError(f"rz_mode={rz_mode!r} — 'fixed' | 'angle'")

    z = float(p_base[2]) + float(g.z_offset_mm) + float(hover_mm)
    pose = [float(p_base[0]), float(p_base[1]), z, float(g.rx_deg), float(g.ry_deg), rz]
    check_base_point_physical(pose)     # hover 를 더한 뒤에도 물리 범위 안인가
    return pose


# ============================================================
# 보조
# ============================================================
def _as_pose6(v: Sequence[float], name: str) -> np.ndarray:
    a = np.asarray(v, dtype=np.float64).reshape(-1)
    if a.size != 6 or not np.all(np.isfinite(a)):
        raise CamToBaseError(f"{name}: [x,y,z,rx,ry,rz] 6개 유한값이어야 한다 (받은 것: {v!r})")
    return a


def _check_se3(T: np.ndarray, where: str) -> None:
    R = T[:3, :3]
    err = float(np.max(np.abs(R.T @ R - np.eye(3))))
    det = float(np.linalg.det(R))
    if err > 1e-4:
        raise CamToBaseError(f"{where}: 회전부 직교성 위반(오차 {err:.2e}) — 파일 손상·손 편집 의심")
    if det < 0:
        raise CamToBaseError(f"{where}: det(R)={det:.4f} < 0 = 반사행렬 — 좌우가 뒤집힌다(8/14 l↔r 사고 형태)")
    if abs(det - 1.0) > 1e-4:
        raise CamToBaseError(f"{where}: det(R)={det:.6f} ≠ 1 — 스케일이 섞였다")
    if not np.allclose(T[3], [0, 0, 0, 1], atol=1e-9):
        raise CamToBaseError(f"{where}: 마지막 행이 [0,0,0,1] 이 아니다 ({T[3]})")


def load_six_detections(six_json: str | Path) -> tuple[dict, list[dict]]:
    d = json.loads(Path(six_json).read_text(encoding="utf-8"))
    dets = d.get("detections") or d.get("predictions") or []
    return d, dets


# ============================================================
# CLI
# ============================================================
def _parse_points(spec: str, name: str) -> np.ndarray:
    """점 목록 한 문자열 → (N,3).

    형식 두 가지 (🚨 음수 좌표가 '-560,20,130' 처럼 '-' 로 시작하면 argparse 가 옵션으로 오해한다 → 한 문자열로 받는다)
      ① "x,y,z; x,y,z; …"            세미콜론 구분
      ② "@points.txt"                 파일 · 한 줄에 x,y,z · '#' 뒤는 주석 (펜던트 값을 메모장에 적어 두고 넘길 때)
    """
    text = spec.strip()
    if text.startswith("@"):
        p = Path(text[1:])
        if not p.exists():
            raise SystemExit(f"🔴 {name}: 파일이 없다 {p}")
        lines = [ln.split("#", 1)[0].strip() for ln in p.read_text(encoding="utf-8").splitlines()]
        items = [ln for ln in lines if ln]
    else:
        items = [s for s in text.split(";") if s.strip()]
    pts = []
    for s in items:
        try:
            parts = [float(v) for v in s.replace(" ", "").split(",") if v != ""]
        except ValueError:
            raise SystemExit(f"🔴 {name} '{s}' — 숫자가 아니다")
        if len(parts) != 3:
            raise SystemExit(f"🔴 {name} '{s}' — x,y,z 세 값이어야 한다")
        pts.append(parts)
    if not pts:
        raise SystemExit(f"🔴 {name}: 점이 하나도 없다")
    return np.asarray(pts, dtype=np.float64)


def _cmd_build(a: argparse.Namespace) -> int:
    if a.blobs:
        b = json.loads(Path(a.blobs).read_text(encoding="utf-8"))
        blobs = sorted(b["blobs"], key=lambda x: x["id"])
        if a.blob_ids:
            want = [int(v) for v in a.blob_ids.split(",")]
            blobs = [x for x in blobs if x["id"] in want]
            blobs.sort(key=lambda x: want.index(x["id"]))
        cam = np.asarray([x["cam_xyz_mm"] for x in blobs], dtype=np.float64)
        src = {"blobs_json": str(a.blobs), "blob_ids": [x["id"] for x in blobs], "depth": b.get("source")}
    elif a.camera_points:
        cam = _parse_points(a.camera_points, "--camera-points")
        src = {"camera_points": "cli"}
    else:
        raise SystemExit("🔴 --blobs 또는 --camera-points 가 필요하다")
    rob = _parse_points(a.robot_points, "--robot-points")
    if rob.shape != cam.shape:
        raise SystemExit(f"🔴 카메라 점 {cam.shape[0]}개 vs 로봇 점 {rob.shape[0]}개 — 같은 순서·같은 개수여야 한다(블록 id 순)")
    grasp = GraspFrame(rx_deg=a.rx, ry_deg=a.ry, rz_ref_deg=a.rz_ref, rz_sign=a.rz_sign,
                       rz_offset_deg=a.rz_offset, z_offset_mm=a.z_offset)
    try:
        calib = build_calibration(cam, rob, a.capture_pose, grasp, source=src, notes=a.notes)
    except (WorkCoordError, CamToBaseError) as e:
        print(f"🔴 캘리브 실패(파일을 만들지 않는다): {e}")
        return 2
    out = save_calibration(calib, a.out)
    print(calib.report())
    print(f"→ 저장 {out}")
    # 검산 ① 왕복 — 캘리브 점이 복원되나
    pred = apply_transform(calib.T_cam_to_base, cam)
    for i, (pp, rr) in enumerate(zip(pred, rob), 1):
        print(f"   P{i}: 예측 {np.round(pp, 1).tolist()} vs 실측 {np.round(rr, 1).tolist()} · 차 {np.linalg.norm(pp - rr):.2f}mm")
    print("다음 = 캘리브에 쓰지 않은 새 블록 1개로 검산 ②(HAND_EYE_CARD §4) → check 로 six.json 검산 → 서버 --calib")
    return 0


def _cmd_check(a: argparse.Namespace) -> int:
    try:
        calib = load_calibration(a.calib)
    except CamToBaseError as e:
        print(f"🔴 {e}")
        return 2
    print(calib.report())
    if a.actual_tcp:
        ok, msg = check_capture_pose(calib, a.actual_tcp)
        print(("🟢 " if ok else "🔴 ") + "P_capture 대조: " + msg)
    if a.cam_point:
        # 검산 ② (HAND_EYE_CARD §4) — 캘리브에 **쓰지 않은** 새 블록: 카메라 점 → base 예측을 찍어 로봇 실측과 사람이 대조한다
        cp = _parse_points(a.cam_point, "--cam-point")
        for i, p in enumerate(cp, 1):
            try:
                b = camera_xyz_to_base(calib, p)
                print(f"  검산 점 {i}: cam {np.round(p, 1).tolist()} → base 예측 {np.round(b, 1).tolist()}"
                      f"   ⇐ 로봇 TCP 를 그 블록 윗면에 대고 읽은 값과 비교 · 차 <5mm 통과 · 5~10 주의 · >10 재캘리브")
            except CamToBaseError as e:
                print(f"  🔴 검산 점 {i}: {e}")
    if not a.six:
        return 0
    _, dets = load_six_detections(a.six)
    print(f"\n{a.six}: 검출 {len(dets)}건 → base 포즈 (hover {a.hover_mm}mm · rz_mode {a.rz_mode})")
    n_ok = 0
    for i, det in enumerate(dets):
        cam = det.get("camera_3d")
        try:
            pose = det_to_base_pose(det, calib, hover_mm=a.hover_mm, rz_mode=a.rz_mode)
            n_ok += 1
            print(f"  🟢 #{i} {det.get('label', '?'):<28} cam={cam} → base={[round(v, 1) for v in pose]}")
        except CamToBaseError as e:
            print(f"  🔴 #{i} {det.get('label', '?'):<28} cam={cam} → 거부: {e}")
    print(f"보낼 수 있는 포즈 {n_ok}/{len(dets)}  (로봇은 움직이지 않았다 — 서버 --calib 로 넘겨야 간다)")
    return 0 if n_ok else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="카메라→base 변환 계층: 캘리브 파일 만들기 / 검산")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="3점법 대응점 → 캘리브 파일")
    b.add_argument("--blobs", help="find_calib_blobs.py 출력 JSON (카메라 점)")
    b.add_argument("--blob-ids", help="쓸 블록 id 순서 (예 1,2,3,4) — 로봇 점과 같은 순서")
    b.add_argument("--camera-points", help="블롭 JSON 대신 직접: \"x,y,z; x,y,z; …\" (mm) 또는 @파일")
    b.add_argument("--robot-points", required=True,
                   help="같은 블록 윗면에 TCP 를 대고 읽은 base 좌표 — \"x,y,z; x,y,z; …\" (mm · 블록 id 순) 또는 @파일(한 줄에 x,y,z)")
    b.add_argument("--capture-pose", type=float, nargs=6, required=True, metavar=("X", "Y", "Z", "RX", "RY", "RZ"),
                   help="촬영 자세 P_capture 의 TCP (펜던트 capture_test 값)")
    b.add_argument("--rz-ref", type=float, required=True, help="'fixed' 모드가 쓸 rz (티칭에서 집었을 때의 rz)")
    b.add_argument("--rx", type=float, default=180.0)
    b.add_argument("--ry", type=float, default=0.0)
    b.add_argument("--rz-sign", type=int, default=1, choices=(1, -1))
    b.add_argument("--rz-offset", type=float, default=0.0)
    b.add_argument("--z-offset", type=float, default=0.0, help="파지 깊이 보정(mm · 음수 = 더 내려감) [실측필요]")
    b.add_argument("--notes", default="")
    b.add_argument("--out", required=True)
    b.set_defaults(func=_cmd_build)

    c = sub.add_parser("check", help="캘리브 파일 검산 (+ six.json → base 포즈 미리보기 · 로봇 안 움직임)")
    c.add_argument("--calib", required=True)
    c.add_argument("--six", help="6요소 JSON")
    c.add_argument("--hover-mm", type=float, default=0.0)
    c.add_argument("--rz-mode", choices=("fixed", "angle"), default="fixed")
    c.add_argument("--actual-tcp", type=float, nargs=6, metavar=("X", "Y", "Z", "RX", "RY", "RZ"),
                   help="지금 펜던트가 보여주는 TCP — 캘리브 P_capture 와 같은지 대조")
    c.add_argument("--cam-point", help="검산 ②: 캘리브에 안 쓴 블록의 카메라 점 \"x,y,z\"(find_calib_blobs 출력) → base 예측을 찍는다")
    c.set_defaults(func=_cmd_check)

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    raise SystemExit(main())
