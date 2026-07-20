"""
Basler Blaze-112 라이브 depth 뷰어 (Mac/Linux 공용)
====================================================

부품 위치 조절 + 시야 확인용. depth를 컬러맵으로 화면에 띄운다.

사용법:
    export BASLER_BLAZE_IP=192.168.20.10
    .venv/binpick/bin/python bin_picking/tests/live_viewer_basler.py

키:
    ESC, q     종료
    s          현재 프레임 PNG 스냅샷 저장 (viz_output/)
    c          컬러맵 토글 (JET / TURBO / INFERNO)
    r          depth 범위 자동 재계산 (현재 프레임 1~99 percentile)
    +/-        depth 표시 범위 확장/축소

CLI:
    --ip 192.168.20.10        직접 IP 지정 (환경변수보다 우선)
    --depth-min 300           mm
    --depth-max 1500          mm
    --no-stats                통계 오버레이 끄기
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import cv2
import numpy as np
from pypylon import pylon


COLORMAPS = [cv2.COLORMAP_JET, cv2.COLORMAP_TURBO, cv2.COLORMAP_INFERNO]
COLORMAP_NAMES = ["JET", "TURBO", "INFERNO"]


def open_blaze(ip: str) -> pylon.InstantCamera:
    """IP 직접 지정으로 Blaze 카메라 열기."""
    tlf = pylon.TlFactory.GetInstance()
    info = pylon.DeviceInfo()
    info.SetIpAddress(ip)
    info.SetDeviceClass("BaslerGigE")
    cam = pylon.InstantCamera(tlf.CreateDevice(info))
    cam.Open()
    nm = cam.GetNodeMap()

    # Range component만 enable (Intensity off) → 깨끗한 848×480 mm depth
    try:
        cs = nm.GetNode("ComponentSelector")
        ce = nm.GetNode("ComponentEnable")
        cs.FromString("Intensity")
        ce.SetValue(False)
        cs.FromString("Range")
        ce.SetValue(True)
    except Exception:
        pass

    try:
        nm.GetNode("ExposureTime").SetValue(1000)  # 1ms
    except Exception:
        pass

    # GigE 스트리밍 튜닝 (macOS + USB 어댑터 buffer underrun 방지)
    # basler_capture._tune_gige와 동일 값. 이거 없으면 라이브 뷰가 멈춤/에러.
    try:
        n = nm.GetNode("DeviceLinkThroughputLimit")
        if n is not None:
            val = max(int(n.Min), min(10_000_000, int(n.Max)))
            n.SetValue(val)
    except Exception:
        pass
    try:
        cam.MaxNumBuffer.SetValue(30)
    except Exception:
        pass

    return cam


def colorize(depth_mm: np.ndarray, dmin_mm: int, dmax_mm: int, cmap_idx: int) -> np.ndarray:
    """uint16 depth → 8-bit 컬러맵 BGR."""
    valid = (depth_mm > 0) & (depth_mm >= dmin_mm) & (depth_mm <= dmax_mm)
    clipped = np.clip(depth_mm, dmin_mm, dmax_mm).astype(np.float32)
    norm = (clipped - dmin_mm) / max(1.0, dmax_mm - dmin_mm)  # 0~1
    img8 = (norm * 255).astype(np.uint8)
    colored = cv2.applyColorMap(img8, COLORMAPS[cmap_idx])
    colored[~valid] = 0  # 유효 안 잡힌 픽셀은 검정
    return colored


def overlay_stats(img: np.ndarray, depth_mm: np.ndarray, fps: float,
                  dmin_mm: int, dmax_mm: int, cmap_idx: int) -> None:
    """좌상단에 통계 텍스트 그리기 (in-place).

    valid % 가드 (SOP v1.1 § 1.3): 70%+ = 본 캡처 OK, 50~70% = 조정 권장, < 50% = 셋업 재점검.
    가드 색상: 녹색 (≥70) / 노랑 (50~70) / 빨강 (<50). 5/15 본 캡처 직관 판정용.
    """
    valid = (depth_mm > 0) & (depth_mm >= dmin_mm) & (depth_mm <= dmax_mm)
    n_valid = int(np.count_nonzero(valid))
    pct = 100.0 * n_valid / depth_mm.size
    median_mm = float(np.median(depth_mm[valid])) if n_valid > 0 else 0.0

    # valid % 가드 색상 (BGR)
    if pct >= 70.0:
        guard_color = (0, 255, 0)      # 녹색 = 본 캡처 OK
        guard_mark = "OK"
    elif pct >= 50.0:
        guard_color = (0, 255, 255)    # 노랑 = 거리/조명 조정 권장
        guard_mark = "ADJ"
    else:
        guard_color = (0, 0, 255)      # 빨강 = 셋업 재점검
        guard_mark = "FAIL"

    lines = [
        (f"FPS {fps:5.1f}    valid {pct:4.1f}% [{guard_mark}]    median {median_mm:5.0f} mm", guard_color),
        (f"range {dmin_mm}-{dmax_mm} mm    cmap {COLORMAP_NAMES[cmap_idx]}", (255, 255, 255)),
        (f"ESC/q quit   s save   c cmap   r auto-range   +/- range", (255, 255, 255)),
    ]
    for i, (line, color) in enumerate(lines):
        y = 22 + i * 22
        # 검정 외곽선 (가독성)
        cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 0, 0), 3, cv2.LINE_AA)
        # 본 텍스트 (첫 줄은 가드 색상, 나머지는 흰색)
        cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, color, 1, cv2.LINE_AA)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=os.environ.get("BASLER_BLAZE_IP", "192.168.20.10"))
    ap.add_argument("--depth-min", type=int, default=300, help="mm")
    ap.add_argument("--depth-max", type=int, default=1500, help="mm")
    ap.add_argument("--no-stats", action="store_true")
    args = ap.parse_args()

    print(f"Blaze IP: {args.ip}")
    cam = open_blaze(args.ip)
    cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    win = "Blaze Live (depth)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    cmap_idx = 0
    dmin_mm = args.depth_min
    dmax_mm = args.depth_max

    snapshot_dir = Path(__file__).resolve().parents[2] / "viz_output"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    last_t = time.time()
    fps = 0.0
    print("뷰어 시작. ESC/q로 종료.")
    try:
        while True:
            res = cam.RetrieveResult(5000, pylon.TimeoutHandling_Return)
            if res is None:
                continue  # 타임아웃 — 다음 프레임 시도 (뷰어 안 죽음)
            if not res.GrabSucceeded():
                res.Release()
                continue  # 간헐 buffer underrun — 스킵하고 계속
            depth = res.Array.copy()
            res.Release()

            colored = colorize(depth, dmin_mm, dmax_mm, cmap_idx)
            if not args.no_stats:
                overlay_stats(colored, depth, fps, dmin_mm, dmax_mm, cmap_idx)

            cv2.imshow(win, colored)
            now = time.time()
            dt = now - last_t
            fps = 0.9 * fps + 0.1 * (1.0 / dt) if dt > 0 else fps
            last_t = now

            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            elif key == ord("s"):
                ts = time.strftime("%Y%m%d_%H%M%S")
                p_depth = snapshot_dir / f"blaze_live_{ts}_depth.npy"
                p_view = snapshot_dir / f"blaze_live_{ts}_view.png"
                np.save(p_depth, depth)
                cv2.imwrite(str(p_view), colored)
                print(f"  saved: {p_depth.name} + {p_view.name}")
            elif key == ord("c"):
                cmap_idx = (cmap_idx + 1) % len(COLORMAPS)
                print(f"  cmap → {COLORMAP_NAMES[cmap_idx]}")
            elif key == ord("r"):
                valid = (depth > 0)
                if np.count_nonzero(valid) > 100:
                    p1, p99 = np.percentile(depth[valid], [1, 99])
                    dmin_mm = int(max(50, p1 - 30))
                    dmax_mm = int(p99 + 30)
                    print(f"  auto-range → {dmin_mm}~{dmax_mm} mm")
            elif key in (ord("+"), ord("=")):
                dmax_mm += 200
                print(f"  range → {dmin_mm}~{dmax_mm} mm")
            elif key in (ord("-"), ord("_")):
                dmax_mm = max(dmin_mm + 100, dmax_mm - 200)
                print(f"  range → {dmin_mm}~{dmax_mm} mm")
    finally:
        cam.StopGrabbing()
        cam.Close()
        cv2.destroyAllWindows()
        print("종료.")


if __name__ == "__main__":
    main()
