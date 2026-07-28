"""
Blaze depth 진단 — 카메라가 실제로 무엇을 보내는지 확인
=========================================================

⭐ 왜 (7/28): RGB-D 오버레이가 물체와 무관한 줄무늬로 나왔다. extrinsic이 조금
   틀린 게 아니라 **depth 값 자체가 이상하다**는 뜻인데, 원인 후보가 여럿이다:
     ① Range 컴포넌트 전환 실패 → intensity(밝기)가 depth 자리에 들어옴
     ② 스케일 오해 → 값 단위가 mm가 아님
     ③ 멀티파트(Range+Intensity 동시) → 엉뚱한 배열을 집음
   추측하지 말고 **실제 배열을 찍어서** 가른다.

사용:
    python bin_picking/tests/diag_blaze_depth.py --ip 192.168.20.10
"""
from __future__ import annotations

import argparse
import os

import numpy as np


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=os.environ.get("BASLER_BLAZE_IP", "192.168.20.10"))
    ap.add_argument("--frames", type=int, default=3)
    args = ap.parse_args()

    from pypylon import pylon

    tlf = pylon.TlFactory.GetInstance()
    gige = tlf.CreateTl("BaslerGigE")
    target = None
    for d in gige.EnumerateAllDevices():
        if d.IsIpAddressAvailable() and d.GetIpAddress() == args.ip:
            target = d
            break
    if target is None:
        target = pylon.DeviceInfo()
        target.SetIpAddress(args.ip)
        target.SetDeviceClass("BaslerGigE")
    cam = pylon.InstantCamera(tlf.CreateDevice(target))
    cam.Open()
    nm = cam.GetNodeMap()

    print("=" * 60)
    print("1) 컴포넌트 상태 (전환 전)")
    print("=" * 60)
    try:
        cs = nm.GetNode("ComponentSelector")
        ce = nm.GetNode("ComponentEnable")
        for comp in ("Range", "Intensity", "Confidence"):
            try:
                cs.FromString(comp)
                print(f"  {comp:12s} enabled={ce.GetValue()}")
            except Exception as e:
                print(f"  {comp:12s} 조회 실패: {e}")
    except Exception as e:
        print(f"  ⚠️ ComponentSelector 없음: {e}")

    print("\n2) Range만 켜기")
    ok_range = False
    try:
        cs.FromString("Intensity"); ce.SetValue(False)
        cs.FromString("Confidence"); ce.SetValue(False)
    except Exception as e:
        print(f"  (Intensity/Confidence 끄기 일부 실패: {e})")
    try:
        cs.FromString("Range"); ce.SetValue(True)
        ok_range = True
        print("  ✅ Range=True 설정 성공")
    except Exception as e:
        print(f"  🚨 Range 전환 실패: {e}  ← 이게 원인이면 intensity가 depth 자리에 옴")

    # 픽셀 포맷 확인 — Coord3D_C16(mm) 이어야 깊이값
    for name in ("PixelFormat", "ImageComponentPixelFormat", "Scan3dCoordinateScale",
                 "Scan3dCoordinateOffset", "DepthMin", "DepthMax"):
        try:
            n = nm.GetNode(name)
            if n is not None:
                try:
                    v = n.GetValue()
                except Exception:
                    v = n.ToString()
                print(f"  {name} = {v}")
        except Exception:
            pass

    print("\n3) 실제 프레임 내용")
    print("=" * 60)
    cam.MaxNumBuffer.SetValue(10)
    cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    got = 0
    try:
        for _ in range(args.frames * 10):
            if got >= args.frames:
                break
            res = cam.RetrieveResult(2000, pylon.TimeoutHandling_Return)
            if res is None or not res.GrabSucceeded():
                if res is not None:
                    res.Release()
                continue
            try:
                arr = res.Array.copy()
                pf = str(res.GetPixelType())
            except Exception as e:
                print(f"  프레임 스킵 (Array 실패: {e})")
                res.Release()
                continue
            res.Release()
            got += 1

            a = arr.astype(np.float64)
            nz = a[a > 0]
            print(f"\n  [프레임 {got}] shape={arr.shape} dtype={arr.dtype} pixeltype={pf}")
            print(f"    전체 min={a.min():.0f} max={a.max():.0f} mean={a.mean():.0f}")
            if nz.size:
                print(f"    0 제외: min={nz.min():.0f} max={nz.max():.0f} "
                      f"중앙={np.median(nz):.0f} (개수 {nz.size:,}/{a.size:,})")
            # 중앙 부근 실제 값 — 카메라 앞 물체까지 거리와 비교할 것
            h, w = arr.shape[:2]
            patch = a[h//2-2:h//2+3, w//2-2:w//2+3]
            print(f"    화면 중앙 5×5 중앙값 = {np.median(patch):.0f}")

            print("    → 판정:")
            if arr.dtype == np.uint8:
                print("       🚨 uint8 = depth가 아님(밝기 영상). Range 전환 실패 확정.")
            elif nz.size and 200 <= np.median(nz) <= 5000:
                print("       ✅ mm 단위 거리로 보임 (200~5000mm 범위)")
            elif nz.size and np.median(nz) < 200:
                print("       ⚠️ 값이 너무 작음 — 단위가 mm가 아니거나 스케일 필요")
            else:
                print("       ⚠️ 값이 범위 밖 — 스케일/포맷 확인 필요")
    finally:
        cam.StopGrabbing()
        cam.Close()

    print("\n" + "=" * 60)
    print("판정 가이드: 화면 중앙 값이 '실제 카메라~물체 거리(mm)'와 비슷해야 정상.")
    print("  예) 벽까지 1m면 중앙값이 ~1000 이어야 함.")
    print("  전혀 다르면 depth가 아니라 다른 컴포넌트가 오고 있는 것.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
