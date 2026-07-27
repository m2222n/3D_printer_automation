"""
Blaze ↔ ACE2 Extrinsic 정렬 (RGB-D 정합, B단계)
================================================

목적: L자 브래킷에 고정된 Blaze(depth)와 ACE2(RGB)의 상대 위치·회전(R,t)을 구해
     depth를 RGB에 투영할 수 있게 함 = RGB-D 정합. A단계(intrinsic 캘리브) 완료 전제.

원리: 두 카메라가 **같은 ChArUco 보드를 동시에** 관측.
  - ACE2 RGB → ChArUco 검출 → solvePnP(캘리브된 intrinsic) → T_board_to_ace2
  - Blaze intensity(흑백) → ChArUco 검출 → solvePnP(Blaze intrinsic) → T_board_to_blaze
  - T_ace2_to_blaze = T_board_to_blaze @ inv(T_board_to_ace2)  ← 프레임마다 구해 평균
  L자 고정이라 한 번 구하면 재사용.

⚠️ Blaze는 ToF depth 카메라 → 흑백 intensity 컴포넌트로 보드를 봐야 함.
   intensity 화질이 낮으면 검출 실패 가능 → --diag 모드로 먼저 확인.
⚠️ 실물 = Mac 직접. 두 카메라 동시 연결 필요(Blaze .10, ACE2 .20 / 192.168.20).

사용:
    export BASLER_BLAZE_IP=192.168.20.10
    export BASLER_ACE2_IP=192.168.20.20

    # 1) 진단: 두 카메라가 보드를 동시에 검출하는지 먼저 확인 (강력 권장)
    python bin_picking/tests/calibrate_blaze_ace2_extrinsic.py --diag --square-mm 25

    # 2) 정렬: 보드를 두 카메라 공통 시야에 두고 여러 각도 채택 → extrinsic
    python bin_picking/tests/calibrate_blaze_ace2_extrinsic.py --square-mm 25

키(정렬):
    SPACE   현재 프레임 채택 (양쪽 다 검출됐을 때만)
    q/ESC   종료 → extrinsic 계산·저장
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
ACE2_INTRINSICS = PROJECT_ROOT / "bin_picking" / "config" / "ace2_intrinsics.json"
BLAZE_INTRINSICS = PROJECT_ROOT / "bin_picking" / "config" / "blaze_intrinsics.json"

# ⚠️ Blaze-112 intrinsics — FOV(75°×104°) 기반 추정값이며 **신뢰 불가**.
#    fx=553 / fy=188 = 비율 2.94:1 → 물리적으로 불가능(정상 카메라는 픽셀 정사각형이라 fx≈fy).
#    축마다 FOV를 따로 대입해 계산한 것이 원인 = 계산 방식 자체가 틀림.
#    이 K로 solvePnP하면 수렴 실패(PNP_FAIL)하거나 틀린 pose가 나옴 → extrinsic 정렬 실패의 유력 원인.
#    ✅ 정답 = calibrate_blaze_intrinsics.py 로 실측 캘리브 후 blaze_intrinsics.json 생성.
BLAZE_K_FALLBACK = np.array([[553.0, 0, 424.0], [0, 188.0, 240.0], [0, 0, 1]], np.float64)
BLAZE_DIST_FALLBACK = np.zeros(5, np.float64)


def load_blaze_intrinsics():
    """실측 캘리브 json 우선, 없으면 추정값 fallback. 반환: (K, dist, source)."""
    if BLAZE_INTRINSICS.exists():
        d = json.loads(BLAZE_INTRINSICS.read_text())
        return (np.array(d["camera_matrix"], np.float64),
                np.array(d["dist_coeffs"], np.float64), "실측 캘리브")
    return BLAZE_K_FALLBACK, BLAZE_DIST_FALLBACK, "⚠️추정값(신뢰불가)"


def build_board(sx, sy, square_mm, marker_ratio):
    square_m = square_mm / 1000.0
    dictionary = cv2.aruco.getPredefinedDictionary(_DICT)
    board = cv2.aruco.CharucoBoard((sx, sy), square_m, square_m * marker_ratio, dictionary)
    return board, cv2.aruco.CharucoDetector(board)


def load_ace2_intrinsics():
    if not ACE2_INTRINSICS.exists():
        raise SystemExit(f"[ERROR] ACE2 intrinsic 없음: {ACE2_INTRINSICS}\n"
                         f"  먼저 calibrate_ace2_intrinsics.py 로 A단계 완료할 것.")
    d = json.loads(ACE2_INTRINSICS.read_text())
    K = np.array(d["camera_matrix"], np.float64)
    dist = np.array(d["dist_coeffs"], np.float64)
    return K, dist


def open_cam(ip, throughput_mbps=30.0):
    """IP로 GigE 카메라 열기.

    macOS + 다중 어댑터(en8/en10 서로 다른 서브넷)에서는 IP 직접 CreateDevice가
    'Failed to discover'로 실패 → GigE TL의 EnumerateAllDevices로 먼저 링크를
    스캔한 뒤 IP 매칭되는 device 객체로 여는 방식이 견고(find_blaze 방식).
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
        # fallback: 기존 IP 직접 지정
        target = pylon.DeviceInfo()
        target.SetIpAddress(ip)
        target.SetDeviceClass("BaslerGigE")
    cam = pylon.InstantCamera(tlf.CreateDevice(target))
    cam.Open()
    try:
        cam.GevSCPSPacketSize.SetValue(1500)
    except Exception:
        pass
    try:
        # GevSCPD(inter-packet delay) — Blaze는 Max 96, ACE2는 큼. 범위로 클램프.
        n = cam.GetNodeMap().GetNode("GevSCPD")
        if n is not None:
            n.SetValue(min(1000, int(n.Max)))
    except Exception:
        pass
    try:
        n = cam.GetNodeMap().GetNode("DeviceLinkThroughputLimit")
        if n is not None:
            lim = int(throughput_mbps * 1_000_000)
            n.SetValue(max(int(n.Min), min(lim, int(n.Max))))
    except Exception:
        pass
    cam.MaxNumBuffer.SetValue(30)
    return cam, pylon


