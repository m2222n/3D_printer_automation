"""
RGB-D 정합 눈으로 검증 — Blaze depth를 ACE2 화면에 겹쳐 보기
================================================================

⭐ 왜 필요한가 (7/28)
   extrinsic이 맞았는지를 **산포 숫자나 자 측정으로는 확인하기 어렵다.**
   - 산포(spread)는 "프레임끼리 얼마나 일관적인가"일 뿐, 값이 맞는지는 말 안 함
   - 자로 재는 광학중심 거리는 x축은 몰라도 **y·z축은 기준 잡기가 사실상 불가능**
     (광학중심은 렌즈 안쪽에 있어 눈에 안 보이고, 두 카메라 몸통 형태도 다름)

   → 가장 확실한 검증은 **겹쳐서 눈으로 보는 것**이다.
     extrinsic이 맞으면 depth 윤곽이 RGB 물체와 겹치고,
     틀리면 그 방향·크기만큼 밀려 보인다. 어긋난 방향이 곧 원인을 알려준다.

읽는 법:
   - 색 = 거리 (가까움=빨강 … 멀리=파랑). ACE2 흑백 영상 위에 반투명 오버레이.
   - **물체 경계와 색 경계가 일치하면 정합 성공.**
   - 일정 방향으로 밀려 있으면 extrinsic의 해당 축이 틀린 것.
     예) 위아래로 밀림 → y 성분 오류 / 좌우로 밀림 → x 성분 오류

사용:
    python bin_picking/tests/verify_rgbd_overlay.py \
        --blaze-ip 192.168.20.10 --ace2-ip 192.168.30.20

키:
    a       오버레이 on/off (겹치기 전/후 비교)
    [ / ]   오버레이 투명도 조절
    s       현재 화면 PNG 저장
    q/ESC   종료
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from bin_picking.src.acquisition.extrinsic_io import (  # noqa: E402
    ExtrinsicError,
    describe,
    load_extrinsic,
)
from bin_picking.src.acquisition.rgbd_fusion import (  # noqa: E402
    NO_DEPTH,
    FusionError,
    align_depth_to_ace2,
    coverage_report,
    load_ace2_intrinsics,
    load_blaze_intrinsics,
)

# 표시 크기 — 5MP 원본은 화면에 안 들어가므로 축소해서 다룬다.
VIEW_W, VIEW_H = 1024, 856


def open_cam(ip, throughput_mbps=30.0):
    """calibrate_blaze_ace2_extrinsic.open_cam 과 동일 방식(다중 어댑터 대응)."""
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
    for name, val in (("GevSCPSPacketSize", 1500),):
        try:
            cam.GetNodeMap().GetNode(name).SetValue(val)
        except Exception:
            pass
    try:
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


def setup_blaze_range(cam):
    """Blaze를 Range(depth) 컴포넌트로 — 여기선 intensity가 아니라 **거리**가 필요."""
    nm = cam.GetNodeMap()
    try:
        cs, ce = nm.GetNode("ComponentSelector"), nm.GetNode("ComponentEnable")
        cs.FromString("Intensity"); ce.SetValue(False)
        cs.FromString("Range"); ce.SetValue(True)
    except Exception as e:
        print(f"  ⚠️ Blaze Range 전환 실패: {e}")


def grab(cam, pylon):
    res = cam.RetrieveResult(2000, pylon.TimeoutHandling_Return)
    if res is None or not res.GrabSucceeded():
        if res is not None:
            res.Release()
        return None
    try:
        arr = res.Array.copy()
    except Exception:
        # 지원 안 되는 픽셀 포맷 프레임은 스킵 (7/28 유실 사고 교훈)
        return None
    finally:
        res.Release()
    return arr


def colorize(depth_mm: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """depth(mm) → 컬러맵. 가까움=빨강, 멀리=파랑. 무효는 검정."""
    valid = depth_mm > NO_DEPTH
    norm = np.zeros(depth_mm.shape, np.uint8)
    if valid.any():
        d = np.clip(depth_mm, lo, hi)
        norm = ((d - lo) / max(1e-6, hi - lo) * 255).astype(np.uint8)
    color = cv2.applyColorMap(norm, cv2.COLORMAP_JET)
    color[~valid] = 0
    return color, valid


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blaze-ip", default=os.environ.get("BASLER_BLAZE_IP", "192.168.20.10"))
    ap.add_argument("--ace2-ip", default=os.environ.get("BASLER_ACE2_IP", "192.168.30.20"))
    ap.add_argument("--near-mm", type=float, default=300.0, help="컬러맵 최소 거리")
    ap.add_argument("--far-mm", type=float, default=1200.0, help="컬러맵 최대 거리")
    ap.add_argument("--dilate", type=int, default=2,
                    help="정합 구멍 메우기 반경(px). Blaze가 저해상이라 기본 2")
    ap.add_argument("--save-dir", type=Path,
                    default=PROJECT_ROOT / "bin_picking" / "config" / "overlay_shots")
    args = ap.parse_args()

    # --- 캘리브 로드 (여기서 막히면 앞 단계가 안 끝난 것) ---
    try:
        ext = load_extrinsic(strict=False)   # 산포 경고는 띄우되 진행
    except ExtrinsicError as e:
        print(f"[ERROR] {e}")
        return 1
    print(describe(ext))
    try:
        ace2_full = load_ace2_intrinsics()
        blaze_intr = load_blaze_intrinsics()
    except FusionError as e:
        print(f"[ERROR] {e}")
        return 1
    print(f"Blaze intrinsic: fx={blaze_intr.fx:.1f} fy={blaze_intr.fy:.1f}")

    # 표시 해상도에 맞춰 ACE2 intrinsic 스케일 (원본 5MP 그대로는 화면에 안 들어감)
    sx = VIEW_W / float(ace2_full.width)
    sy = VIEW_H / float(ace2_full.height)
    ace2_view = ace2_full.scaled(sx, sy)
    print(f"표시 해상도 {VIEW_W}×{VIEW_H} (intrinsic 스케일 {sx:.3f}, {sy:.3f})")

    blaze, pylon = open_cam(args.blaze_ip)
    setup_blaze_range(blaze)
    ace2, _ = open_cam(args.ace2_ip)
    blaze.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    ace2.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

    win = "RGB-D overlay (a=on/off  [ ]=투명도  s=저장  q=종료)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, VIEW_W, VIEW_H)
    show_overlay, alpha, saved = True, 0.5, 0
    printed_cov = False

    try:
        while True:
            db = grab(blaze, pylon)
            ca = grab(ace2, pylon)
            if db is None or ca is None:
                if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                    break
                continue

            # ACE2: BayerRG8 → gray → 표시 크기
            gray = cv2.cvtColor(cv2.cvtColor(ca, cv2.COLOR_BayerRG2BGR),
                                cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (VIEW_W, VIEW_H))
            base = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

            # Blaze depth(uint16 mm) → ACE2 격자로 정합
            if db.ndim == 3:
                db = db[..., 0]
            aligned = align_depth_to_ace2(
                db.astype(np.float32), (VIEW_H, VIEW_W),
                extrinsic=ext, ace2_intr=ace2_view, blaze_intr=blaze_intr,
                dilate=args.dilate,
            )
            if not printed_cov:
                print(coverage_report(aligned))
                printed_cov = True

            disp = base
            if show_overlay:
                color, valid = colorize(aligned, args.near_mm, args.far_mm)
                disp = base.copy()
                disp[valid] = cv2.addWeighted(
                    base, 1 - alpha, color, alpha, 0)[valid]

            cov = 100.0 * np.count_nonzero(aligned > NO_DEPTH) / aligned.size
            cv2.putText(disp, f"overlay {'ON' if show_overlay else 'OFF'}  "
                              f"alpha {alpha:.1f}  coverage {cov:.1f}%",
                        (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            cv2.putText(disp, "물체 경계와 색 경계가 겹치면 정합 OK / 밀려 있으면 그 축이 오류",
                        (8, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 255), 1)
            cv2.imshow(win, disp)

            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if key == ord("a"):
                show_overlay = not show_overlay
            if key == ord("["):
                alpha = max(0.1, alpha - 0.1)
            if key == ord("]"):
                alpha = min(0.9, alpha + 0.1)
            if key == ord("s"):
                args.save_dir.mkdir(parents=True, exist_ok=True)
                p = args.save_dir / f"overlay_{saved:03d}.png"
                cv2.imwrite(str(p), disp)
                saved += 1
                print(f"  저장: {p}")
    except Exception as e:
        print(f"\n  ⚠️ 오류({type(e).__name__}: {e})")
    finally:
        try:
            blaze.StopGrabbing(); blaze.Close()
            ace2.StopGrabbing(); ace2.Close()
        except Exception:
            pass
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
