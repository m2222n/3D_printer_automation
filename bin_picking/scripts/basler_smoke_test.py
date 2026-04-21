#!/usr/bin/env python
"""
Basler 카메라 스모크 테스트 — 카메라 도착 당일 현장 검증용
===========================================================

목적: Blaze-112 + ace2 2대 카메라가 연결됐을 때
      최소한의 동작을 단계별로 확인하여 문제 지점을 빠르게 파악한다.

단계:
  1. pypylon import 확인
  2. TL Factory 초기화 + 장치 열거
  3. 예상 카메라 2대 (Blaze-112 + ace2) 존재 확인
  4. 각 카메라 Open / GenICam 노드 확인
  5. 1프레임 캡처 (depth / color)
  6. 프레임 통계 (유효 픽셀, 범위)
  7. /tmp/basler_smoke/ 에 저장 → save/load 라운드트립
  8. depth_to_pointcloud() 변환 테스트
  9. (옵션) main_pipeline.py --basler --load 파이프라인 통과

사용법:
    source .venv/binpick/bin/activate
    python bin_picking/scripts/basler_smoke_test.py
    python bin_picking/scripts/basler_smoke_test.py --skip-capture   # 장치 열거만
    python bin_picking/scripts/basler_smoke_test.py --out /tmp/my_test
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path


# ============================================================
# 로깅 헬퍼
# ============================================================
PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
INFO = "\033[94m[INFO]\033[0m"


def step(num: int, title: str) -> None:
    print()
    print("=" * 60)
    print(f"  STEP {num}. {title}")
    print("=" * 60)


def ok(msg: str) -> None:
    print(f"  {PASS} {msg}")


def fail(msg: str) -> None:
    print(f"  {FAIL} {msg}")


def warn(msg: str) -> None:
    print(f"  {WARN} {msg}")


def info(msg: str) -> None:
    print(f"  {INFO} {msg}")


# ============================================================
# 스모크 테스트
# ============================================================
class SmokeTestResult:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.warned: list[str] = []

    def add_pass(self, name: str) -> None:
        self.passed.append(name)

    def add_fail(self, name: str) -> None:
        self.failed.append(name)

    def add_warn(self, name: str) -> None:
        self.warned.append(name)

    def summary(self) -> None:
        print()
        print("=" * 60)
        print("  스모크 테스트 결과")
        print("=" * 60)
        print(f"  PASS: {len(self.passed)}")
        for p in self.passed:
            print(f"    + {p}")
        if self.warned:
            print(f"  WARN: {len(self.warned)}")
            for w in self.warned:
                print(f"    - {w}")
        if self.failed:
            print(f"  FAIL: {len(self.failed)}")
            for f in self.failed:
                print(f"    x {f}")
        print()
        if self.failed:
            print(f"  {FAIL} 실패 {len(self.failed)}건 — 조치 후 재실행")
            sys.exit(1)
        else:
            print(f"  {PASS} 전체 통과")


# ============================================================
# STEP 1: pypylon import
# ============================================================
def test_import(r: SmokeTestResult) -> "pylon":  # noqa: F821
    step(1, "pypylon import")
    try:
        from pypylon import pylon
        version = getattr(pylon, "__version__", "?")
        ok(f"pypylon import 성공 (version: {version})")
        r.add_pass("pypylon import")
        return pylon
    except ImportError as e:
        fail(f"pypylon import 실패: {e}")
        info("해결: pip install pypylon")
        r.add_fail("pypylon import")
        return None


# ============================================================
# STEP 2: TL Factory + 장치 열거
# ============================================================
def test_enumerate(pylon, r: SmokeTestResult) -> list:
    step(2, "TL Factory 초기화 + 장치 열거")
    try:
        tlf = pylon.TlFactory.GetInstance()
        devices = tlf.EnumerateDevices()
        info(f"감지된 장치 수: {len(devices)}")

        device_info = []
        for i, dev in enumerate(devices):
            entry = {
                "model": dev.GetModelName(),
                "serial": dev.GetSerialNumber(),
                "vendor": dev.GetVendorName(),
                "device_class": dev.GetDeviceClass(),
            }
            # GigE 카메라는 IP 있음
            try:
                entry["ip"] = dev.GetIpAddress()
            except Exception:
                entry["ip"] = "N/A"
            device_info.append(entry)
            print(
                f"    [{i}] {entry['model']} "
                f"(S/N: {entry['serial']}, {entry['device_class']}, IP: {entry['ip']})"
            )

        if len(devices) == 0:
            fail("카메라 0대 — 하드웨어/네트워크 확인")
            info("  - GigE 카메라 전원/케이블 확인")
            info("  - IP 동일 서브넷 (예: 192.168.10.x) 확인")
            info("  - 방화벽 (ufw): sudo ufw allow 3956/udp")
            r.add_fail("장치 열거")
            return []

        r.add_pass(f"장치 열거 ({len(devices)}대)")
        return device_info
    except Exception as e:
        fail(f"장치 열거 실패: {e}")
        traceback.print_exc()
        r.add_fail("장치 열거")
        return []


# ============================================================
# STEP 3: Blaze-112 + ace2 식별
# ============================================================
def test_identify(devices: list, r: SmokeTestResult) -> dict:
    step(3, "Blaze-112 + ace2 식별")

    blaze = None
    ace2 = None

    for dev in devices:
        model_lower = dev["model"].lower()
        if "blaze" in model_lower and blaze is None:
            blaze = dev
            ok(f"Blaze-112 감지: {dev['model']} (S/N: {dev['serial']})")
        elif ("a2a" in model_lower or "ace" in model_lower) and ace2 is None:
            ace2 = dev
            ok(f"ace2 감지: {dev['model']} (S/N: {dev['serial']})")

    if blaze is None:
        fail("Blaze-112 미감지 — 장치 모델명에 'blaze' 키워드 없음")
        r.add_fail("Blaze-112 식별")
    else:
        r.add_pass("Blaze-112 식별")

    if ace2 is None:
        warn("ace2 미감지 — Blaze 단독 모드로 진행 (RGB 없음)")
        r.add_warn("ace2 식별 (단독 모드)")
    else:
        r.add_pass("ace2 식별")

    return {"blaze": blaze, "ace2": ace2}


# ============================================================
# STEP 4: BaslerCapture.start()
# ============================================================
def test_start(r: SmokeTestResult):
    step(4, "BaslerCapture.start() — 카메라 열기")

    # sys.path 에 프로젝트 루트 추가
    project_root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(project_root))

    try:
        from bin_picking.src.acquisition.basler_capture import BaslerCapture
    except ImportError as e:
        fail(f"BaslerCapture import 실패: {e}")
        info(f"프로젝트 루트: {project_root}")
        r.add_fail("BaslerCapture import")
        return None

    cap = BaslerCapture()
    try:
        t0 = time.time()
        result = cap.start()
        elapsed = (time.time() - t0) * 1000
        info(f"start() 소요시간: {elapsed:.0f} ms")

        if result.get("blaze"):
            ok("Blaze-112 Open + StartGrabbing OK")
            r.add_pass("Blaze-112 start")
        else:
            fail("Blaze-112 start 실패")
            r.add_fail("Blaze-112 start")

        if result.get("ace2"):
            ok("ace2 Open + StartGrabbing OK")
            r.add_pass("ace2 start")
        else:
            warn("ace2 start 실패 또는 미연결 — 단독 모드")
            r.add_warn("ace2 start")

        return cap
    except Exception as e:
        fail(f"start() 실패: {e}")
        traceback.print_exc()
        r.add_fail("BaslerCapture.start()")
        try:
            cap.stop()
        except Exception:
            pass
        return None


# ============================================================
# STEP 5: 1프레임 캡처
# ============================================================
def test_capture(cap, r: SmokeTestResult):
    step(5, "1프레임 캡처")

    if cap is None:
        warn("start() 실패로 캡처 스킵")
        return None

    try:
        t0 = time.time()
        frames = cap.capture(timeout_ms=5000)
        elapsed = (time.time() - t0) * 1000
        info(f"capture() 소요시간: {elapsed:.0f} ms")

        # depth
        if frames.depth_map is not None:
            ok(f"depth: shape={frames.depth_map.shape}, dtype={frames.depth_map.dtype}")
            r.add_pass("depth 캡처")
        else:
            fail("depth None")
            r.add_fail("depth 캡처")

        # color
        if frames.color_image is not None:
            ok(f"color: shape={frames.color_image.shape}, dtype={frames.color_image.dtype}")
            r.add_pass("color 캡처")
        else:
            warn("color None (Blaze 단독 모드)")
            r.add_warn("color 캡처 (None)")

        # confidence
        if frames.confidence_map is not None:
            ok(f"confidence: shape={frames.confidence_map.shape}")
            r.add_pass("confidence 캡처")
        else:
            warn("confidence None — Blaze 멀티파트 미지원 또는 미설정")
            r.add_warn("confidence 캡처 (None)")

        return frames
    except Exception as e:
        fail(f"capture() 실패: {e}")
        traceback.print_exc()
        r.add_fail("capture()")
        return None


# ============================================================
# STEP 6: 프레임 통계
# ============================================================
def test_stats(frames, r: SmokeTestResult) -> None:
    step(6, "프레임 통계")

    if frames is None or frames.depth_map is None:
        warn("프레임 없음 - 스킵")
        return

    import numpy as np

    depth = frames.depth_map
    valid = depth > 0
    valid_pct = valid.mean() * 100

    info(f"유효 depth: {valid.sum():,} / {valid.size:,} ({valid_pct:.1f}%)")

    if valid.any():
        d_valid = depth[valid]
        info(f"depth 범위: {d_valid.min()} ~ {d_valid.max()} mm")
        info(f"depth 중앙값: {np.median(d_valid):.0f} mm")

        if valid_pct < 30:
            warn(f"유효 픽셀 {valid_pct:.1f}% - ToF 신호 약함 (조명/거리/반사 확인)")
            r.add_warn(f"유효 픽셀 {valid_pct:.1f}%")
        else:
            ok(f"유효 픽셀 {valid_pct:.1f}%")
            r.add_pass("depth 통계")

        # 작동거리 확인
        median_d = np.median(d_valid)
        if median_d < 300:
            warn(f"중앙값 {median_d:.0f}mm - 너무 가까움 (Blaze 최소 300mm)")
        elif median_d > 3000:
            warn(f"중앙값 {median_d:.0f}mm - 빈피킹 거리 벗어남 (권장 500~1500mm)")
    else:
        fail("유효 depth 0 - 카메라 노출/거리/렌즈 캡 확인")
        r.add_fail("depth 통계 (유효 0)")


# ============================================================
# STEP 7: save/load 라운드트립
# ============================================================
def test_save_load(frames, out_dir: Path, r: SmokeTestResult) -> None:
    step(7, f"save/load 라운드트립 → {out_dir}")

    if frames is None:
        warn("프레임 없음 - 스킵")
        return

    import numpy as np
    from bin_picking.src.acquisition.basler_capture import BaslerCapture

    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        frames.save(out_dir)
        ok(f"저장 완료: {out_dir}")

        loaded = BaslerCapture.load_frames(out_dir)

        if np.array_equal(loaded.depth_map, frames.depth_map):
            ok("depth 라운드트립 일치")
        else:
            fail("depth 라운드트립 불일치")
            r.add_fail("save/load depth")
            return

        if frames.color_image is not None:
            if np.array_equal(loaded.color_image, frames.color_image):
                ok("color 라운드트립 일치")
            else:
                fail("color 라운드트립 불일치")
                r.add_fail("save/load color")
                return

        r.add_pass("save/load 라운드트립")
    except Exception as e:
        fail(f"save/load 실패: {e}")
        traceback.print_exc()
        r.add_fail("save/load")


# ============================================================
# STEP 8: PointCloud 변환
# ============================================================
def test_pointcloud(cap, frames, r: SmokeTestResult) -> None:
    step(8, "depth → PointCloud 변환")

    if cap is None or frames is None:
        warn("카메라/프레임 없음 - 스킵")
        return

    try:
        pcd = cap.to_pointcloud(frames)
        n_pts = len(pcd.points) if hasattr(pcd, "points") else 0
        if n_pts > 0:
            ok(f"PointCloud 생성: {n_pts:,} 점")
            r.add_pass("PointCloud 변환")
        else:
            fail("PointCloud 0 점 - depth 유효성 문제")
            r.add_fail("PointCloud 변환")
    except Exception as e:
        fail(f"to_pointcloud() 실패: {e}")
        traceback.print_exc()
        r.add_fail("PointCloud 변환")


# ============================================================
# STEP 9: main_pipeline 통과 안내
# ============================================================
def test_pipeline_hint(out_dir: Path) -> None:
    step(9, "L1~L5 파이프라인 통과 안내")
    info("다음 명령어로 저장된 프레임으로 전체 파이프라인 실행:")
    print()
    print(f"    python bin_picking/src/main_pipeline.py \\")
    print(f"        --basler --load {out_dir} \\")
    print(f"        --save-viz /tmp/basler_smoke_viz")
    print()
    info("성공하면 L1~L5 전체 통과 + 시각화 PNG 생성")


# ============================================================
# MAIN
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Basler 카메라 스모크 테스트")
    parser.add_argument("--skip-capture", action="store_true",
                        help="장치 열거까지만 수행 (카메라 Open 안 함)")
    parser.add_argument("--out", type=str, default="/tmp/basler_smoke",
                        help="프레임 저장 경로 (기본 /tmp/basler_smoke)")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  Basler 스모크 테스트 - 2026-04-21")
    print("  대상: Blaze-112 (ToF) + ace2 (RGB 5MP)")
    print("=" * 60)

    r = SmokeTestResult()
    out_dir = Path(args.out)

    # STEP 1-3: import + 장치 열거
    pylon = test_import(r)
    if pylon is None:
        r.summary()
        return

    devices = test_enumerate(pylon, r)
    if not devices:
        r.summary()
        return

    identified = test_identify(devices, r)

    if args.skip_capture:
        info("--skip-capture - STEP 4 이후 스킵")
        r.summary()
        return

    # STEP 4-8: 카메라 open + 캡처
    cap = test_start(r)
    frames = test_capture(cap, r) if cap else None
    test_stats(frames, r)
    test_save_load(frames, out_dir, r)
    test_pointcloud(cap, frames, r)

    # 정리
    if cap is not None:
        try:
            cap.stop()
            ok("카메라 정상 종료")
        except Exception as e:
            warn(f"stop() 경고: {e}")

    # STEP 9
    test_pipeline_hint(out_dir)

    # 결과
    r.summary()


if __name__ == "__main__":
    main()
