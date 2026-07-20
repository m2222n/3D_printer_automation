"""
ACE2 RGB Intrinsic 캘리브레이션 (ChArUco, OpenCV 4.13 CharucoDetector)
======================================================================

목적: 8mm 렌즈 장착한 ACE2 의 정확한 intrinsic(fx,fy,cx,cy) + 왜곡계수 구하기.
     → basler_capture.py ACE2_5MP_SPEC 의 이론 근사값을 실측값으로 교체.
     → RGB 융합의 선행 조건(A단계). B단계(Blaze↔ACE2 extrinsic)가 이 값에 의존.

⚠️ 실물 카메라 작업 = Mac 에서 직접 (6000엔 pypylon 없음).
⚠️ 보드 규격은 make_charuco_board.py 와 **완전히 동일**해야 함 (다르면 검출 0).
   인쇄 후 자로 한 칸 실측한 값을 --square-mm 로 넘길 것 (인쇄 배율 오차 흡수).

워크플로우:
  1) live 모드로 보드를 여러 각도/거리에서 캡처 (스페이스=현재 프레임 채택, 15~25장 권장)
     - 화면 모서리·중앙 골고루, 기울여서(±30°), 30~60cm 거리 변화
     - 검출된 코너가 초록으로 그려짐 → 충분히 잡힐 때만 채택
  2) 캡처 끝(q)나면 자동으로 calibrateCamera 실행 → 결과 출력·저장

사용:
    export BASLER_ACE2_IP=192.168.20.20
    python bin_picking/tests/calibrate_ace2_intrinsics.py \
        --squares-x 7 --squares-y 5 --square-mm 30 --marker-ratio 0.75

    # 이미 캡처해둔 이미지 폴더로 (라이브 없이):
    python bin_picking/tests/calibrate_ace2_intrinsics.py --images viz_output/calib_shots

키(라이브):
    SPACE   현재 프레임 채택 (코너 검출됐을 때만)
    d       마지막 채택 취소
    q/ESC   캡처 종료 → 캘리브 실행
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import cv2
import numpy as np

_DICT = cv2.aruco.DICT_5X5_250
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_board(sx: int, sy: int, square_mm: float, marker_ratio: float):
    square_m = square_mm / 1000.0
    marker_m = square_m * marker_ratio
    dictionary = cv2.aruco.getPredefinedDictionary(_DICT)
    board = cv2.aruco.CharucoBoard((sx, sy), square_m, marker_m, dictionary)
    detector = cv2.aruco.CharucoDetector(board)
    return board, detector


def _open_ace2(ip: str, exposure_us: float, packet_size: int, throughput_mbps: float):
    from pypylon import pylon
    tlf = pylon.TlFactory.GetInstance()
    info = pylon.DeviceInfo()
    info.SetIpAddress(ip)
    info.SetDeviceClass("BaslerGigE")
    cam = pylon.InstantCamera(tlf.CreateDevice(info))
    cam.Open()
    try:
        cam.GevSCPSPacketSize.SetValue(packet_size)
    except Exception:
        cam.GevSCPSPacketSize.SetValue(1500)
    cam.GevSCPD.SetValue(1000)
    try:
        n = cam.GetNodeMap().GetNode("DeviceLinkThroughputLimit")
        if n is not None:
            limit = int(throughput_mbps * 1_000_000)
            n.SetValue(max(int(n.Min), min(limit, int(n.Max))))
    except Exception:
        pass
    cam.MaxNumBuffer.SetValue(30)
    cam.ExposureAuto.SetValue("Continuous")
    return cam, pylon


def collect_from_live(args, board, detector):
    """라이브 뷰에서 보드 여러 장 채택 → gray 이미지 리스트 반환."""
    cam, pylon = _open_ace2(args.ip, args.exposure, args.packet_size, args.throughput)
    print(f"Model: {cam.GetDeviceInfo().GetModelName()}  "
          f"WxH: {cam.Width.GetValue()}x{cam.Height.GetValue()}")
    cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    win = "ACE2 ChArUco calib (SPACE=채택, d=취소, q=끝)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, int(2448 * 0.4), int(2048 * 0.4))

    shots: list[np.ndarray] = []  # gray full-res
    shot_dir = PROJECT_ROOT / "bin_picking" / "viz_output" / "calib_shots"
    shot_dir.mkdir(parents=True, exist_ok=True)

    try:
        while True:
            res = cam.RetrieveResult(2000, pylon.TimeoutHandling_Return)
            if res is None:
                continue
            if not res.GrabSucceeded():
                res.Release()
                continue
            raw = res.Array.copy()  # BayerRG8 (H,W)
            res.Release()
            bgr = cv2.cvtColor(raw, cv2.COLOR_BayerRG2BGR)
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

            ch_corners, ch_ids, _, _ = detector.detectBoard(gray)
            disp = cv2.resize(bgr, None, fx=0.4, fy=0.4, interpolation=cv2.INTER_AREA)
            n_corners = 0 if ch_ids is None else len(ch_ids)
            if n_corners > 0:
                pts = (ch_corners.reshape(-1, 2) * 0.4).astype(int)
                for p in pts:
                    cv2.circle(disp, tuple(p), 4, (0, 255, 0), -1)
            color = (0, 255, 0) if n_corners >= 6 else (0, 165, 255)
            cv2.putText(disp, f"corners: {n_corners}  accepted: {len(shots)}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)
            cv2.imshow(win, disp)

            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            elif key == ord(" ") and n_corners >= 6:
                shots.append(gray.copy())
                ts = time.strftime("%H%M%S")
                cv2.imwrite(str(shot_dir / f"calib_{len(shots):02d}_{ts}.png"), gray)
                print(f"  채택 {len(shots)} (corners {n_corners})")
            elif key == ord("d") and shots:
                shots.pop()
                print(f"  취소 → {len(shots)}장")
    finally:
        cam.StopGrabbing()
        cam.Close()
        cv2.destroyAllWindows()
    return shots


def collect_from_images(img_dir: Path):
    files = sorted([p for p in img_dir.iterdir()
                    if p.suffix.lower() in (".png", ".jpg", ".jpeg")])
    shots = []
    for p in files:
        g = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if g is not None:
            shots.append(g)
    print(f"  이미지 {len(shots)}장 로드 ({img_dir})")
    return shots


def calibrate(shots, board, detector):
    """채택된 gray 이미지들 → calibrateCamera. 반환: dict 결과."""
    all_obj, all_img = [], []
    img_size = None
    used = 0
    for gray in shots:
        if img_size is None:
            img_size = (gray.shape[1], gray.shape[0])
        ch_corners, ch_ids, _, _ = detector.detectBoard(gray)
        if ch_ids is None or len(ch_ids) < 6:
            continue
        obj_pts, img_pts = board.matchImagePoints(ch_corners, ch_ids)
        if obj_pts is None or len(obj_pts) < 6:
            continue
        all_obj.append(obj_pts)
        all_img.append(img_pts)
        used += 1

    if used < 5:
        return {"status": "FAIL",
                "message": f"유효 프레임 부족 ({used} < 5). 각도·거리 다양하게 더 촬영."}

    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        all_obj, all_img, img_size, None, None
    )
    return {
        "status": "OK",
        "rms_reproj_px": float(rms),
        "n_frames_used": used,
        "image_width": img_size[0],
        "image_height": img_size[1],
        "fx": float(K[0, 0]), "fy": float(K[1, 1]),
        "cx": float(K[0, 2]), "cy": float(K[1, 2]),
        "dist_coeffs": dist.ravel().tolist(),
        "camera_matrix": K.tolist(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", default=os.environ.get("BASLER_ACE2_IP", "192.168.20.20"))
    ap.add_argument("--squares-x", type=int, default=7)
    ap.add_argument("--squares-y", type=int, default=5)
    ap.add_argument("--square-mm", type=float, default=30.0,
                    help="인쇄 후 자로 실측한 한 칸 길이 mm")
    ap.add_argument("--marker-ratio", type=float, default=0.75)
    ap.add_argument("--exposure", type=float, default=8000.0)
    ap.add_argument("--packet-size", type=int, default=1500)
    ap.add_argument("--throughput", type=float, default=30.0)
    ap.add_argument("--images", type=Path, help="라이브 대신 이미지 폴더에서 캘리브")
    ap.add_argument("--out", type=Path,
                    default=PROJECT_ROOT / "bin_picking" / "config" / "ace2_intrinsics.json")
    args = ap.parse_args()

    board, detector = build_board(args.squares_x, args.squares_y,
                                  args.square_mm, args.marker_ratio)

    if args.images:
        shots = collect_from_images(args.images)
    else:
        shots = collect_from_live(args, board, detector)

    if not shots:
        print("[ERROR] 채택된 프레임 없음.")
        return 1

    print(f"\n캘리브 실행 ({len(shots)}장)...")
    result = calibrate(shots, board, detector)

    print("\n" + "=" * 60)
    print("ACE2 Intrinsic 캘리브 결과")
    print("=" * 60)
    if result["status"] != "OK":
        print(f"  ❌ {result['message']}")
        return 1

    print(f"  재투영 RMS: {result['rms_reproj_px']:.3f} px  "
          f"({'✅ 양호 <1px' if result['rms_reproj_px'] < 1.0 else '⚠️ >1px, 촬영 재검토'})")
    print(f"  사용 프레임: {result['n_frames_used']}")
    print(f"  fx={result['fx']:.1f}  fy={result['fy']:.1f}  "
          f"cx={result['cx']:.1f}  cy={result['cy']:.1f}")
    print(f"  dist: {[round(c, 4) for c in result['dist_coeffs']]}")
    print(f"\n  (참고) 8mm 이론 근사값: fx≈2920, cx=1224, cy=1024")

    result["board"] = {"squares_x": args.squares_x, "squares_y": args.squares_y,
                       "square_mm": args.square_mm, "marker_ratio": args.marker_ratio,
                       "dict": "DICT_5X5_250"}
    result["lens"] = "C23-0824-5M (8mm)"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n  ✅ 저장: {args.out}")
    print("  → basler_capture.py ACE2_5MP_SPEC 의 fx/fy/cx/cy 를 이 값으로 교체.")
    print("  → 다음 단계: Blaze↔ACE2 extrinsic 정렬(B).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
