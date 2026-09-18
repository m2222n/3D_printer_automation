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
  ① raw → mm (`depth_units.to_mm` · 단위 사고 방어 8/5 · 🚨 (배열, 설명) 튜플을 돌려준다)
  ② 🆕 **근접 컷** — `--near-cut` (기본 300mm) 보다 가까운 픽셀은 무효. 팔에 달린 카메라 화면에는 **그리퍼·브라켓이 들어온다**
     (9/16 실물 = 113~163mm 픽셀이 화면의 16% · 좌우 세로 띠). 이걸 안 걷어내면 바닥 중앙값이 180mm 로 무너진다.
  ③ 바닥 평면 깊이 = 중앙 ROI 유효 픽셀의 중앙값 … 단 🆕 **바닥이 depth 에 안 보이면**(골판지가 850nm 을 흡수 → 무효 · 9/16 ROI 유효 3.6%)
     중앙값은 바닥이 아니라 블록 윗면이 된다 ⇒ ROI 유효율 < 20% 면 **"유효 픽셀 = 물체" 모드**로 전환(바닥 높이 판정을 쓰지 않는다)
  ④ 바닥이 보이면: 바닥보다 `--min-height` mm 이상 가까운 픽셀 = 물체 → 연결 성분(cv2)
  ⑤ 성분마다 면적 필터 → 중심 픽셀 · 윗면 depth(성분 안 가까운 쪽 20% 분위) → `pixel_to_camera_3d`(fx 309.3 · fy 310.1 실측 intrinsic)

🚨 한계(정직하게)
  - 바닥이 보일 때 블록은 바닥과 8mm 이상 높이 차가 나야 한다(Blaze 노이즈 ±3~5mm).
  - 바닥이 안 보일 때(골판지) 블록끼리 **화면에서 30px(≈5cm) 이상** 떨어져야 한다 — 붙으면 한 블롭으로 합쳐진다.
  - 블록 윗면이 평평해야 "중심 = TCP 를 댄 점" 이 성립한다. 부품처럼 울퉁불퉁하면 오차가 커진다 ⇒ **각진 블록**을 쓴다.
  - 블록을 화면 좌우 띠(그리퍼가 보이는 자리)에 놓으면 가려진다 ⇒ 블롭 표의 u 가 100 미만·750 초과면 배치를 안쪽으로.
  - 결과 좌표계 = **카메라 좌표(mm)**. 로봇 좌표로 바꾸는 것은 `work_coord_3point.solve_rigid_transform` / `cam_to_base build` 몫.

사용
  python bin_picking/tests/find_calib_blobs.py --depth shot.npy [--intr bin_picking/config/blaze_intrinsics.json] [--out blobs.json]
  python bin_picking/tests/find_calib_blobs.py --depth shot.npy --floor-mm 503      # 바닥 깊이를 사람이 지정(자동 판정이 못 미더울 때)
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
from bin_picking.src.utils.console_utf8 import enable_utf8_console  # noqa: E402  (IPC cp949 방어 · 8/28)
from bin_picking.src.acquisition.depth_units import to_mm  # noqa: E402
from bin_picking.src.pipeline.depth_track_to_6elements import pixel_to_camera_3d  # noqa: E402

DEFAULT_INTR = REPO / "bin_picking" / "config" / "blaze_intrinsics.json"

NEAR_CUT_MM = 300.0            # 이보다 가까운 것 = 팔에 달린 그리퍼·브라켓(9/16 실물 113~163mm). 렌즈↔바닥 450~500 이라 물체가 여기 올 수 없다
FAR_CUT_MM = 1500.0            # Blaze ShortRange 상한 부근 · 이 밖은 노이즈
FLOOR_VISIBLE_MIN_FRAC = 0.20  # ROI 유효율이 이보다 낮으면 바닥이 안 보이는 것(골판지 · 9/16 3.6%). 8/18 학습 조건 all_valid 3~9% 도 이 아래
NEAR_WARN_PCT = 5.0            # 화면의 이 % 이상이 근접 컷에 걸리면 경고(정상이지만 블록 배치가 그 띠를 피해야 한다)