def setup_blaze_intensity(cam, exposure_us=1000.0):
    """Blaze를 intensity(흑백) 컴포넌트로 전환 → 보드 검출용.

    exposure_us: ToF intensity 노출. 강한 조명(850nm 직사광)에 과노출되면
                 흑백 대비가 날아가 ChArUco 검출 실패 → 노출 낮추기(예: 200~500).
    """
    nm = cam.GetNodeMap()
    try:
        cs, ce = nm.GetNode("ComponentSelector"), nm.GetNode("ComponentEnable")
        cs.FromString("Range"); ce.SetValue(False)      # depth 끄기
        cs.FromString("Intensity"); ce.SetValue(True)   # 흑백 켜기
    except Exception as e:
        print(f"  ⚠️ Blaze intensity 전환 실패: {e}")
    try:
        n = nm.GetNode("ExposureTime")
        if n is not None:
            n.SetValue(max(float(n.Min), min(exposure_us, float(n.Max))))
            print(f"  Blaze intensity 노출: {exposure_us}us")
    except Exception:
        pass


def grab_gray(cam, pylon, is_blaze):
    res = cam.RetrieveResult(2000, pylon.TimeoutHandling_Return)
    if res is None or not res.GrabSucceeded():
        if res is not None:
            res.Release()
        return None
    arr = res.Array.copy()
    res.Release()
    if is_blaze:
        # intensity = Mono (8 or 16bit). 8bit로 정규화.
        if arr.dtype != np.uint8:
            arr = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        return arr
    # ACE2 = BayerRG8 → gray
    bgr = cv2.cvtColor(arr, cv2.COLOR_BayerRG2BGR)
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


def detect_corners(gray, detector):
    """ChArUco 코너 검출만 → (ch_corners, ch_ids, n) 또는 (None,None,0)."""
    ch_corners, ch_ids, _, _ = detector.detectBoard(gray)
    n = 0 if ch_ids is None else len(ch_ids)
    return ch_corners, ch_ids, n


