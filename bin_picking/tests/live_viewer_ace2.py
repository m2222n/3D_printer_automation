"""
Basler ace2 (a2A2448-23gcBAS) 라이브 RGB 뷰어
==============================================

5/20 ACE2 셋업 검증용. BayerRG8 raw → 디모자이크 → 화면 표시.
포커스 / 노출 / 시야 / 색상 균형 사람 눈으로 확인.

사용법:
    export BASLER_ACE2_IP=192.168.20.20
    .venv/binpick/bin/python bin_picking/tests/live_viewer_ace2.py

키:
    ESC, q     종료
    s          스냅샷 PNG 저장 (viz_output/)
    a          노출 자동 토글 (Continuous / Off)
    [ ]        노출 -/+ (수동 모드일 때, ms 단위)
    f          포커스 도움 토글 (Laplacian variance 표시)

CLI:
    --ip 192.168.20.20        직접 IP (환경변수보다 우선)
    --exposure 8000           초기 노출 (us), 기본 8ms
    --auto                    시작 시 노출 자동 ON
    --packet-size 1500        GigE 패킷 크기 (jumbo 안 되면 1500)
    --throughput 30           GigE throughput 상한 (Mbps). macOS+USB어댑터 underrun 방지.
    --no-stats                통계 오버레이 끄기

⚠️ macOS Tahoe + USB이더넷 어댑터에서 GigE buffer underrun('incompletely grabbed',
   0xE1000014)이 뜨면 --throughput 를 낮추기 (7/20 Blaze 검증: 10Mbps=30/30 안정).
   ACE2는 5MP(6.5MB/frame)로 Blaze보다 무거워 더 낮아야 할 수 있음.
   기본 30Mbps에서 drop 뜨면 20 → 15 → 10 순으로 낮춰볼 것.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import cv2
import numpy as np
from pypylon import pylon


def _tune_gige(cam, throughput_mbps: float) -> None:
    """GigE throughput 상한을 낮춰 macOS+USB어댑터 buffer underrun 방지.

    7/20 Blaze 검증(basler_capture._tune_gige)과 동일한 레버.
    DeviceLinkThroughputLimit(bytes/s)를 카메라 지원 범위로 클램프.
    노드 없거나 실패해도 무시 — 기존 동작 유지(on-board에선 이 값이어도 무해).
    """
    limit = int(throughput_mbps * 1_000_000)
    try:
        n = cam.GetNodeMap().GetNode("DeviceLinkThroughputLimit")
        if n is not None:
            val = max(int(n.Min), min(limit, int(n.Max)))
            n.SetValue(val)
            print(f"  DeviceLinkThroughputLimit = {val/1e6:.1f} Mbps (요청 {throughput_mbps} Mbps)")
    except Exception as e:
        print(f"  throughput 튜닝 스킵: {e}")


def open_ace2(ip: str, exposure_us: float, auto: bool, packet_size: int,
              throughput_mbps: float) -> pylon.InstantCamera:
    """IP 직접 지정으로 ace2 카메라 열기."""
    tlf = pylon.TlFactory.GetInstance()
    info = pylon.DeviceInfo()
    info.SetIpAddress(ip)
    info.SetDeviceClass("BaslerGigE")
    cam = pylon.InstantCamera(tlf.CreateDevice(info))
    cam.Open()

    try:
        cam.GevSCPSPacketSize.SetValue(packet_size)
    except Exception as e:
        print(f"PacketSize {packet_size} 실패, 1500 fallback: {e}")
        cam.GevSCPSPacketSize.SetValue(1500)
    cam.GevSCPD.SetValue(1000)
    _tune_gige(cam, throughput_mbps)
    cam.MaxNumBuffer.SetValue(30)  # underrun 여유 (Blaze와 동일)

    if auto:
        try:
            cam.ExposureAuto.SetValue("Continuous")
        except Exception:
            pass
    else:
        try:
            cam.ExposureAuto.SetValue("Off")
        except Exception:
            pass
        cam.ExposureTime.SetValue(exposure_us)

    return cam


def overlay_stats(img: np.ndarray, raw_img: np.ndarray, fps: float,
                  exposure_us: float, auto: bool, show_focus: bool) -> None:
    """좌상단 통계 오버레이 (in-place).

    valid % 대신 RGB는 saturation / dark 픽셀 비율 + 포커스 척도 사용.
    """
    h, w = raw_img.shape
    sat = int(np.count_nonzero(raw_img >= 250))
    dark = int(np.count_nonzero(raw_img <= 5))
    sat_pct = 100.0 * sat / raw_img.size
    dark_pct = 100.0 * dark / raw_img.size
    mean = float(raw_img.mean())

    # 노출 가드 색상
    if sat_pct > 5.0:
        guard_color = (0, 0, 255)   # 빨강 = 포화 (노출 줄여야)
        guard_mark = "SAT"
    elif dark_pct > 50.0 or mean < 30.0:
        guard_color = (0, 255, 255) # 노랑 = 너무 어두움
        guard_mark = "DARK"
    else:
        guard_color = (0, 255, 0)   # 녹색 = 정상
        guard_mark = "OK"

    exp_str = f"AUTO {exposure_us:.0f}us" if auto else f"{exposure_us:.0f}us"
    lines = [
        (f"FPS {fps:5.1f}    mean {mean:5.1f}    sat {sat_pct:4.1f}%    dark {dark_pct:4.1f}% [{guard_mark}]", guard_color),
        (f"Exposure: {exp_str}    Resolution: {w}x{h}", (255, 255, 255)),
    ]

    if show_focus:
        # 중앙 ROI Laplacian variance (포커스 척도, 높을수록 선명)
        cy, cx = h // 2, w // 2
        roi = raw_img[cy-200:cy+200, cx-200:cx+200]
        focus_score = float(cv2.Laplacian(roi, cv2.CV_64F).var())
        focus_color = (0, 255, 0) if focus_score > 100 else (0, 255, 255) if focus_score > 30 else (0, 0, 255)
        lines.append((f"FOCUS score: {focus_score:7.1f}  (>100 sharp, >30 ok, <30 blurry)", focus_color))

    lines.append(("ESC/q quit   s save   a auto-exp   [ ] exp -/+   f focus", (255, 255, 255)))

    for i, (line, color) in enumerate(lines):
        y = 22 + i * 22
        cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, color, 1, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=os.environ.get("BASLER_ACE2_IP", "192.168.20.20"))
    ap.add_argument("--exposure", type=float, default=8000.0, help="us (1ms = 1000us)")
    ap.add_argument("--auto", action="store_true", help="자동 노출 시작")
    ap.add_argument("--packet-size", type=int, default=1500)
    ap.add_argument("--throughput", type=float, default=30.0,
                    help="GigE throughput 상한 (Mbps). drop 뜨면 20→15→10 낮출 것")
    ap.add_argument("--no-stats", action="store_true")
    ap.add_argument("--display-scale", type=float, default=0.4,
                    help="화면 표시 축소 (2448x2048 너무 커서 기본 0.4)")
    args = ap.parse_args()

    print(f"ACE2 IP: {args.ip}")
    cam = open_ace2(args.ip, args.exposure, args.auto, args.packet_size, args.throughput)
    print(f"Model: {cam.GetDeviceInfo().GetModelName()}  Serial: {cam.GetDeviceInfo().GetSerialNumber()}")
    print(f"PixelFormat: {cam.PixelFormat.GetValue()}  WxH: {cam.Width.GetValue()}x{cam.Height.GetValue()}")
    cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    win = "ACE2 Live (RGB)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, int(2448 * args.display_scale), int(2048 * args.display_scale))

    snapshot_dir = Path(__file__).resolve().parents[2] / "viz_output"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    last_t = time.time()
    fps = 0.0
    auto_exp = args.auto
    show_focus = False
    exposure_us = args.exposure

    print("뷰어 시작. ESC/q로 종료.")
    try:
        while True:
            res = cam.RetrieveResult(2000, pylon.TimeoutHandling_Return)
            if res is None:
                continue
            if not res.GrabSucceeded():
                print(f"  drop: {res.GetErrorDescription()[:60]}")
                res.Release()
                continue
            raw = res.Array.copy()  # uint8 (2048, 2448) BayerRG8
            res.Release()

            # 디모자이크 (Bayer → BGR)
            bgr = cv2.cvtColor(raw, cv2.COLOR_BayerRG2BGR)

            # 화면 축소
            if args.display_scale != 1.0:
                disp = cv2.resize(bgr, None, fx=args.display_scale, fy=args.display_scale,
                                  interpolation=cv2.INTER_AREA)
            else:
                disp = bgr.copy()

            # 현재 노출값 읽기 (auto 모드면 실시간 변화)
            try:
                exposure_us = cam.ExposureTime.GetValue()
            except Exception:
                pass

            if not args.no_stats:
                overlay_stats(disp, raw, fps, exposure_us, auto_exp, show_focus)

            cv2.imshow(win, disp)
            now = time.time()
            dt = now - last_t
            fps = 0.9 * fps + 0.1 * (1.0 / dt) if dt > 0 else fps
            last_t = now

            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            elif key == ord("s"):
                ts = time.strftime("%Y%m%d_%H%M%S")
                p_raw = snapshot_dir / f"ace2_live_{ts}_raw.png"
                p_bgr = snapshot_dir / f"ace2_live_{ts}_bgr.png"
                cv2.imwrite(str(p_raw), raw)
                cv2.imwrite(str(p_bgr), bgr)
                print(f"  saved: {p_bgr.name} (full {bgr.shape[1]}x{bgr.shape[0]}) + {p_raw.name}")
            elif key == ord("a"):
                auto_exp = not auto_exp
                try:
                    if auto_exp:
                        cam.ExposureAuto.SetValue("Continuous")
                        print("  exposure → AUTO")
                    else:
                        cam.ExposureAuto.SetValue("Off")
                        print(f"  exposure → MANUAL ({exposure_us:.0f}us)")
                except Exception as e:
                    print(f"  exposure 토글 실패: {e}")
            elif key == ord("["):
                if auto_exp:
                    print("  manual로 먼저 전환 (a 키)")
                else:
                    exposure_us = max(100.0, exposure_us * 0.7)
                    cam.ExposureTime.SetValue(exposure_us)
                    print(f"  exposure → {exposure_us:.0f}us")
            elif key == ord("]"):
                if auto_exp:
                    print("  manual로 먼저 전환 (a 키)")
                else:
                    exposure_us = min(100000.0, exposure_us * 1.4)
                    cam.ExposureTime.SetValue(exposure_us)
                    print(f"  exposure → {exposure_us:.0f}us")
            elif key == ord("f"):
                show_focus = not show_focus
                print(f"  focus score → {'ON' if show_focus else 'OFF'}")
    finally:
        cam.StopGrabbing()
        cam.Close()
        cv2.destroyAllWindows()
        print("종료.")


if __name__ == "__main__":
    main()