def find_blobs(depth_mm: np.ndarray, intr: dict, *, min_height_mm: float = 8.0,
               min_area_px: int = 40, max_area_px: int = 20000, roi_frac: float = 0.8,
               near_cut_mm: float = NEAR_CUT_MM, far_cut_mm: float = FAR_CUT_MM,
               floor_mm: float | None = None) -> dict:
    import cv2

    depth_mm = np.asarray(depth_mm)
    if depth_mm.ndim != 2:
        raise RuntimeError(f"depth 가 2차원이 아니다 {depth_mm.shape}")
    h, w = depth_mm.shape
    if h / w > 0.75:   # Blaze Range 는 480×848(0.57). Range 만 켜면 Intensity 가 세로로 붙어 (960,848)=1.13 이 된다(9/16 함정)
        raise RuntimeError(f"depth 모양 {depth_mm.shape} — (480,848) 이 아니다. Intensity 동봉(960,848) 의심 → grab 에서 Intensity off + Range on 두 동작")
    finite = np.isfinite(depth_mm) & (depth_mm > 0)
    near = finite & (depth_mm < near_cut_mm)                         # ② 그리퍼·브라켓
    valid = finite & (depth_mm >= near_cut_mm) & (depth_mm <= far_cut_mm)
    near_pct = 100.0 * float(near.mean())

    # ③ 바닥 깊이 — 중앙 ROI 에서 (가장자리는 빈 벽·케이블·그리퍼가 섞인다)
    y0, y1 = int(h * (1 - roi_frac) / 2), int(h * (1 + roi_frac) / 2)
    x0, x1 = int(w * (1 - roi_frac) / 2), int(w * (1 + roi_frac) / 2)
    roi_valid = valid[y0:y1, x0:x1]
    roi_vals = depth_mm[y0:y1, x0:x1][roi_valid]
    roi_valid_pct = 100.0 * float(roi_valid.mean())
    if roi_vals.size < 100:
        raise RuntimeError(
            f"유효 depth({near_cut_mm:.0f}~{far_cut_mm:.0f}mm) 가 ROI 에 {roi_vals.size}픽셀 — 카메라가 바닥을 못 본다"
            f"(전원·방화벽·거리 · 근접 픽셀 {near_pct:.1f}%)"
        )
    warnings: list[str] = []
    if floor_mm is not None:
        floor, floor_visible, floor_how = float(floor_mm), True, "사람 지정(--floor-mm)"
    elif roi_valid_pct >= 100.0 * FLOOR_VISIBLE_MIN_FRAC:
        floor, floor_visible, floor_how = float(np.median(roi_vals)), True, f"ROI 유효 {roi_valid_pct:.1f}% 중앙값"
    else:
        # 바닥이 무효(골판지 흡수) — 중앙값은 블록 윗면이라 바닥이 아니다. 가장 깊은 쪽(p90)을 참고값으로만 적고 높이 판정은 쓰지 않는다
        floor, floor_visible, floor_how = float(np.percentile(roi_vals, 90)), False, f"ROI 유효 {roi_valid_pct:.1f}% <{100 * FLOOR_VISIBLE_MIN_FRAC:.0f}% → 바닥 안 보임 · p90 참고값"
        warnings.append(
            f"⚠️ 바닥이 depth 에 거의 없다(ROI 유효 {roi_valid_pct:.1f}% · 골판지 IR 흡수) → 유효 픽셀 연결 성분을 그대로 물체로 본다. "
            "height 는 참고값 · 블록끼리 화면에서 30px 이상 떨어져야 한다(붙으면 한 블롭)"
        )
    near_bands: list[list[int]] = []
    if near_pct >= NEAR_WARN_PCT:
        col_frac = near.mean(axis=0)                                   # 열마다 근접 픽셀 비율
        hot = np.nonzero(col_frac > 0.3)[0]
        if hot.size:
            start = prev = int(hot[0])
            for c in hot[1:]:
                if int(c) != prev + 1:
                    near_bands.append([start, prev]); start = int(c)
                prev = int(c)
            near_bands.append([start, prev])
        bands_txt = " · ".join(f"u {a}~{b}" for a, b in near_bands) or "띠 아님(산발)"
        warnings.append(
            f"🚨 화면의 {near_pct:.1f}% 가 {near_cut_mm:.0f}mm 안(그리퍼·브라켓 · {bands_txt}) — 무효 처리했다. "
            "9/16 실물처럼 좌우 띠면 정상 · 블록이 그 띠에 걸치면 가려진다"
        )

    # ④ 물체 픽셀
    above = valid & (depth_mm < floor - min_height_mm) if floor_visible else valid
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
    return {
        "floor_depth_mm": round(floor, 1), "floor_visible": floor_visible, "floor_how": floor_how,
        "roi_valid_pct": round(roi_valid_pct, 1), "near_cut_mm": near_cut_mm, "near_pct": round(near_pct, 1),
        "near_bands_u": near_bands,
        "min_height_mm": min_height_mm, "n_blobs": len(blobs), "blobs": blobs, "warnings": warnings,
    }


