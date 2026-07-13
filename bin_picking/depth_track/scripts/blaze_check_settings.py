#!/usr/bin/env python3
"""Blaze 카메라 depth 설정값 진단 (촬영 X, 읽기만).
실행: sudo python blaze_check_settings.py --ip <BLAZE_IP>
목적: OperatingMode(ShortRange 적용여부), Scan3dCoordinateScale(3.5배 스케일 근원),
      실제 한 프레임의 depth median(m)까지 확인해 45~50cm 정합 여부 눈으로 검증.
"""
import argparse, sys
try:
    from pypylon import pylon
except Exception as e:
    sys.exit("pypylon import 실패: %s  (blaze capture 돌리던 그 venv에서 실행)" % e)

import numpy as np


def read_node(cam, name):
    """노드 값 안전하게 읽기. 없거나 못 읽으면 사유 반환."""
    try:
        node = getattr(cam, name)
    except Exception as e:
        return f"(노드 없음: {type(e).__name__})"
    for getter in ("GetValue", "ToString"):
        try:
            return getattr(node, getter)()
        except Exception:
            continue
    return "(값 읽기 실패)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True, help="Blaze 카메라 IP")
    ap.add_argument("--grab", action="store_true", default=True,
                    help="프레임 1장 잡아 depth median 확인 (기본 on)")
    ap.add_argument("--set-shortrange", dest="set_shortrange", action="store_true",
                    help="ShortRange 강제 적용 후 재확인 + 시험 프레임 (근접 45~50cm 품질 확인)")
    args = ap.parse_args()

    tl = pylon.TlFactory.GetInstance(); tl.CreateTl("BaslerGigE")
    di = pylon.CDeviceInfo(); di.SetIpAddress(args.ip); di.SetDeviceClass("BaslerGigE")
    cam = pylon.InstantCamera(tl.CreateDevice(di)); cam.Open()

    info = cam.GetDeviceInfo()
    print("=" * 60)
    print("연결:", info.GetModelName(), info.GetIpAddress())
    print("=" * 60)

    # Range 컴포넌트 활성 (depth)
    try:
        cam.ComponentSelector.SetValue("Range"); cam.ComponentEnable.SetValue(True)
    except Exception as e:
        print("Range 활성 경고:", e)

    # ⭐ ShortRange 강제 적용 (7/6: LongRange로 찍혀 g2·g3 품질저하 발견 → 근접 45~50cm는 ShortRange가 정확)
    if getattr(args, "set_shortrange", False):
        print("\n[ShortRange 강제 적용 시도]")
        before = read_node(cam, "OperatingMode")
        try:
            cam.OperatingMode.SetValue("ShortRange")
            after = read_node(cam, "OperatingMode")
            if after == "ShortRange":
                print(f"  ✅ 성공: {before} → {after}")
            else:
                print(f"  🔴 실패: {before} → {after} (여전히 ShortRange 아님)")
        except Exception as e:
            print(f"  🔴 SetValue 예외: {type(e).__name__}: {e}")

    print("\n[핵심 depth 노드 실제값]")
    for name in [
        "OperatingMode",              # ShortRange 여부  ← 3.5배 스케일 핵심
        "Scan3dCoordinateScale",      # raw→mm 변환 배율  ← 3.5배 근원
        "Scan3dCoordinateOffset",
        "Scan3dDistanceUnit",
        "Scan3dOutputMode",
        "PixelFormat",
        "DepthMin", "DepthMax",       # 측정 범위
        "ExposureTime",
        "Scan3dConfidenceThreshold",
    ]:
        print(f"  {name:28s} = {read_node(cam, name)}")

    # OperatingMode 선택 가능한 값(enum) 확인 → ShortRange 지원 여부
    try:
        entries = cam.OperatingMode.Symbolics
        print(f"\n  OperatingMode 선택가능 = {list(entries)}")
    except Exception:
        pass

    # 프레임 1장 잡아 실제 depth 확인
    if args.grab:
        print("\n[프레임 1장 depth 확인]")
        try:
            cam.StartGrabbingMax(1)
            res = cam.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
            if res.GrabSucceeded():
                arr = res.Array
                print("  raw dtype/shape:", arr.dtype, arr.shape)
                v = arr[arr > 0].astype(np.float32)
                if v.size:
                    print("  raw>0  min/med/max:", int(v.min()), int(np.median(v)), int(v.max()))
                    # 조교 변환식 (uint16 * 10/65535) 기준 meter
                    m = v * (10.0 / 65535.0)
                    print("  →meter(x10/65535) min/med/max: %.3f / %.3f / %.3f"
                          % (m.min(), float(np.median(m)), m.max()))
                    print("  (45~50cm=0.45~0.50 이면 정합. 다르면 스케일/모드 점검)")
                else:
                    print("  유효 depth 픽셀 없음 (부품 안 놓였거나 confidence 필터)")
            res.Release()
            cam.StopGrabbing()
        except Exception as e:
            print("  grab 실패:", e)

    cam.Close()
    print("\n완료.")


if __name__ == "__main__":
    main()
