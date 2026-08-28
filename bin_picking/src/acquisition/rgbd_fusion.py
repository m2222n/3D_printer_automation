"""
Blaze depth ↔ ACE2 RGB 정합 (두 카메라 RGB-D 융합)
=====================================================

⚠️ 왜 필요한가 — 기존 `detect_and_output.py`가 못 쓰는 이유
   기존 코드는 `safe_depth_at(depth, cx, cy)`로 **RGB 픽셀 좌표를 depth 이미지에
   그대로** 넣습니다. RealSense처럼 하드웨어 정렬된 단일 카메라에선 맞지만,
   Blaze(848×480 ToF) + ACE2(5MP RGB)는 **해상도·화각·광학중심이 전부 다른
   별개 카메라**(baseline ~32mm)라 같은 (x,y)가 전혀 다른 지점을 가리킵니다.
   → 그 좌표를 그대로 쓰면 z가 조용히 틀립니다(에러도 안 남).

⭐ 이 모듈의 방식 — "depth를 RGB로 투영"(forward projection)
   역방향(RGB 픽셀 → 3D)은 z를 모르면 광선 하나로만 정해져 풀 수 없습니다.
   그래서 정방향으로 풉니다:

     Blaze depth 픽셀 전부 → Blaze 3D 점구름 → (extrinsic 역변환) → ACE2 좌표계
       → ACE2 intrinsic으로 투영 → ACE2 픽셀 격자에 z 기록 = "정렬된 depth map"

   이렇게 만든 정렬 depth map은 ACE2 RGB와 **같은 픽셀 격자**를 쓰므로,
   기존 `detect_and_output.py`가 **수정 없이** 그대로 소비할 수 있습니다.

⭐ z-buffer(가림 처리)
   여러 depth 점이 같은 RGB 픽셀로 투영되면 **가장 가까운 것만** 남깁니다.
   빈피킹은 부품이 겹쳐 쌓이므로, 뒤쪽 부품 depth가 앞쪽을 덮어쓰면
   로봇이 없는 자리를 집으러 갑니다.

⭐ 단위: 내부 계산 전부 **mm** (Blaze depth 원본이 uint16 mm, 한솔 6요소 z도 mm)

사용:
    from bin_picking.src.acquisition.rgbd_fusion import align_depth_to_ace2

    aligned = align_depth_to_ace2(blaze_depth_mm, ace2_shape=(H, W))
    # → aligned를 기존 detect_and_output(color, aligned, ...)에 그대로 투입
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

from .extrinsic_io import Extrinsic, ExtrinsicError, load_extrinsic

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ACE2_INTRINSICS = PROJECT_ROOT / "bin_picking" / "config" / "ace2_intrinsics.json"
BLAZE_INTRINSICS = PROJECT_ROOT / "bin_picking" / "config" / "blaze_intrinsics.json"

# 정렬 depth map에서 "값 없음"을 나타내는 값. 0 = 기존 safe_depth_at의 invalid 규약과 동일.
NO_DEPTH = 0

# Blaze ToF 유효 거리(mm). 이 밖은 노이즈로 보고 버림.
# Blaze-112 사양 0.3~10m이나, 빈피킹 실사용은 0.5~0.8m(촬영 가이드) → 넉넉히 잡음.
DEPTH_MIN_MM = 100.0
DEPTH_MAX_MM = 5000.0


class FusionError(RuntimeError):
    """정합에 필요한 캘리브 파일이 없거나 입력이 규약에 안 맞을 때."""


@dataclass(frozen=True)
class Intrinsics:
    """핀홀 intrinsic. detect_and_output의 dict 규약과 상호 변환 가능."""

    fx: float
    fy: float
    cx: float
    cy: float
    width: Optional[int] = None
    height: Optional[int] = None
    # 🐛 7/31 현장에서 드러난 결함: 이 필드가 아예 없어 **왜곡 보정이 통째로 빠져** 있었다.
    #    화면 중앙은 맞는데 가장자리로 갈수록 밀려, 오버레이에서 상자 밖 천장까지
    #    depth가 찍혔다. Blaze는 108° 초광각(k1=-0.043)이라 영향이 특히 크다.
    #    ⚠️ None이면 왜곡 0으로 간주(구 캘리브 json 호환).
    dist: Optional[Tuple[float, ...]] = None

    @property
    def K(self) -> np.ndarray:
        return np.array(
            [[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )

    @property
    def D(self) -> np.ndarray:
        """OpenCV 왜곡계수 벡터. 없으면 0(=보정 없음)."""
        if not self.dist:
            return np.zeros((5, 1), dtype=np.float64)
        return np.asarray(self.dist, dtype=np.float64).reshape(-1, 1)

    @property
    def has_dist(self) -> bool:
        return bool(self.dist) and any(abs(c) > 1e-12 for c in self.dist)

    def dist_valid_radius(self) -> float:
        """왜곡 다항식이 **단조증가**를 유지하는 최대 정규화 반지름 r.

        🚨 7/31에 실측으로 드러난 함정: Blaze 캘리브 계수가 r≈1.05를 넘으면
           r'(=r·(1+k1r²+k2r⁴+k3r⁶))이 되레 **줄어든다**. 단조가 깨지면 역변환
           (undistortPoints)이 성립하지 않아, 반복을 100번 돌려도 엉뚱한 해로 수렴한다.
           실제로 화면 구석 왕복 오차가 **168px**까지 났다(중앙은 0px).
           원인 = 캘리브 보드가 화면 중앙 근처에만 있어 바깥이 전부 외삽.
        ⭐ 그러므로 "왜곡계수가 있다"와 "그 계수를 이 픽셀에 써도 된다"는 다른 문제다.
        """
        if not self.has_dist:
            return float("inf")
        d = list(self.dist) + [0.0] * 8
        k1, k2, k3 = d[0], d[1], d[4]
        r = np.linspace(1e-3, 3.0, 3000)
        rp = r * (1.0 + k1 * r**2 + k2 * r**4 + k3 * r**6)
        bad = np.nonzero(np.diff(rp) <= 0)[0]
        return float(r[bad[0]]) if bad.size else float("inf")

    def max_image_radius(self) -> float:
        """이미지 네 귀퉁이의 정규화 반지름(가장 먼 지점)."""
        if not (self.width and self.height):
            return float("nan")
        corners = [(0, 0), (self.width, 0), (0, self.height), (self.width, self.height)]
        return max(
            float(np.hypot((u - self.cx) / self.fx, (v - self.cy) / self.fy))
            for u, v in corners
        )

    def dist_usable(self) -> Tuple[bool, str]:
        """이 intrinsic의 왜곡계수를 **이미지 전체에** 적용해도 되는가."""
        if not self.has_dist:
            return False, "왜곡계수 없음(보정 없이 핀홀로 처리)"
        rmax, rok = self.max_image_radius(), self.dist_valid_radius()
        if not np.isfinite(rmax):
            return False, "이미지 크기 미기록 — 유효 범위를 판정할 수 없음"
        if rmax <= rok:
            return True, f"OK (이미지 최대 r={rmax:.2f} ≤ 유효 r={rok:.2f})"
        return False, (
            f"🚨 왜곡계수 유효범위 초과 — 이미지 최대 r={rmax:.2f} > 유효 r={rok:.2f}.\n"
            f"     r>{rok:.2f}에서 왜곡 다항식이 단조가 아니라 역변환이 성립하지 않는다.\n"
            f"     (켜면 화면 가장자리가 오히려 크게 어긋남 — 7/31 실측 168px)\n"
            f"     → 보드를 **화면 구석까지** 옮겨가며 재캘리브할 것."
        )

    def to_dict(self) -> dict:
        """detect_and_output.pixel_to_camera_3d 가 먹는 형식."""
        d = {"fx": self.fx, "fy": self.fy, "cx": self.cx, "cy": self.cy,
             "ppx": self.cx, "ppy": self.cy}
        if self.width is not None:
            d["width"] = self.width
        if self.height is not None:
            d["height"] = self.height
        return d

    def scaled(self, sx: float, sy: float) -> "Intrinsics":
        """이미지를 리사이즈했을 때 intrinsic도 같이 스케일.

        ACE2 5MP 원본으로 캘리브했는데 추론은 축소 이미지로 하는 경우가 흔해
        (basler_capture에도 /4 하드코딩이 있음) 여기서 정식으로 제공한다.
        """
        return Intrinsics(
            fx=self.fx * sx, fy=self.fy * sy,
            cx=self.cx * sx, cy=self.cy * sy,
            width=int(round(self.width * sx)) if self.width else None,
            height=int(round(self.height * sy)) if self.height else None,
            # ⭐ 왜곡계수는 **정규화 좌표** 기준이라 리사이즈해도 그대로다(스케일 금지).
            dist=self.dist,
        )


_DIST_WARNED: set = set()


def _use_dist(intr: Intrinsics, where: str) -> bool:
    """왜곡 보정을 적용할지 판정. 유효범위를 벗어나면 **쓰지 않고 한 번만 경고**.

    ⭐ 원칙 = "조용히 틀리지 말고 크게 실패하라". 다만 여기서 예외를 던지면
       캘리브가 미비한 상태에서 정합 자체가 아예 안 되므로, **핀홀로 물러서되
       이유를 반드시 알린다**(그냥 무시하면 7/31처럼 원인 규명에 시간이 든다).
    """
    ok, msg = intr.dist_usable()
    if ok:
        return True
    if intr.has_dist:
        key = (where, msg)
        if key not in _DIST_WARNED:
            _DIST_WARNED.add(key)
            print(f"[rgbd_fusion:{where}] 왜곡 보정 **미적용** — {msg}")
    return False


def _load_intrinsics_json(path: Path, what: str) -> Intrinsics:
    if not path.exists():
        raise FusionError(
            f"{what} intrinsic 없음: {path}\n"
            f"  → 캘리브 먼저: bin_picking/tests/calibrate_"
            f"{'ace2' if what == 'ACE2' else 'blaze'}_intrinsics.py\n"
            f"  ⚠️ 캘리브 결과 json은 git에 없음(로컬 상주) — Mac에서 만든 뒤 옮길 것."
        )
    d = json.loads(path.read_text(encoding="utf-8"))
    K = np.array(d["camera_matrix"], dtype=np.float64)
    if K.shape != (3, 3):
        raise FusionError(f"{path}: camera_matrix가 3×3이 아님 (shape={K.shape})")

    fx, fy = float(K[0, 0]), float(K[1, 1])
    # 7/27에 Blaze 추정값 fx=553/fy=188(비율 2.94)이 정렬 실패 원인이었던 전례가 있어,
    # 읽는 시점에 같은 결함을 막는다. 정상 카메라는 픽셀이 정사각형이라 fx≈fy.
    if fx <= 0 or fy <= 0:
        raise FusionError(f"{path}: fx/fy가 양수가 아님 (fx={fx}, fy={fy})")
    ratio = max(fx, fy) / min(fx, fy)
    if ratio > 1.5:
        raise FusionError(
            f"{path}: fx/fy 비율 {ratio:.2f} — 물리적으로 비정상(정상 카메라는 fx≈fy).\n"
            f"  fx={fx:.1f}, fy={fy:.1f}. FOV 역산 추정값일 가능성이 큼 → 실측 캘리브 필요.\n"
            f"  (7/27 Blaze fx=553/fy=188 = 비율 2.94 사례와 동일 결함)"
        )

    # 🐛 7/31: 여기서 dist_coeffs를 안 읽어 왜곡 보정이 통째로 빠져 있었다.
    #    json에는 처음부터 들어 있었는데 로더가 버리고 있었던 것.
    dist = d.get("dist_coeffs")
    if dist is not None:
        dist = tuple(float(x) for x in np.asarray(dist, dtype=np.float64).ravel())
        if len(dist) not in (4, 5, 8, 12, 14):
            raise FusionError(
                f"{path}: dist_coeffs 길이 {len(dist)} — OpenCV 규약(4/5/8/12/14) 아님"
            )

    return Intrinsics(
        fx=fx, fy=fy, cx=float(K[0, 2]), cy=float(K[1, 2]),
        width=d.get("image_width"), height=d.get("image_height"),
        dist=dist,
    )


def load_ace2_intrinsics(path: Optional[Path] = None) -> Intrinsics:
    return _load_intrinsics_json(Path(path) if path else ACE2_INTRINSICS, "ACE2")


def load_blaze_intrinsics(path: Optional[Path] = None) -> Intrinsics:
    return _load_intrinsics_json(Path(path) if path else BLAZE_INTRINSICS, "Blaze")


def depth_to_points_mm(depth_mm: np.ndarray, intr: Intrinsics) -> np.ndarray:
    """depth 이미지 → 카메라 좌표계 3D 점 (N,3), 단위 mm. 유효 픽셀만.

    핀홀 역투영: X = (u-cx)·Z/fx, Y = (v-cy)·Z/fy

    ⭐ 7/31 수정: intr에 왜곡계수가 있으면 `undistortPoints`로 **먼저 왜곡을 편** 뒤
       역투영한다. 이전에는 이 단계가 없어 Blaze 108° 초광각의 배럴 왜곡이
       그대로 3D 좌표에 실렸고, 화면 가장자리일수록 어긋났다.
    """
    if depth_mm.ndim != 2:
        raise FusionError(f"depth는 2D여야 함 (shape={depth_mm.shape})")

    z = depth_mm.astype(np.float64)
    valid = np.isfinite(z) & (z >= DEPTH_MIN_MM) & (z <= DEPTH_MAX_MM)
    if not valid.any():
        return np.empty((0, 3), dtype=np.float64)

    vs, us = np.nonzero(valid)
    zs = z[vs, us]

    if _use_dist(intr, "depth_to_points_mm"):
        # undistortPoints(P=None) → 정규화 좌표(x', y')를 돌려준다. 즉 (u-cx)/fx 대응.
        pts = np.stack([us, vs], axis=1).astype(np.float64).reshape(-1, 1, 2)
        norm = cv2.undistortPoints(pts, intr.K, intr.D).reshape(-1, 2)
        xs = norm[:, 0] * zs
        ys = norm[:, 1] * zs
    else:
        xs = (us - intr.cx) * zs / intr.fx
        ys = (vs - intr.cy) * zs / intr.fy
    return np.stack([xs, ys, zs], axis=1)


def transform_points(points: np.ndarray, T: np.ndarray) -> np.ndarray:
    """(N,3) 점을 4×4 변환. 단위는 T와 점이 같아야 함(둘 다 mm)."""
    if points.size == 0:
        return points
    return points @ T[:3, :3].T + T[:3, 3]


def project_points(points_mm: np.ndarray, intr: Intrinsics) -> Tuple[np.ndarray, np.ndarray]:
    """(N,3) 카메라 좌표 점 → 픽셀 (N,2) float + z (N,). 카메라 앞(z>0)만 반환.

    ⭐ 7/31 수정: 왜곡계수가 있으면 `projectPoints`로 **왜곡을 실어** 투영한다.
       실제 카메라가 맺는 상이 왜곡된 상이므로, 겹쳐 보려면 같은 왜곡을 줘야 한다.
    """
    if points_mm.size == 0:
        return np.empty((0, 2)), np.empty((0,))

    z = points_mm[:, 2]
    front = z > 0
    p = points_mm[front]
    z = z[front]
    if z.size == 0:
        return np.empty((0, 2)), np.empty((0,))

    if _use_dist(intr, "project_points"):
        zero = np.zeros(3, dtype=np.float64)
        uv, _ = cv2.projectPoints(
            p.reshape(-1, 1, 3).astype(np.float64), zero, zero, intr.K, intr.D
        )
        return uv.reshape(-1, 2), z

    u = p[:, 0] * intr.fx / z + intr.cx
    v = p[:, 1] * intr.fy / z + intr.cy
    return np.stack([u, v], axis=1), z


def align_depth_to_ace2(
    blaze_depth_mm: np.ndarray,
    ace2_shape: Tuple[int, int],
    *,
    extrinsic: Optional[Extrinsic] = None,
    ace2_intr: Optional[Intrinsics] = None,
    blaze_intr: Optional[Intrinsics] = None,
    dilate: int = 1,
) -> np.ndarray:
    """Blaze depth를 ACE2 픽셀 격자로 정렬한 depth map(mm, float32)을 만든다.

    반환값은 ACE2 RGB와 같은 (H,W)라, 기존 `detect_and_output`에 그대로 넣을 수 있다.
    값 없는 픽셀 = `NO_DEPTH`(0) → `safe_depth_at`이 invalid로 인식.

    Args:
        blaze_depth_mm: Blaze depth (H,W) uint16/float, 단위 mm
        ace2_shape: 정렬 대상 (H, W) — ACE2 **추론에 쓸 이미지**의 크기
        extrinsic:  None이면 config에서 로드
        ace2_intr / blaze_intr: None이면 config에서 로드
        dilate: 투영점 주변 채우기 반경(px). Blaze(848×480)가 ACE2보다 훨씬
                저해상도라 그대로 투영하면 **점묘화처럼 구멍**이 생긴다.
                0이면 끔. 1이면 3×3으로 메움.

    ⚠️ ace2_shape은 반드시 **실제 추론 이미지 크기**와 같아야 한다. intrinsic이
       5MP 기준인데 축소 이미지를 넘기면 조용히 어긋나므로, 크기 불일치 시
       intrinsic을 `scaled()`로 맞춰 넘길 것.
    """
    if extrinsic is None:
        extrinsic = load_extrinsic(strict=False)
    if ace2_intr is None:
        ace2_intr = load_ace2_intrinsics()
    if blaze_intr is None:
        blaze_intr = load_blaze_intrinsics()

    H, W = int(ace2_shape[0]), int(ace2_shape[1])
    if H <= 0 or W <= 0:
        raise FusionError(f"ace2_shape이 올바르지 않음: {ace2_shape}")

    # intrinsic이 5MP 기준인데 목표 격자가 다르면 좌표가 통째로 어긋난다.
    if ace2_intr.width and ace2_intr.height:
        if abs(ace2_intr.width - W) > 2 or abs(ace2_intr.height - H) > 2:
            raise FusionError(
                f"ACE2 intrinsic 해상도({ace2_intr.width}×{ace2_intr.height})와 "
                f"목표 격자({W}×{H})가 다름 — 그대로 쓰면 좌표가 어긋남.\n"
                f"  → ace2_intr.scaled({W}/{ace2_intr.width:.0f}, "
                f"{H}/{ace2_intr.height:.0f}) 로 맞춰서 넘길 것."
            )

    # ① Blaze depth → Blaze 3D (mm)
    pts_blaze = depth_to_points_mm(blaze_depth_mm, blaze_intr)
    if pts_blaze.size == 0:
        return np.zeros((H, W), dtype=np.float32)

    # ② Blaze → ACE2 좌표계.
    #    extrinsic은 T_ace2_to_blaze(ACE2→Blaze)이므로 **역변환**을 쓴다.
    T_blaze_to_ace2 = extrinsic.inverse_mm()
    pts_ace2 = transform_points(pts_blaze, T_blaze_to_ace2)

    # ③ ACE2 intrinsic으로 투영
    uv, z = project_points(pts_ace2, ace2_intr)
    if uv.shape[0] == 0:
        return np.zeros((H, W), dtype=np.float32)

    u = np.rint(uv[:, 0]).astype(np.int64)
    v = np.rint(uv[:, 1]).astype(np.int64)
    inside = (u >= 0) & (u < W) & (v >= 0) & (v < H)
    u, v, z = u[inside], v[inside], z[inside]
    if u.size == 0:
        return np.zeros((H, W), dtype=np.float32)

    # ④ z-buffer: 같은 픽셀에 여럿 오면 가장 가까운 것만.
    #    가림 처리를 안 하면 뒤 부품 depth가 앞을 덮어써 로봇이 허공을 집는다.
    #    구현: z 내림차순 정렬 후 대입 → 마지막(=가장 가까운)이 남음.
    order = np.argsort(-z, kind="stable")
    u, v, z = u[order], v[order], z[order]

    aligned = np.zeros((H, W), dtype=np.float32)
    aligned[v, u] = z

    # ⑤ 구멍 메우기 — Blaze가 저해상도라 ACE2 격자에선 점이 흩뿌려진다.
    if dilate > 0:
        aligned = _fill_holes_nearest(aligned, radius=dilate)

    return aligned


def _fill_holes_nearest(depth: np.ndarray, radius: int) -> np.ndarray:
    """빈 픽셀을 주변 유효 depth 중 **가장 가까운(작은) 값**으로 메운다.

    max가 아니라 min을 쓰는 이유: 경계에서 배경(먼 값)이 부품 위로 번지면
    부품 z가 실제보다 멀게 나와 로봇이 아래를 찌른다. 가까운 값이 안전측.
    (구멍이 아닌 원래 값은 절대 덮어쓰지 않는다.)
    """
    if radius <= 0:
        return depth

    out = depth.copy()
    holes = depth == NO_DEPTH
    if not holes.any():
        return out

    # 유효값만 담고, 빈 곳은 +inf로 둔 뒤 창 최소값을 취한다.
    big = np.full_like(depth, np.inf, dtype=np.float32)
    valid = depth > NO_DEPTH
    big[valid] = depth[valid]

    H, W = depth.shape
    best = np.full_like(big, np.inf)
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            ys0, ys1 = max(0, dy), min(H, H + dy)
            xs0, xs1 = max(0, dx), min(W, W + dx)
            yd0, yd1 = max(0, -dy), min(H, H - dy)
            xd0, xd1 = max(0, -dx), min(W, W - dx)
            np.minimum(best[yd0:yd1, xd0:xd1], big[ys0:ys1, xs0:xs1],
                       out=best[yd0:yd1, xd0:xd1])

    filled = np.isfinite(best) & holes
    out[filled] = best[filled]
    return out


def coverage_report(aligned: np.ndarray) -> str:
    """정렬 결과가 쓸 만한지 눈으로 판단하는 요약.

    현장에서 "정합이 된 건가?"를 즉시 가르기 위한 것 — 커버리지가 낮으면
    extrinsic이 틀렸거나 두 카메라가 다른 곳을 보고 있다는 신호다.
    """
    total = aligned.size
    valid = int(np.count_nonzero(aligned > NO_DEPTH))
    pct = 100.0 * valid / total if total else 0.0
    lines = [
        f"정렬 depth 커버리지: {valid:,}/{total:,} px ({pct:.1f}%)",
    ]
    if valid:
        z = aligned[aligned > NO_DEPTH]
        lines.append(
            f"  z 범위: {z.min():.0f} ~ {z.max():.0f} mm (중앙 {np.median(z):.0f} mm)"
        )
    if pct < 1.0:
        lines.append(
            "  ⚠️ 커버리지 1% 미만 — extrinsic이 틀렸거나 두 카메라 화각이 거의 안 겹침."
        )
    elif pct < 10.0:
        lines.append(
            "  ⚠️ 커버리지 낮음 — Blaze 화각이 ACE2보다 넓어 일부만 겹치는 건 정상이나, "
            "부품 영역이 비면 dilate를 키우거나 카메라 간 거리를 재확인."
        )
    return "\n".join(lines)


__all__ = [
    "FusionError",
    "Intrinsics",
    "NO_DEPTH",
    "align_depth_to_ace2",
    "coverage_report",
    "depth_to_points_mm",
    "load_ace2_intrinsics",
    "load_blaze_intrinsics",
    "project_points",
    "transform_points",
]