def _self_test() -> int:
    """합성 장면: 450mm 바닥 + 블록 4개(높이 20·25·30·15mm) → 4개 검출 · 3D 가 기대와 2mm 안.
    + 🆕 raw uint16 입력(to_mm 튜플) · 그리퍼 좌우 띠(145mm) · 바닥 무효(골판지) 세 조건에서도 같은 4개."""
    import cv2  # noqa: F401  — 없으면 여기서 크게 실패
    intr = json.loads(DEFAULT_INTR.read_text(encoding="utf-8"))
    h, w = 480, 848
    rng = np.random.default_rng(0)
    blocks = [((200, 150), 20), ((600, 150), 25), ((200, 330), 30), ((600, 330), 15)]   # (u,v) 중심, 높이

    def scene(floor_valid: bool = True) -> np.ndarray:
        depth = np.full((h, w), 450.0, np.float32)
        depth += rng.normal(0, 2.0, size=depth.shape)                  # Blaze 노이즈급
        if not floor_valid:
            depth[:] = 0.0                                             # 골판지 = 바닥 무효(9/16 ROI 유효 3.6%)
        for (cu, cv_), hgt in blocks:
            depth[cv_ - 12:cv_ + 12, cu - 12:cu + 12] = 450.0 - hgt + rng.normal(0, 1.0, size=(24, 24))
        depth[0:5, :] = 0                                              # 무효 띠(실제 화면에 있다)
        return depth

    fails = 0

    def check(name, cond, detail=""):
        nonlocal fails
        print(f"  {'🟢' if cond else '🔴'} {name}" + (f"  — {detail}" if detail and not cond else ""))
        if not cond:
            fails += 1

    def check_blobs(tag, res, tol=3.0):
        check(f"{tag} 블롭 4개", res["n_blobs"] == 4, str(res["n_blobs"]))
        for b in res["blobs"]:
            exp = min(blocks, key=lambda bl: abs(bl[0][0] - b["u"]) + abs(bl[0][1] - b["v"]))
            (cu, cv_), hgt = exp
            ex, ey, ez = pixel_to_camera_3d(cu, cv_, 450 - hgt, intr)
            err = np.linalg.norm(np.array(b["cam_xyz_mm"]) - np.array([ex, ey, ez]))
            check(f"{tag} 블롭 {b['id']} 3D 오차 < {tol:.0f}mm (높이 {hgt})", err < tol, f"{err:.1f}mm")

    print("① 기본(바닥 보임 · float mm)")
    depth = scene()
    res = find_blobs(depth, intr)
    check("바닥 깊이 450±3", abs(res["floor_depth_mm"] - 450) < 3, str(res["floor_depth_mm"]))
    check("floor_visible", res["floor_visible"] is True)
    check_blobs("①", res)

    print("② raw uint16 입력 → to_mm 튜플 언패킹(9/16 실물 npy 에서 크래시 났던 경로)")
    raw = np.round(depth / 1000.0 / 10.0 * 65535.0).astype(np.uint16)
    depth2, unit_msg = to_mm(raw, verbose=False)
    check("to_mm 가 (배열, 설명) 을 준다", isinstance(depth2, np.ndarray) and isinstance(unit_msg, str))
    res2 = find_blobs(depth2, intr)
    check_blobs("②", res2, tol=3.5)                                    # raw 양자화 0.15mm + 노이즈

    print("③ 그리퍼·브라켓 좌우 띠 145mm(9/16 실물 16%) → 근접 컷으로 무효 · 바닥·블롭 불변")
    depth3 = scene()
    depth3[:, :100] = 145.0
    depth3[:, 640:] = 145.0
    res3 = find_blobs(depth3, intr)
    check("근접 픽셀 %가 기록됨(>20%)", res3["near_pct"] > 20, str(res3["near_pct"]))
    check("바닥 깊이 450±3 유지(145mm 무리에 안 끌림)", abs(res3["floor_depth_mm"] - 450) < 3, str(res3["floor_depth_mm"]))
    check("경고에 '그리퍼' 문구", any("그리퍼" in s for s in res3["warnings"]), str(res3["warnings"]))
    check("근접 띠가 두 개(좌·우)로 보고됨", len(res3["near_bands_u"]) == 2, str(res3["near_bands_u"]))
    check_blobs("③", res3)
    # 🧪 그물 = 9/16 실물 조건 그대로(바닥 무효 + 좌우 띠): near_cut 을 끄면 띠가 "유효 바닥" 으로 잡혀 바닥 145mm 로 무너져야 한다
    depth3b = scene(floor_valid=False)
    depth3b[:, :100] = 145.0
    depth3b[:, 640:] = 145.0
    bad = find_blobs(depth3b, intr, near_cut_mm=0.0)
    check("🧪 그물: near_cut 0 + 바닥 무효 → 바닥이 145 로 무너진다(컷이 실제로 작동)",
          bad["floor_visible"] is True and abs(bad["floor_depth_mm"] - 145) < 5, f"{bad['floor_depth_mm']} visible={bad['floor_visible']}")
    good = find_blobs(depth3b, intr)
    check("같은 장면에 컷 켜면 바닥 무효 모드 · 4개", good["floor_visible"] is False and good["n_blobs"] == 4, str(good["n_blobs"]))

    print("④ 바닥 무효(골판지 흡수 · ROI 유효 <20%) → '유효 픽셀 = 물체' 모드")
    depth4 = scene(floor_valid=False)
    res4 = find_blobs(depth4, intr)
    check("floor_visible False", res4["floor_visible"] is False)
    check("경고에 '바닥' 문구", any("바닥" in s for s in res4["warnings"]), str(res4["warnings"]))
    check_blobs("④", res4)
    check("🧪 그물: 바닥 무효인데 --floor-mm 450 을 억지로 주면 높이 판정으로 돌아가도 4개(윗면 20% 분위가 살아 있다)",
          find_blobs(depth4, intr, floor_mm=450.0)["n_blobs"] == 4)

    print("⑤ 임계 그물 + 입력 형태")
    res5 = find_blobs(depth, intr, min_height_mm=40)
    check("🧪 그물: min_height 40 → 0개", res5["n_blobs"] == 0, str(res5["n_blobs"]))
    try:
        find_blobs(np.zeros((960, 848), np.float32), intr)
        check("(960,848) 은 거부", False)
    except RuntimeError as e:
        check("(960,848) 은 거부(Intensity 동봉 9/16 함정)", "960" in str(e))
    print(f"  {'✅ 통과' if fails == 0 else '🔴 실패 ' + str(fails)}")
    return 0 if fails == 0 else 1


