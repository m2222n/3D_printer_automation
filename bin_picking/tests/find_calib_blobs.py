"""
hand-eye 3점법용 — depth 한 장에서 "바닥 위에 놓인 작은 물체" 들의 중심을 찾아 카메라 3D 좌표(mm)로 낸다
================================================================================================

🎯 왜 있는가 (9/10 재택)
  카메라를 팔에 달아도 **촬영 자세(P_capture)를 하나로 고정하면 카메라는 사실상 고정**이다
  ⇒ 8/8 검증된 3점법(`work_coord_3point.py`)이 그대로 쓰인다. 체커보드·scipy·자세 15개가 필요 없다.
  3점법의 🅑 단계 = "카메라로 같은 점 보기" 인데, **테이프 십자는 depth 에 안 보인다.**
  ⇒ 대신 **작은 블록(부품) 3~4개**를 바닥에 놓고, 그 **윗면 중심**을 카메라(이 도구)와 로봇 TCP(손으로 대기) 양쪽에서 잰다.

입력  = Blaze depth .npy (raw uint16 · 8/28 grab 4줄 또는 run_live_pick --capture 산출물)
출력  = 블롭별 (u, v) 픽셀 중심 · 윗면 depth 중앙값 · 카메라 3D (x, y, z) mm  + JSON

원리
  ① raw → mm (`depth_units.to_mm` · 단위 사고 방어 8/5)
  ② 바닥 평면 깊이 = 중앙 ROI 유효 픽셀의 중앙값(빈·테이블이 화면 대부분)
  ③ 바닥보다 `--min-height` mm 이상 가까운 픽셀 = 물체 → 연결 성분(cv2)
  ④ 성분마다 면적 필터 → 중심 픽셀 · 윗면 depth(성분 안 최소 20% 분위) → `pixel_to_camera_3d`(fx 309.3 · fy 310.1 실측 intrinsic)

🚨 한계(정직하게)
  - 블록이 바닥과 8mm 이상 높이 차가 나야 한다(Blaze 노이즈 ±3~5mm).
  - 블록 윗면이 평평해야 "중심 = TCP 를 댄 점" 이 성립한다. 부품처럼 울퉁불퉁하면 오차가 커진다 ⇒ **각진 블록**을 쓴다.
  - 결과 좌표계 = **카메라 좌표(mm)**. 로봇 좌표로 바꾸는 것은 `work_coord_3point.solve_rigid_transform` 몫.

사용
  python bin_picking/tests/find_calib_blobs.py --depth shot.npy [--intr bin_picking/config/blaze_intrinsics.json] [--out blobs.json]
  python bin_picking/tests/find_calib_blobs.py --self-test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from bin_picking.src.acquisition.depth_units import to_mm  # noqa: E402
from bin_picking.src.pipeline.depth_track_to_6elements import pixel_to_camera_3d  # noqa: E402

DEFAULT_INTR = REPO / "bin_picking" / "config" / "blaze_intrinsics.json"


def find_blobs(depth_mm: np.ndarray, intr: dict, *, min_height_mm: float = 8.0,
               min_area_px: int = 40, max_area_px: int = 20000, roi_frac: float = 0.8) -> dict:
    import cv2

    h, w = depth_mm.shape
    valid = (depth_mm > 0) & np.isfinite(depth_mm)
    # ② 바닥 깊이 — 중앙 ROI 에서 (가장자리는 빈 벽·케이블이 섞인다)
    y0, y1 = int(h * (1 - roi_frac) / 2), int(h * (1 + roi_frac) / 2)
    x0, x1 = int(w * (1 - roi_frac) / 2), int(w * (1 + roi_frac) / 2)
    roi = depth_mm[y0:y1, x0:x1]
    roi_valid = roi[(roi > 0) & np.isfinite(roi)]
    if roi_valid.size < 100:
        raise RuntimeError(f"유효 depth 가 {roi_valid.size}픽셀 — 카메라가 바닥을 못 본다(전원·방화벽·거리)")
    floor = float(np.median(roi_valid))

    # ③ 바닥보다 가까운(=위에 있는) 픽셀
    above = valid & (depth_mm < floor - min_height_mm)
    mask = np.zeros((h, w), np.uint8)
    mask[y0:y1, x0:x1] = above[y0:y1, x0:x1].astype(np.uint8)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)

    blobs = []
    for i in range(1, n):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area_px or area > max_area_px:
            continue
        sel = labels == i
        d = depth_mm[sel]
        top = float(np.percentile(d, 20))            # 윗면 = 가까운 쪽 20% 분위(가장자리 기울기 배제)
        cu, cv_ = float(cents[i][0]), float(cents[i][1])
        x, y, z = pixel_to_camera_3d(cu, cv_, top, intr)
        blobs.append({
            "u": round(cu, 1), "v": round(cv_, 1), "area_px": area,
            "top_depth_mm": round(top, 1), "height_mm": round(floor - top, 1),
            "cam_xyz_mm": [round(x, 1), round(y, 1), round(z, 1)],
            "bbox": [int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                     int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])],
        })
    # 왼쪽 위 → 오른쪽 아래 순으로 (사람이 로봇으로 찍는 순서와 맞추기 쉽게)
    blobs.sort(key=lambda b: (round(b["v"] / 60), b["u"]))
    for k, b in enumerate(blobs, 1):
        b["id"] = k
    return {"floor_depth_mm": round(floor, 1), "min_height_mm": min_height_mm, "n_blobs": len(blobs), "blobs": blobs}


def _self_test() -> int:
    """합성 장면: 450mm 바닥 + 블록 4개(높이 20·25·30·15mm) → 4개 검출 · 3D 가 기대와 2mm 안."""
    import cv2  # noqa: F401  — 없으면 여기서 크게 실패
    intr = json.loads(DEFAULT_INTR.read_text(encoding="utf-8"))
    h, w = 480, 848
    depth = np.full((h, w), 450.0, np.float32)
    rng = np.random.default_rng(0)
    depth += rng.normal(0, 2.0, size=depth.shape)                  # Blaze 노이즈급
    blocks = [((200, 150), 20), ((600, 150), 25), ((200, 330), 30), ((600, 330), 15)]   # (u,v) 중심, 높이
    for (cu, cv_), hgt in blocks:
        depth[cv_ - 12:cv_ + 12, cu - 12:cu + 12] = 450.0 - hgt
    depth[0:5, :] = 0                                              # 무효 띠(실제 화면에 있다)
    res = find_blobs(depth, intr)
    fails = 0
    def check(name, cond, detail=""):
        nonlocal fails
        print(f"  {'🟢' if cond else '🔴'} {name}" + (f"  — {detail}" if detail and not cond else ""))
        if not cond:
            fails += 1
    check("바닥 깊이 450±3", abs(res["floor_depth_mm"] - 450) < 3, str(res["floor_depth_mm"]))
    check("블롭 4개", res["n_blobs"] == 4, str(res["n_blobs"]))
    for b in res["blobs"]:
        exp = min(blocks, key=lambda bl: abs(bl[0][0] - b["u"]) + abs(bl[0][1] - b["v"]))
        (cu, cv_), hgt = exp
        ex, ey, ez = pixel_to_camera_3d(cu, cv_, 450 - hgt, intr)
        err = np.linalg.norm(np.array(b["cam_xyz_mm"]) - np.array([ex, ey, ez]))
        check(f"블롭 {b['id']} 3D 오차 < 3mm (높이 {hgt})", err < 3.0, f"{err:.1f}mm")
    # 🧪 그물: min_height 를 40 으로 올리면 하나도 안 잡혀야 한다(임계가 실제로 작동)
    res2 = find_blobs(depth, intr, min_height_mm=40)
    check("🧪 그물: min_height 40 → 0개", res2["n_blobs"] == 0, str(res2["n_blobs"]))
    print(f"  {'✅ 통과' if fails == 0 else '🔴 실패 ' + str(fails)}")
    return 0 if fails == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="depth 한 장에서 캘리브 블록 중심의 카메라 3D 좌표(mm)")
    ap.add_argument("--depth", type=Path, help="Blaze depth .npy (raw uint16 또는 mm)")
    ap.add_argument("--intr", type=Path, default=DEFAULT_INTR)
    ap.add_argument("--out", type=Path, default=None, help="결과 JSON 경로(기본 = depth 옆 *.blobs.json)")
    ap.add_argument("--min-height", type=float, default=8.0, help="바닥보다 이만큼(mm) 이상 높은 것만 물체로 본다")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return _self_test()
    if not a.depth:
        ap.error("--depth 또는 --self-test")
    raw = np.load(a.depth)
    depth_mm = to_mm(raw)                                          # 🚨 단위는 여기서만 정한다
    intr = json.loads(Path(a.intr).read_text(encoding="utf-8"))
    res = find_blobs(depth_mm, intr, min_height_mm=a.min_height)
    res["source"] = str(a.depth)
    print(f"바닥 깊이 {res['floor_depth_mm']}mm · 블롭 {res['n_blobs']}개")
    print(f"{'id':>3} {'u':>7} {'v':>7} {'area':>6} {'height':>7} {'cam x':>8} {'cam y':>8} {'cam z':>8}")
    for b in res["blobs"]:
        x, y, z = b["cam_xyz_mm"]
        print(f"{b['id']:>3} {b['u']:>7.1f} {b['v']:>7.1f} {b['area_px']:>6} {b['height_mm']:>7.1f} {x:>8.1f} {y:>8.1f} {z:>8.1f}")
    out = a.out or a.depth.with_suffix(".blobs.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out}")
    print("다음 = 같은 블록 윗면 중심에 로봇 TCP 를 대고 getCurrentPose 를 적는다(id 순서대로) → work_coord_3point.solve_rigid_transform(cam, rob)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
