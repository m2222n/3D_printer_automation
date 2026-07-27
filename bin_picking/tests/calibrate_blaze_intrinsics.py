"""
Blaze-112 Intrinsic 캘리브 (ChArUco, intensity 영상)
====================================================

목적: Blaze ToF의 **실측 intrinsic**(fx, fy, cx, cy, dist)을 구해
     `bin_picking/config/blaze_intrinsics.json` 생성.
     → extrinsic 정렬(calibrate_blaze_ace2_extrinsic.py)이 이걸 자동으로 집어 씀.

⚠️ 왜 필요한가 (7/27 규명)
--------------------------
기존 Blaze intrinsic은 FOV(75°×104°)에서 축마다 따로 역산한 **추정값**:

    fx=553, fy=188   →  비율 2.94 : 1

정상 카메라는 픽셀이 정사각형이라 **fx ≈ fy**여야 한다. 2.94배 차이는 물리적으로
불가능하며, 계산 방식(수평/수직 FOV를 각각 초점거리로 환산) 자체가 틀린 것이다.
이 K를 solvePnP에 넣으면 수렴 실패(PNP_FAIL)하거나 틀린 pose가 나와서,
**extrinsic 정렬에서 BOTH OK가 안 뜨는 원인**이 된다. (7/20·7/21 정렬 실패의 유력 원인)

ACE2는 이미 A단계에서 실측 완료(RMS 0.546px). Blaze도 같은 방식으로 맞춘다.

원리: ChArUco 보드를 Blaze **intensity(적외선 흑백)** 로 여러 각도 촬영 →
     cv2.calibrateCamera. depth가 아니라 intensity를 쓰는 이유는 보드의 흑백 패턴을
     봐야 하기 때문.

⚠️ 실물 = Mac 직접 (Blaze가 Mac에 연결됨). 6000 서버에서는 실행 불가.

사용:
    # 0) 네트워크 (재부팅 시마다 — ForceIp는 임시라 소멸)
    sudo ifconfig en10 192.168.30.1
    python bin_picking/tests/find_blaze.py --force-ip 192.168.30.10

    # 1) 캘리브 (라이브)
    python bin_picking/tests/calibrate_blaze_intrinsics.py \
        --ip 192.168.30.10 --square-mm 25 --exposure 400

    # 2) 저장된 이미지로 재계산 (노출 스윕 후 좋은 것만 골라 쓸 때)
    python bin_picking/tests/calibrate_blaze_intrinsics.py \
        --images /tmp/blaze_calib --square-mm 25 --min-corners 15

키:
    SPACE   현재 프레임 채택 (코너 검출됐을 때만)
    s       현재 프레임 PNG 저장 (--save-dir 지정 시)
    q/ESC   종료 → 캘리브 계산·저장

⭐ 촬영 요령 (ACE2 A단계 교훈 = 모션블러가 RMS 주범)
  - SPACE 직전 0.5초 정지. 손 흔들리면 RMS 급등(2.98 → 0.546px 개선 사례).
  - 보드를 화면 곳곳(중앙·네 모서리)에 + 기울기 다양하게 15~25장.
  - Blaze intensity는 850nm 조명에 과노출됨 → 조명 등지고 --exposure 200~800 스윕.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import cv2
import numpy as np

_DICT = cv2.aruco.DICT_5X5_250
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = PROJECT_ROOT / "bin_picking" / "config" / "blaze_intrinsics.json"


def build_board(sx: int, sy: int, square_mm: float, marker_ratio: float):
    square_m = square_mm / 1000.0
    dictionary = cv2.aruco.getPredefinedDictionary(_DICT)
    board = cv2.aruco.CharucoBoard((sx, sy), square_m, square_m * marker_ratio, dictionary)
    return board, cv2.aruco.CharucoDetector(board)


def open_blaze(ip: str, exposure_us: float, throughput_mbps: float):
    """Blaze를 intensity 모드로 열기.

    ⚠️ 함정 (7/20 규명, 전부 실제로 겪은 것):
      - Basler ToF는 ICMP 무응답 → ping으로 살았는지 판단 금지. pypylon 열거가 정답.
      - macOS 다중 어댑터에서 IP 직접 CreateDevice는 'Failed to discover' → GigE TL
        EnumerateAllDevices로 링크 스캔 후 매칭하는 방식이 견고.
      - GevSCPD는 Blaze에서 Max=96 (1000 넣으면 OutOfRange) → n.Max로 클램프.
      - macOS+USB어댑터는 66Mbps를 못 따라감 → DeviceLinkThroughputLimit 튜닝 필요.
    """
    from pypylon import pylon
    tlf = pylon.TlFactory.GetInstance()
    gige = tlf.CreateTl("BaslerGigE")
    target = None
    try:
        for d in gige.EnumerateAllDevices():
            if d.IsIpAddressAvailable() and d.GetIpAddress() == ip:
                target = d
                break
    except Exception:
        target = None
    if target is None:
        target = pylon.DeviceInfo()
        target.SetIpAddress(ip)
        target.SetDeviceClass("BaslerGigE")

    cam = pylon.InstantCamera(tlf.CreateDevice(target))
    cam.Open()
    nm = cam.GetNodeMap()
    try:
        cam.GevSCPSPacketSize.SetValue(1500)
    except Exception:
        pass
    try:
        n = nm.GetNode("GevSCPD")
        if n is not None:
            n.SetValue(min(1000, int(n.Max)))   # Blaze Max=96 클램프
    except Exception:
        pass
    try:
        n = nm.GetNode("DeviceLinkThroughputLimit")
        if n is not None:
            lim = int(throughput_mbps * 1_000_000)
            n.SetValue(max(int(n.Min), min(lim, int(n.Max))))
    except Exception:
        pass

    # depth 끄고 intensity(흑백) 켜기 — 보드 패턴을 봐야 하므로
    try:
        cs, ce = nm.GetNode("ComponentSelector"), nm.GetNode("ComponentEnable")
        cs.FromString("Range"); ce.SetValue(False)
        cs.FromString("Intensity"); ce.SetValue(True)
    except Exception as e:
        print(f"  ⚠️ intensity 전환 실패: {e}")
    try:
        n = nm.GetNode("ExposureTime")
        if n is not None:
            n.SetValue(max(float(n.Min), min(exposure_us, float(n.Max))))
            print(f"  intensity 노출: {exposure_us}us")
    except Exception:
        pass

    cam.MaxNumBuffer.SetValue(30)
    return cam, pylon


def grab_gray(cam, pylon):
    res = cam.RetrieveResult(2000, pylon.TimeoutHandling_Return)
    if res is None or not res.GrabSucceeded():
        if res is not None:
            res.Release()
        return None
    arr = res.Array.copy()
    res.Release()
    if arr.dtype != np.uint8:
        arr = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    if arr.ndim == 3:
        arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    return arr


def collect_from_live(args, board, detector):
    cam, pylon = open_blaze(args.ip, args.exposure, args.throughput)
    cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    win = "Blaze intensity - SPACE 채택 / s 저장 / q 종료"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    save_dir = args.save_dir
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)

    shots = []
    saved = 0
    try:
        while True:
            gray = grab_gray(cam, pylon)
            if gray is None:
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    break
                continue

            ch_corners, ch_ids, _, _ = detector.detectBoard(gray)
            n = 0 if ch_ids is None else len(ch_ids)
            disp = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            if n > 0:
                for p in ch_corners.reshape(-1, 2).astype(int):
                    cv2.circle(disp, tuple(p), 4, (0, 255, 0), -1)
            ok = n >= args.min_corners
            cv2.putText(disp, f"corners: {n}  shots: {len(shots)}  {'OK-SPACE' if ok else ''}",
                        (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 255, 0) if ok else (0, 0, 255), 2)
            cv2.putText(disp, "정지 0.5초 후 SPACE (모션블러가 RMS 주범)", (8, 52),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 1)
            cv2.imshow(win, disp)

            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if key == ord(" ") and ok:
                shots.append(gray.copy())
                print(f"  채택 {len(shots)} (corners {n})")
            if key == ord("s") and save_dir:
                cv2.imwrite(str(save_dir / f"blaze_{saved:03d}.png"), gray)
                saved += 1
                print(f"  저장 {saved}")
    finally:
        cam.StopGrabbing(); cam.Close()
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


def calibrate(shots, board, detector, min_corners: int):
    all_obj, all_img = [], []
    img_size = None
    used = skipped = 0
    for gray in shots:
        if img_size is None:
            img_size = (gray.shape[1], gray.shape[0])
        ch_corners, ch_ids, _, _ = detector.detectBoard(gray)
        if ch_ids is None or len(ch_ids) < max(6, min_corners):
            skipped += 1
            continue
        obj_pts, img_pts = board.matchImagePoints(ch_corners, ch_ids)
        if obj_pts is None or len(obj_pts) < 6:
            skipped += 1
            continue
        all_obj.append(obj_pts)
        all_img.append(img_pts)
        used += 1

    if used < 5:
        return {"status": "FAIL",
                "message": f"유효 프레임 부족 ({used} < 5). --min-corners 낮추거나 더 촬영."}

    rms, K, dist, _, _ = cv2.calibrateCamera(all_obj, all_img, img_size, None, None)
    return {
        "status": "OK",
        "rms_reproj_px": float(rms),
        "n_frames_used": used,
        "n_frames_skipped": skipped,
        "image_width": img_size[0],
        "image_height": img_size[1],
        "fx": float(K[0, 0]), "fy": float(K[1, 1]),
        "cx": float(K[0, 2]), "cy": float(K[1, 2]),
        "camera_matrix": K.tolist(),
        "dist_coeffs": dist.ravel().tolist(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ip", default=os.environ.get("BASLER_BLAZE_IP", "192.168.30.10"))
    ap.add_argument("--squares-x", type=int, default=7)
    ap.add_argument("--squares-y", type=int, default=5)
    ap.add_argument("--square-mm", type=float, default=25.0,
                    help="ChArUco 한 칸 실측 mm (자체 제작 A4 보드 = 25mm)")
    ap.add_argument("--marker-ratio", type=float, default=0.75)
    ap.add_argument("--exposure", type=float, default=400.0,
                    help="intensity 노출 us. 850nm 과노출이면 200~800 스윕")
    ap.add_argument("--throughput", type=float, default=30.0)
    ap.add_argument("--min-corners", type=int, default=10,
                    help="채택 최소 코너. 재계산 시 15~20으로 올리면 나쁜 프레임 걸러짐")
    ap.add_argument("--images", type=Path, help="라이브 대신 이미지 폴더에서 재계산")
    ap.add_argument("--save-dir", type=Path, help="라이브 중 s키로 PNG 저장할 폴더")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
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

    res = calibrate(shots, board, detector, args.min_corners)
    if res["status"] != "OK":
        print(f"[ERROR] {res['message']}")
        return 1

    fx, fy = res["fx"], res["fy"]
    ratio = max(fx, fy) / max(1e-9, min(fx, fy))

    print("\n" + "=" * 60)
    print("Blaze-112 Intrinsic 캘리브 결과")
    print("=" * 60)
    print(f"  사용 프레임: {res['n_frames_used']} (제외 {res['n_frames_skipped']})")
    print(f"  해상도: {res['image_width']}×{res['image_height']}")
    print(f"  fx={fx:.2f}  fy={fy:.2f}  cx={res['cx']:.2f}  cy={res['cy']:.2f}")
    print(f"  fx/fy 비율: {ratio:.3f} "
          f"({'✅ 정상(≈1)' if ratio < 1.15 else '🚨 비정상 — 촬영 재검토'})")
    rms = res["rms_reproj_px"]
    if rms < 1.0:
        verdict = "✅ 우수 (<1px)"
    elif rms < 2.0:
        verdict = "⚠️ 보통 (1~2px) — 쓸 수는 있음"
    else:
        verdict = "🚨 나쁨 (>2px) — 모션블러 의심, 정지 후 재촬영"
    print(f"  RMS 재투영 오차: {rms:.3f} px  {verdict}")
    print(f"  (참고: ACE2 A단계 실측 = 0.546px)")

    print(f"\n  [기존 추정값과 비교] fx=553 / fy=188 (비율 2.94, 물리적으로 불가능)")
    print(f"  [이번 실측값]        fx={fx:.1f} / fy={fy:.1f} (비율 {ratio:.2f})")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\n  ✅ 저장: {args.out}")
    print("  → 이제 calibrate_blaze_ace2_extrinsic.py 가 이 값을 자동으로 집어 씁니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