def main() -> int:
    enable_utf8_console()
    ap = argparse.ArgumentParser(description="depth 한 장에서 캘리브 블록 중심의 카메라 3D 좌표(mm)")
    ap.add_argument("--depth", type=Path, help="Blaze depth .npy (raw uint16 또는 mm)")
    ap.add_argument("--intr", type=Path, default=DEFAULT_INTR)
    ap.add_argument("--out", type=Path, default=None, help="결과 JSON 경로(기본 = depth 옆 *.blobs.json)")
    ap.add_argument("--min-height", type=float, default=8.0, help="바닥보다 이만큼(mm) 이상 높은 것만 물체로 본다(바닥이 보일 때만)")
    ap.add_argument("--near-cut", type=float, default=NEAR_CUT_MM, help="이보다 가까운 픽셀은 그리퍼·브라켓으로 보고 무효(mm)")
    ap.add_argument("--floor-mm", type=float, default=None, help="바닥 깊이를 사람이 지정(자동 판정을 덮어쓴다)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return _self_test()
    if not a.depth:
        ap.error("--depth 또는 --self-test")
    raw = np.load(a.depth)
    depth_mm, unit_msg = to_mm(raw, verbose=False)                    # 🚨 단위는 여기서만 정한다 · (배열, 설명) 튜플
    print(f"[단위] {unit_msg}  (🚨 중앙값은 그리퍼 픽셀이 섞여 낮게 나올 수 있다 — 아래 바닥 깊이를 본다)")
    intr = json.loads(Path(a.intr).read_text(encoding="utf-8"))
    res = find_blobs(depth_mm, intr, min_height_mm=a.min_height, near_cut_mm=a.near_cut, floor_mm=a.floor_mm)
    res["source"] = str(a.depth)
    for wmsg in res["warnings"]:
        print(wmsg)
    print(f"바닥 깊이 {res['floor_depth_mm']}mm ({res['floor_how']}) · 근접 무효 {res['near_pct']}% · 블롭 {res['n_blobs']}개")
    print(f"{'id':>3} {'u':>7} {'v':>7} {'area':>6} {'top':>7} {'height':>7} {'cam x':>8} {'cam y':>8} {'cam z':>8}")
    for b in res["blobs"]:
        x, y, z = b["cam_xyz_mm"]
        print(f"{b['id']:>3} {b['u']:>7.1f} {b['v']:>7.1f} {b['area_px']:>6} {b['top_depth_mm']:>7.1f} {b['height_mm']:>7.1f} {x:>8.1f} {y:>8.1f} {z:>8.1f}")
    out = a.out or a.depth.with_suffix(".blobs.json")
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out}")
    print("다음 = 같은 블록 윗면 중심에 로봇 TCP 를 대고 좌표를 적는다(id 순서대로) → cam_to_base build --blobs 이 파일 --robot-points @robot_points.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