def pose_from_corners(ch_corners, ch_ids, board, K, dist, min_corners=6):
    """검출된 코너 → solvePnP → (rvec, tvec, n). 실패 시 None."""
    r = pose_from_corners_diag(ch_corners, ch_ids, board, K, dist, min_corners)
    return r[0]


def pose_from_corners_diag(ch_corners, ch_ids, board, K, dist, min_corners=6):
    """pose_from_corners + 실패 사유 문자열.

    ⭐ 7/27 추가: "코너는 잡히는데 pose가 안 나오는" 경우를 구분하기 위함.
       코너 부족(조명·화각 문제)과 PnP 실패(intrinsic 문제)는 대응책이 완전히 다른데,
       기존엔 둘 다 그냥 OK 미표시라 현장에서 원인 판별이 불가능했음.

    반환: (pose or None, reason)
      reason: "OK" | "NO_CORNERS" | "FEW_CORNERS(n<min)" | "MATCH_FAIL" | "PNP_FAIL"
    """
    if ch_ids is None or len(ch_ids) == 0:
        return None, "NO_CORNERS"
    n = len(ch_ids)
    need = max(4, min_corners)
    if n < need:
        return None, f"FEW_CORNERS({n}<{need})"
    obj_pts, img_pts = board.matchImagePoints(ch_corners, ch_ids)
    if obj_pts is None or len(obj_pts) < need:
        return None, "MATCH_FAIL"
    ok, rvec, tvec = cv2.solvePnP(obj_pts, img_pts, K, dist)
    if not ok:
        return None, "PNP_FAIL"
    return (rvec, tvec, n), "OK"


def check_intrinsic_sanity(K, name, width=None):
    """fx/fy 비율 sanity check → 경고 문자열 리스트.

    ⭐ 7/27: Blaze K가 fx=553/fy=188(비율 2.94)로 물리적으로 불가능한 값이었음.
       정상 카메라는 픽셀이 정사각형이라 fx≈fy여야 함. FOV(75°×104°)를 축마다
       따로 대입해 계산한 추정값이 원인 — 그 계산 방식 자체가 틀림.
       이 K로 solvePnP하면 수렴 실패(PNP_FAIL) 또는 틀린 pose가 나옴.
    """
    warns = []
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]
    ratio = max(fx, fy) / max(1e-9, min(fx, fy))
    if ratio > 1.15:
        warns.append(
            f"🚨 {name} fx/fy 비율 {ratio:.2f} (fx={fx:.1f}, fy={fy:.1f}) — "
            f"정상 카메라는 fx≈fy. 이 intrinsic으로는 solvePnP가 실패하거나 "
            f"틀린 pose를 냄. → calibrate_blaze_intrinsics.py 로 실측 캘리브 필요."
        )
    if width is not None and abs(cx - width / 2) > width * 0.25:
        warns.append(f"⚠️ {name} cx={cx:.1f}가 이미지 중심({width/2:.0f})에서 많이 벗어남")
    return warns


