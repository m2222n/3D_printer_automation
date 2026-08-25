"""RGB(ACE2) → depth(Blaze) 격자 정합 — RGB 융합 학습 입력을 만든다.

🎯 목적 = D-2. **depth 픽셀마다 "그 자리의 색"을 붙인다.**
   결과 = (H,W,3) uint8, depth와 **같은 격자**(848×480).

⭐⭐ 왜 depth 격자로 가져오나 (반대가 아니라)
   `rgbd_fusion.align_depth_to_ace2()`는 **depth를 ACE2 격자로** 올린다(7/31 오버레이용).
   학습에는 그 반대가 맞다:
     - 라벨이 **depth 해상도 기준**으로 그려져 있다(848×480 → PNG 1696×960)
     - 모델 입력이 depth 파생 320×576이다
     - 🚨 RGB 격자(2448×2048)로 가면 **라벨을 다시 만들어야 한다**
   ⇒ 📌 **depth 격자를 정본으로 두고 색만 끌어온다.** 라벨·모델 경로가 그대로 산다.

원리 (7/28 extrinsic + 양쪽 intrinsic)
   ① depth 픽셀 (u,v,z) → Blaze 카메라 3D 좌표    (역투영, 왜곡 보정 포함)
   ② Blaze 3D → ACE2 3D                          (T_ace2_to_blaze 의 역변환)
   ③ ACE2 3D → ACE2 픽셀                          (투영, 왜곡 실음)
   ④ 그 픽셀의 RGB 를 depth 격자 자리에 기록

🚨 알려진 한계 — 정직하게 적는다
   - **depth 가 없는 픽셀은 색도 없다**(z 를 모르면 어디를 보는지 계산 불가).
     8/24 데이터는 크롭 안 무효 픽셀이 94.7% 라 **색이 붙는 곳은 부품 표면뿐**이다.
     ⭐ 그런데 그게 우리가 원하는 것이다 — 배경색은 학습에 해롭다(8/18 배경재 교훈).
   - **가림(occlusion) 처리 없음.** 두 카메라 시점이 44.7mm 떨어져 있어 원리상
     한쪽에서 가려진 표면에 엉뚱한 색이 붙을 수 있다. 거리 450mm·시차 44.7mm 라
     영향은 작지만 **0은 아니다** ⇒ [미검증]
   - 🚨 **7/28 extrinsic 산포가 5.29mm** 다. 450mm 거리에서 각도 오차로 환산하면
     픽셀 수 개 수준이고, 부품(20~110mm)에 비해 작지만 **경계에서는 색이 밀릴 수 있다.**

사용법:
    python -m bin_picking.src.acquisition.rgb_to_depth_align \
        --depth-dir /data/jtm/dual_capture_0824 --glob "shot_*_sA.npy" \
        --out-dir /data/jtm/dual_capture_0824/rgb_aligned
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from bin_picking.src.acquisition.extrinsic_io import load_extrinsic  # noqa: E402
from bin_picking.src.acquisition.rgbd_fusion import (  # noqa: E402
    Intrinsics,
    depth_to_points_mm,
    load_ace2_intrinsics,
    load_blaze_intrinsics,
    project_points,
    transform_points,
)

# 8/24 촬영 데이터 규약 — raw uint16 → mm
#   real_uint16_max_depth_m = 10.0 이므로  raw 65535 = 10m = 10000mm
#   ⇒ 1 raw = 10000/65535 = 0.152590 mm
# ⭐ 실측 검산(8/25) = shot_001 nonzero 중앙값 raw 2959 × 0.15259 = **451.5mm**
#    (8/24 촬영 DIST 428~473mm 대역과 일치)
# 🚨 처음에 여기에 `* 1000.0` 을 붙여 값이 1000배가 되어 유효 픽셀이 0이 되었다.
#    주석에는 검산을 써두고 코드엔 다른 값을 넣은 것 — 8/21 *"측정한 값과 도는 값이
#    달랐다"* 와 같은 형태다. **상수는 넣고 나서 한 장으로 재본다.**
DEPTH_SCALE_MM = 10000.0 / 65535.0  # = 0.152590 mm per raw unit

# 색을 붙일 depth 범위 — 학습 전처리와 같은 대역(0.40~0.60m)
BAND_MIN_MM, BAND_MAX_MM = 400.0, 600.0


class AlignError(RuntimeError):
    pass


def align_rgb_to_depth(
    depth_mm: np.ndarray,
    rgb: np.ndarray,
    *,
    T_blaze_to_ace2_mm: np.ndarray,
    blaze_intr: Intrinsics,
    ace2_intr: Intrinsics,
    band: tuple[float, float] = (BAND_MIN_MM, BAND_MAX_MM),
) -> tuple[np.ndarray, dict]:
    """depth 격자 위에 RGB를 실어 (H,W,3) uint8 로 돌려준다.

    Returns: (rgb_on_depth, stats)
    """
    if depth_mm.ndim != 2:
        raise AlignError(f"depth는 2D여야 한다: {depth_mm.shape}")
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise AlignError(f"rgb는 (H,W,3)이어야 한다: {rgb.shape}")

    H, W = depth_mm.shape
    out = np.zeros((H, W, 3), dtype=np.uint8)

    z = depth_mm.astype(np.float64)
    valid = np.isfinite(z) & (z >= band[0]) & (z <= band[1])
    n_valid = int(valid.sum())
    if n_valid == 0:
        return out, {"valid_px": 0, "mapped_px": 0, "mapped_ratio": 0.0}

    # ① depth 픽셀 → Blaze 3D — 대역 밖은 0으로 눌러 제외시킨다
    z_masked = np.where(valid, z, 0.0)
    pts_blaze = depth_to_points_mm(z_masked, blaze_intr)      # (N,3), 유효만
    vs, us = np.nonzero(valid)                                # 같은 순서(np.nonzero)

    if pts_blaze.shape[0] != vs.size:
        # depth_to_points_mm 의 유효 판정이 우리 band 와 다를 수 있다 ⇒ 재계산
        raise AlignError(
            f"유효 픽셀 수 불일치: 역투영 {pts_blaze.shape[0]} vs 마스크 {vs.size}. "
            "DEPTH_MIN_MM/MAX_MM 와 band 범위를 확인할 것"
        )

    # ② Blaze 3D → ACE2 3D
    # ⭐ 역변환은 `Extrinsic.inverse_mm()`이 이미 정확히 제공한다(R^T 방식).
    #    직접 만들지 않는다 — 8/24 교훈("성공한 전례 코드를 먼저 연다").
    pts_ace2 = transform_points(pts_blaze, T_blaze_to_ace2_mm)

    # ③ ACE2 3D → ACE2 픽셀
    uv, _zc = project_points(pts_ace2, ace2_intr)
    if uv.shape[0] != pts_ace2.shape[0]:
        # project_points 는 z>0 만 돌려준다 — 개수가 줄면 대응이 깨지므로 직접 계산
        raise AlignError(
            "투영에서 점이 탈락했다(z<=0). 좌표계 방향(extrinsic 역변환)을 확인할 것"
        )

    # ④ RGB 샘플링 (nearest)
    Hr, Wr = rgb.shape[:2]
    uu = np.rint(uv[:, 0]).astype(np.int64)
    vv = np.rint(uv[:, 1]).astype(np.int64)
    inside = (uu >= 0) & (uu < Wr) & (vv >= 0) & (vv < Hr)
    out[vs[inside], us[inside]] = rgb[vv[inside], uu[inside]]

    stats = {
        "valid_px": n_valid,
        "mapped_px": int(inside.sum()),
        "mapped_ratio": float(inside.sum()) / max(n_valid, 1),
        "uv_range": [float(uv[:, 0].min()), float(uv[:, 0].max()),
                     float(uv[:, 1].min()), float(uv[:, 1].max())],
    }
    return out, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth-dir", required=True)
    ap.add_argument("--glob", default="shot_*.npy")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--rgb-suffix", default="_rgb.png")
    ap.add_argument("--min-mapped-ratio", type=float, default=0.80,
                    help="이 비율 미만이면 실패로 본다(정합이 어긋난 신호)")
    args = ap.parse_args()

    import cv2

    depth_dir = Path(args.depth_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ⭐ strict=False — 7/28 산포 5.29mm 가 경고 대상이라 strict면 로딩이 막힌다.
    #    경고는 받아서 **출력하고 계속 간다**(품질을 알고 쓰는 것과 모르고 쓰는 것은 다르다).
    ex = load_extrinsic(strict=False)
    T_inv = ex.inverse_mm()        # Blaze → ACE2 (mm)
    for w in ex.quality_warnings():
        print(f"  {w}")

    blaze_intr = load_blaze_intrinsics()
    ace2_intr = load_ace2_intrinsics()

    files = sorted(depth_dir.glob(args.glob))
    if not files:
        raise AlignError(f"{args.glob} 를 못 찾음: {depth_dir}")

    print(f"대상 {len(files)}장 · baseline {ex.baseline_mm:.1f}mm · 산포 {ex.spread_mm:.2f}mm")
    ok = bad = 0
    for i, f in enumerate(files, 1):
        rgb_path = f.with_name(f.stem + args.rgb_suffix)
        if not rgb_path.exists():
            print(f"  🔴 [{i}/{len(files)}] {f.name}: RGB 없음 ({rgb_path.name})")
            bad += 1
            continue
        depth = np.load(f).astype(np.float32) * DEPTH_SCALE_MM
        bgr = cv2.imread(str(rgb_path))
        if bgr is None:
            print(f"  🔴 [{i}/{len(files)}] {f.name}: RGB 읽기 실패")
            bad += 1
            continue
        rgb = bgr[:, :, ::-1]                      # BGR → RGB
        aligned, st = align_rgb_to_depth(
            depth, rgb, T_blaze_to_ace2_mm=T_inv,
            blaze_intr=blaze_intr, ace2_intr=ace2_intr)
        mark = "🟢" if st["mapped_ratio"] >= args.min_mapped_ratio else "🔴"
        if st["mapped_ratio"] < args.min_mapped_ratio:
            bad += 1
        else:
            ok += 1
        np.save(out_dir / (f.stem + "_rgbaligned.npy"), aligned)
        if i <= 3 or i % 15 == 0 or mark == "🔴":
            print(f"  {mark} [{i}/{len(files)}] {f.name}  유효 {st['valid_px']:6d}px "
                  f"→ 매핑 {st['mapped_px']:6d}px ({st['mapped_ratio']*100:.1f}%)")

    print(f"\n{'='*58}")
    print(f"  성공 {ok} / 실패 {bad}  → {out_dir}")
    print(f"  🚨 매핑률이 낮으면 extrinsic 방향(역변환)·단위(m/mm)를 먼저 본다")
    print(f"{'='*58}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