def to_T(rvec, tvec):
    R, _ = cv2.Rodrigues(rvec)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = tvec.ravel()
    return T


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blaze-ip", default=os.environ.get("BASLER_BLAZE_IP", "192.168.20.10"))
    ap.add_argument("--ace2-ip", default=os.environ.get("BASLER_ACE2_IP", "192.168.20.20"))
    ap.add_argument("--squares-x", type=int, default=7)
    ap.add_argument("--squares-y", type=int, default=5)
    ap.add_argument("--square-mm", type=float, default=25.0)
    ap.add_argument("--marker-ratio", type=float, default=0.75)
    ap.add_argument("--blaze-exposure", type=float, default=1000.0,
                    help="Blaze intensity 노출 us. 과노출로 보드 안 보이면 낮추기(300~500)")
    ap.add_argument("--min-corners", type=int, default=6,
                    help="pose 성립 최소 코너(양쪽 동시 어려우면 4로 낮춤, 정확도 소폭↓)")
    ap.add_argument("--diag", action="store_true", help="진단: 검출만 확인(정렬 안 함)")
    ap.add_argument("--out", type=Path,
                    default=PROJECT_ROOT / "bin_picking" / "config" / "blaze_ace2_extrinsic.json")
    args = ap.parse_args()

    board, detector = build_board(args.squares_x, args.squares_y,
                                  args.square_mm, args.marker_ratio)
    ace2_K, ace2_dist = load_ace2_intrinsics()
    print(f"ACE2 intrinsic 로드: fx={ace2_K[0,0]:.1f} fy={ace2_K[1,1]:.1f} cx={ace2_K[0,2]:.1f}")

    # Blaze intrinsic: 실측 캘리브 json 있으면 그걸, 없으면 추정값(경고와 함께)
    blaze_K, blaze_dist, blaze_src = load_blaze_intrinsics()
    print(f"Blaze intrinsic 로드({blaze_src}): "
          f"fx={blaze_K[0,0]:.1f} fy={blaze_K[1,1]:.1f} cx={blaze_K[0,2]:.1f}")

    warns = (check_intrinsic_sanity(ace2_K, "ACE2")
             + check_intrinsic_sanity(blaze_K, "Blaze", width=848))
    for w in warns:
        print(f"  {w}")
    if warns:
        print("  ⚠️ 위 경고가 있으면 BOTH OK가 안 뜨거나 spread가 커질 수 있음.\n"
              "     --diag 로 먼저 확인: 코너는 잡히는데 [PNP_FAIL]이면 intrinsic이 원인.")

    blaze, pylon = open_cam(args.blaze_ip)
    setup_blaze_intensity(blaze, args.blaze_exposure)
    ace2, _ = open_cam(args.ace2_ip)
    try:
        ace2.ExposureAuto.SetValue("Continuous")
    except Exception:
        pass
    blaze.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    ace2.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    print("두 카메라 grab 시작. 보드를 양쪽 공통 시야에 두세요.")

    win_b, win_a = "Blaze intensity", "ACE2 RGB"
    cv2.namedWindow(win_b, cv2.WINDOW_NORMAL)
    cv2.namedWindow(win_a, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_a, 640, 536)

    T_pairs = []  # (T_board_to_blaze, T_board_to_ace2)
    try:
        while True:
            gb = grab_gray(blaze, pylon, is_blaze=True)
            ga = grab_gray(ace2, pylon, is_blaze=False)
            if gb is None or ga is None:
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    break
                continue

            cb, ib, nb = detect_corners(gb, detector)
            ca, ia, na = detect_corners(ga, detector)
            pb, why_b = pose_from_corners_diag(cb, ib, board, blaze_K, blaze_dist,
                                               args.min_corners)
            pa, why_a = pose_from_corners_diag(ca, ia, board, ace2_K, ace2_dist,
                                               args.min_corners)

            disp_b = cv2.cvtColor(gb, cv2.COLOR_GRAY2BGR)
            disp_a = cv2.cvtColor(ga, cv2.COLOR_GRAY2BGR)
            # 검출 코너 점으로 그리기 (어디가 잡히는지 눈으로 확인)
            if nb > 0:
                for p in cb.reshape(-1, 2).astype(int):
                    cv2.circle(disp_b, tuple(p), 5, (0, 255, 0), -1)
            if na > 0:
                for p in ca.reshape(-1, 2).astype(int):
                    cv2.circle(disp_a, tuple(p), 6, (0, 255, 0), -1)
            disp_a = cv2.resize(disp_a, (640, 536))

            ok_b = pb is not None
            ok_a = pa is not None
            # ⭐ 실패 사유를 화면에 표시 — "코너는 잡히는데 PNP_FAIL"이면 intrinsic 문제,
            #    "NO_CORNERS/FEW_CORNERS"면 조명·화각 문제. 대응책이 다르므로 구분 필수.
            cv2.putText(disp_b, f"Blaze corners: {nb} [{why_b}]", (8, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0) if ok_b else (0, 0, 255), 2)
            cv2.putText(disp_a, f"ACE2 corners: {na} [{why_a}]  pairs: {len(T_pairs)}",
                        (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                        (0, 255, 0) if ok_a else (0, 0, 255), 2)
            if why_b == "PNP_FAIL" or why_a == "PNP_FAIL":
                cv2.putText(disp_b, "PNP_FAIL = intrinsic 의심 (코너는 보임)", (8, 84),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            # 양쪽 동시 성립이면 상단에 크게 표시(채택 타이밍 알림)
            if ok_b and ok_a:
                cv2.putText(disp_b, "<< BOTH OK - SPACE >>", (8, 56),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.imshow(win_b, disp_b)
            cv2.imshow(win_a, disp_a)

            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if not args.diag and key == ord(" ") and ok_b and ok_a:
                T_pairs.append((to_T(pb[0], pb[1]), to_T(pa[0], pa[1])))
                print(f"  채택 {len(T_pairs)} (blaze {nb}, ace2 {na})")
    finally:
        blaze.StopGrabbing(); blaze.Close()
        ace2.StopGrabbing(); ace2.Close()
        cv2.destroyAllWindows()

    if args.diag:
        print("\n[진단 종료] 화면의 대괄호 안 사유로 원인을 가를 것:")
        print("  [OK]                → 정렬 가능. --diag 빼고 재실행해 SPACE로 채택.")
        print("  [NO_CORNERS]/[FEW_CORNERS] → 조명·화각 문제.")
        print("        → Blaze: 조명 등지기 + --blaze-exposure 200~800 스윕")
        print("        → 화각차: 보드를 두 화각 겹치는 중앙에 / 카메라를 더 멀리 / A3 보드")
        print("  [PNP_FAIL]          → 🚨 intrinsic 문제(코너는 보이는데 pose 계산 실패).")
        print("        → python bin_picking/tests/calibrate_blaze_intrinsics.py 로 실측 캘리브")
        print("           (현 Blaze 추정값 fx=553/fy=188은 비율 2.94로 물리적으로 불가능)")
        return 0

    if len(T_pairs) < 3:
        print(f"[ERROR] 채택 부족 ({len(T_pairs)} < 3). 양쪽 동시 검출되는 위치에서 더 채택.")
        return 1

    # T_ace2_to_blaze = T_board_to_blaze @ inv(T_board_to_ace2), 프레임마다 → 평균
    Ts = [Tb @ np.linalg.inv(Ta) for Tb, Ta in T_pairs]
    t_mean = np.mean([T[:3, 3] for T in Ts], axis=0)
    # 회전 평균: 쿼터니언 평균 근사(첫 R 기준 정렬 후 산술평균→재정규화)
    Rs = np.array([T[:3, :3] for T in Ts])
    R_mean = Rs.mean(axis=0)
    U, _, Vt = np.linalg.svd(R_mean)
    R_mean = U @ Vt
    spread_mm = float(np.std([T[:3, 3] for T in Ts], axis=0).mean() * 1000)

    T_final = np.eye(4)
    T_final[:3, :3] = R_mean
    T_final[:3, 3] = t_mean

    print("\n" + "=" * 60)
    print("Blaze ↔ ACE2 Extrinsic 결과 (T_ace2_to_blaze)")
    print("=" * 60)
    print(f"  채택 프레임: {len(T_pairs)}")
    print(f"  translation (m): [{t_mean[0]:.4f}, {t_mean[1]:.4f}, {t_mean[2]:.4f}]")
    print(f"  baseline: {np.linalg.norm(t_mean)*1000:.1f} mm  (두 카메라 광학중심 거리)")
    print(f"  프레임 간 translation 산포(std): {spread_mm:.2f} mm  "
          f"({'✅ 안정 <5mm' if spread_mm < 5 else '⚠️ >5mm, 프레임 재검토'})")

    result = {
        "T_ace2_to_blaze": T_final.tolist(),
        "translation_m": t_mean.tolist(),
        "baseline_mm": float(np.linalg.norm(t_mean) * 1000),
        "spread_mm": spread_mm,
        "n_frames": len(T_pairs),
        "board": {"squares_x": args.squares_x, "squares_y": args.squares_y,
                  "square_mm": args.square_mm},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n  ✅ 저장: {args.out}")
    print("  → RGB-D 정합: depth 점을 이 T로 ACE2 좌표계에 투영 후 RGB 샘플링.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
