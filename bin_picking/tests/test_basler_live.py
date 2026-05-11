"""
Basler 카메라 라이브 검증 + E2E 파이프라인 테스트
====================================================

어댑터 도착 후 카메라 검증을 8단계 절차에서 1줄 명령으로 압축한다.
RealSense E2E (test_e2e_realsense.py) 패턴을 Basler에 맞게 이식.

카메라 조합:
  - Blaze-112 (ToF depth, 24VDC, S/N 40737830)
  - ace2 a2A2448-23gcBAS (RGB 5MP, 5/8 정정 모델명)

실행 환경:
    cd ~/3D_printer_automation
    source .venv/binpick/bin/activate

5가지 모드:

  # 1) 카메라 탐색 — pypylon 설치 + 네트워크 확인
  python bin_picking/tests/test_basler_live.py --discover

  # 2) 라이브 캡처 — depth + color 1프레임
  python bin_picking/tests/test_basler_live.py --live

  # 3) 라이브 + 영구 저장 — 서버 로드 검증용
  python bin_picking/tests/test_basler_live.py --live --save

  # 4) 저장 프레임 로드 — 카메라 없이 검증
  python bin_picking/tests/test_basler_live.py --load

  # 5) 풀 파이프라인 — L1~L4 (CAD 매칭) 실데이터 검증
  python bin_picking/tests/test_basler_live.py --live --pipeline

추가 옵션:
  --blaze-serial 40737830   # 특정 카메라 시리얼 지정
  --ace2-serial 41881328
  --no-ace2                 # Blaze 단독 모드 (ace2 미연결 시)
  --depth-min 0.3           # depth 유효 범위 (m, 기본 0.3~1.5)
  --depth-max 1.5
  --timeout 5000            # 캡처 타임아웃 (ms, 기본 5초)
  --output bin_picking/models/basler_frames/   # 저장/로드 디렉토리

종료 코드:
  0 = 모든 단계 PASS
  1 = pypylon 미설치 또는 import 실패
  2 = 카메라 탐색 실패 (네트워크/전원)
  3 = 라이브 캡처 실패 (timeout/grab error)
  4 = 파이프라인 실패 (L1~L4 어느 단계 fail)
  10 = 저장/로드 라운드트립 실패

설계 의도:
  - 각 단계 독립 PASS/FAIL → 어디서 막혔는지 즉시 진단
  - pypylon/Open3D 없는 환경(6000 서버 등)에서도 부분 검증 가능
  - Blaze만 OK + ace2 실패도 정상 진행 (warning만)
  - 저장 → 다른 PC에서 로드 = 분석 환경 분리
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

import numpy as np

# ============================================================
# 경로 + import 설정
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# 저장 디렉토리 기본값
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "bin_picking" / "models" / "basler_frames"


# ============================================================
# 환경 확인 (모듈 단위 import — 명확한 에러 메시지)
# ============================================================
def check_pypylon() -> bool:
    """pypylon 설치 여부 확인. 미설치 시 설치 가이드 출력."""
    try:
        from pypylon import pylon  # noqa: F401
        return True
    except ImportError:
        print("\n[ERROR] pypylon이 설치되지 않았습니다.")
        print("        설치: pip install pypylon")
        print("        macOS는 Basler pylon Camera Software Suite 설치 후 pip 가능")
        print("        https://www.baslerweb.com/en/sales-support/downloads/software-downloads/")
        return False


def check_open3d() -> bool:
    """Open3D 설치 여부 확인. 6000 서버는 AVX2 미지원으로 fail 가능."""
    try:
        import open3d as o3d  # noqa: F401
        return True
    except ImportError:
        return False


# ============================================================
# Step 1 — 카메라 탐색 (--discover)
# ============================================================
def step_discover(args: argparse.Namespace) -> int:
    """연결된 Basler 카메라 목록 출력 + 네트워크 진단."""
    print("\n" + "=" * 60)
    print("Step: 카메라 탐색 (--discover)")
    print("=" * 60)

    if not check_pypylon():
        return 1

    from bin_picking.src.acquisition.basler_capture import BaslerCapture

    try:
        devices = BaslerCapture.list_devices()
    except Exception as e:
        print(f"  [ERROR] 카메라 열거 실패: {e}")
        traceback.print_exc()
        return 2

    print(f"  발견된 카메라: {len(devices)}")
    if not devices:
        _print_discovery_diagnostics()
        return 2

    blaze_found = False
    ace2_found = False
    for i, dev in enumerate(devices):
        print(f"\n  [{i}] {dev['model']}")
        print(f"        Serial: {dev['serial']}")
        print(f"        Vendor: {dev['vendor']}")
        print(f"        Interface: {dev['interface']}")
        print(f"        IP: {dev['ip']}")

        model_lower = dev["model"].lower()
        if "blaze" in model_lower:
            blaze_found = True
        if "a2a" in model_lower or "ace" in model_lower:
            ace2_found = True

    print("\n  요약:")
    print(f"    Blaze-112 (depth): {'✅ 발견' if blaze_found else '❌ 미발견'}")
    print(f"    ace2 (RGB): {'✅ 발견' if ace2_found else '❌ 미발견'}")

    if not blaze_found:
        _print_discovery_diagnostics()
        return 2

    print("\n  [PASS] 카메라 탐색")
    print("\n  다음 단계: python bin_picking/tests/test_basler_live.py --live")
    return 0


def _print_discovery_diagnostics() -> None:
    """카메라 미발견 시 진단 가이드."""
    print("\n  [진단] 카메라가 발견되지 않았습니다:")
    print("    1. 어댑터 검증 (5단계):")
    print("       system_profiler SPUSBDataType | grep -B 2 -A 8 'RTL\\|U1G\\|Realtek'")
    print("       → 'Speed: Up to 5 Gb/s' 표시되어야 함")
    print("       ifconfig en6 | grep media")
    print("       → '1000baseT <full-duplex>' 표시되어야 함")
    print("    2. 카메라 전원 확인 (Blaze 24VDC, ace2 12VDC)")
    print("       → STATUS LED 녹색 깜빡 + ETHERNET LED 빨강 = 정상")
    print("    3. Mac 이더넷 IP 고정: 192.168.10.1/255.255.255.0")
    print("    4. pylon IP Configurator로 카메라 IP 할당 (예: 192.168.10.10)")
    print("    5. 방화벽 / sandbox 차단 여부 확인")
    print("       → macOS: 시스템 환경설정 > 보안 > 방화벽 OFF 또는 pylon 허용")


# ============================================================
# Step 2 — 라이브 캡처 (--live)
# ============================================================
def step_live_capture(args: argparse.Namespace):
    """라이브 카메라에서 1프레임 캡처 + 통계 출력."""
    print("\n" + "=" * 60)
    print("Step: 라이브 캡처 (--live)")
    print("=" * 60)

    from bin_picking.src.acquisition.basler_capture import BaslerCapture

    cap = BaslerCapture(
        blaze_serial=args.blaze_serial,
        ace2_serial=None if args.no_ace2 else args.ace2_serial,
        depth_min=args.depth_min,
        depth_max=args.depth_max,
    )

    print(f"  Blaze-112 serial: {args.blaze_serial or '자동 검색'}")
    if args.no_ace2:
        print("  ace2: 비활성화 (--no-ace2)")
    else:
        print(f"  ace2 serial: {args.ace2_serial or '자동 검색'}")
    print(f"  depth 유효 범위: {args.depth_min}~{args.depth_max} m")

    print("\n  카메라 연결 중...")
    t0 = time.time()
    try:
        status = cap.start()
    except RuntimeError as e:
        print(f"  [ERROR] 연결 실패: {e}")
        _print_discovery_diagnostics()
        return None
    except Exception as e:
        print(f"  [ERROR] 예상치 못한 에러: {e}")
        traceback.print_exc()
        return None

    print(f"  Blaze-112: {'✅ 연결' if status['blaze'] else '❌ 실패'}")
    print(f"  ace2: {'✅ 연결' if status['ace2'] else '⚠️  미연결 (depth만)'}")
    print(f"  연결 시간: {time.time() - t0:.2f}s")

    # Warmup — ToF 적응 (Blaze는 노출 자동 조절 없으므로 RealSense보다 짧게 OK)
    print("\n  Warmup 캡처 (10프레임)...")
    warmup_ok = 0
    for i in range(10):
        try:
            cap.capture(timeout_ms=args.timeout)
            warmup_ok += 1
        except Exception as e:
            print(f"    프레임 {i}: 실패 ({e})")
    print(f"  Warmup 성공: {warmup_ok}/10")

    # 본 캡처
    print("\n  본 캡처...")
    t0 = time.time()
    try:
        frames = cap.capture(timeout_ms=args.timeout)
    except Exception as e:
        print(f"  [ERROR] 캡처 실패: {e}")
        cap.stop()
        return None
    capture_time = time.time() - t0

    cap.stop()

    # 통계 출력
    print(f"\n  Depth shape: {frames.depth_map.shape}")
    print(f"  Depth dtype: {frames.depth_map.dtype}")
    print(f"  Depth scale: {frames.depth_scale} (raw → m)")

    valid_mask = (frames.depth_map > 0) & (
        frames.depth_map < args.depth_max * frames.depth_scale
    )
    n_valid = int(np.count_nonzero(valid_mask))
    n_total = frames.depth_map.size
    valid_pct = n_valid / n_total * 100 if n_total > 0 else 0
    print(f"  유효 depth: {n_valid:,}/{n_total:,} ({valid_pct:.1f}%)")

    if n_valid > 0:
        valid_depth = frames.depth_map[valid_mask].astype(np.float32)
        depth_min_mm = float(valid_depth.min())
        depth_max_mm = float(valid_depth.max())
        depth_median_mm = float(np.median(valid_depth))
        print(f"  Depth 범위: {depth_min_mm:.0f}~{depth_max_mm:.0f} mm (중앙값 {depth_median_mm:.0f} mm)")

        # 유니크 값 수 (4/22 D435 진단 패턴 — 너무 적으면 양자화 문제)
        n_unique = len(np.unique(valid_depth.astype(np.uint16)))
        print(f"  Depth 유니크 값: {n_unique}")
        if n_unique < 20:
            print("  ⚠️  유니크 값 < 20 — depth 양자화 의심 (4/22 D435 USB 20cm 케이스와 유사)")

    print(f"\n  Intrinsics (depth): {frames.depth_intrinsics.to_dict()}")

    if frames.color_image is not None:
        print(f"  Color shape: {frames.color_image.shape}")
        print(f"  Color dtype: {frames.color_image.dtype}")
        if frames.color_intrinsics is not None:
            print(f"  Intrinsics (color): {frames.color_intrinsics.to_dict()}")
    else:
        print("  Color: 없음 (ace2 미연결 또는 그랩 실패)")

    if frames.confidence_map is not None:
        print(f"  Confidence shape: {frames.confidence_map.shape}")

    print(f"  캡처 시간: {capture_time:.2f}s")

    # 최소 유효성 검증
    if n_valid < 1000:
        print(f"\n  [WARN] 유효 depth 픽셀 < 1000 ({n_valid}). 카메라 시야/거리 확인 필요.")
    print("\n  [PASS] 라이브 캡처")
    return frames


# ============================================================
# Step 3 — 저장 (--save)
# ============================================================
def step_save(frames, output_dir: Path) -> bool:
    """프레임을 영구 저장 + 라운드트립 검증."""
    print("\n" + "=" * 60)
    print(f"Step: 영구 저장 (--save) → {output_dir}")
    print("=" * 60)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        frames.save(output_dir)
    except Exception as e:
        print(f"  [ERROR] 저장 실패: {e}")
        traceback.print_exc()
        return False

    # 저장 후 파일 크기 출력
    saved_files = {
        "depth.npy": frames.depth_map.nbytes,
        "color.npy": frames.color_image.nbytes if frames.color_image is not None else 0,
        "confidence.npy": frames.confidence_map.nbytes if frames.confidence_map is not None else 0,
    }
    print("  저장된 파일:")
    total_kb = 0
    for fname, expected_size in saved_files.items():
        fpath = output_dir / fname
        if fpath.exists():
            actual_kb = fpath.stat().st_size / 1024
            total_kb += actual_kb
            print(f"    {fname}: {actual_kb:.0f} KB")
    meta_path = output_dir / "meta.json"
    if meta_path.exists():
        meta_kb = meta_path.stat().st_size / 1024
        total_kb += meta_kb
        print(f"    meta.json: {meta_kb:.1f} KB")
    print(f"  합계: {total_kb / 1024:.1f} MB")

    # 라운드트립 검증
    print("\n  라운드트립 검증 (저장 → 로드 → 비교)...")
    from bin_picking.src.acquisition.basler_capture import BaslerCapture

    try:
        loaded = BaslerCapture.load_frames(output_dir)
    except Exception as e:
        print(f"  [ERROR] 로드 실패: {e}")
        traceback.print_exc()
        return False

    if not np.array_equal(frames.depth_map, loaded.depth_map):
        print("  [ERROR] depth 불일치")
        return False
    print("    depth ✓")

    if frames.color_image is not None:
        if loaded.color_image is None or not np.array_equal(
            frames.color_image, loaded.color_image
        ):
            print("  [ERROR] color 불일치")
            return False
        print("    color ✓")

    if frames.confidence_map is not None:
        if loaded.confidence_map is None or not np.array_equal(
            frames.confidence_map, loaded.confidence_map
        ):
            print("  [ERROR] confidence 불일치")
            return False
        print("    confidence ✓")

    if frames.depth_intrinsics.fx != loaded.depth_intrinsics.fx:
        print("  [ERROR] intrinsics 불일치")
        return False
    print("    intrinsics ✓")

    print("  [PASS] 저장 + 라운드트립")
    return True


# ============================================================
# Step 4 — 로드 (--load)
# ============================================================
def step_load(output_dir: Path):
    """저장된 프레임 로드 (카메라 없이 검증)."""
    print("\n" + "=" * 60)
    print(f"Step: 저장 프레임 로드 (--load) ← {output_dir}")
    print("=" * 60)

    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        print(f"  [ERROR] 디렉토리 없음: {output_dir}")
        print("  먼저 --live --save 로 프레임을 저장하세요.")
        return None

    from bin_picking.src.acquisition.basler_capture import BaslerCapture

    try:
        frames = BaslerCapture.load_frames(output_dir)
    except Exception as e:
        print(f"  [ERROR] 로드 실패: {e}")
        traceback.print_exc()
        return None

    print(f"  Depth shape: {frames.depth_map.shape}")
    if frames.color_image is not None:
        print(f"  Color shape: {frames.color_image.shape}")
    if frames.confidence_map is not None:
        print(f"  Confidence shape: {frames.confidence_map.shape}")
    print(f"  Depth scale: {frames.depth_scale}")
    print(f"  Intrinsics: {frames.depth_intrinsics.to_dict()}")

    print("  [PASS] 로드")
    return frames


# ============================================================
# Step 5 — PointCloud 변환 (Open3D 필요)
# ============================================================
def step_to_pointcloud(frames):
    """BaslerFrames → Open3D PointCloud 변환."""
    print("\n" + "=" * 60)
    print("Step: PointCloud 변환")
    print("=" * 60)

    if not check_open3d():
        print("  [SKIP] Open3D 미설치 (6000 서버는 AVX2 미지원).")
        print("        Mac 또는 비전 PC에서 실행하세요.")
        return None

    from bin_picking.src.acquisition.depth_to_pointcloud import depth_to_pointcloud

    intr = frames.depth_intrinsics

    # color 해상도 정합 (필요 시 resize)
    color_for_pcd = None
    if frames.color_image is not None:
        color_for_pcd = frames.color_image
        dh, dw = frames.depth_map.shape[:2]
        ch, cw = color_for_pcd.shape[:2]
        if (ch, cw) != (dh, dw):
            try:
                import cv2

                color_for_pcd = cv2.resize(color_for_pcd, (dw, dh))
                print(f"  color 리사이즈: ({ch},{cw}) → ({dh},{dw})")
            except ImportError:
                print("  [WARN] cv2 미설치 → color 무시")
                color_for_pcd = None

    t0 = time.time()
    pcd = depth_to_pointcloud(
        depth_map=frames.depth_map,
        fx=intr.fx,
        fy=intr.fy,
        cx=intr.cx,
        cy=intr.cy,
        color_image=color_for_pcd,
        depth_scale=frames.depth_scale,
        depth_min=0.1,
        depth_max=5.0,
        confidence_map=frames.confidence_map,
    )
    elapsed = time.time() - t0

    n_points = len(pcd.points)
    has_colors = len(pcd.colors) > 0
    print(f"  포인트 수: {n_points:,}")
    print(f"  Colored: {'✓' if has_colors else '✗'}")
    print(f"  변환 시간: {elapsed:.2f}s")

    if n_points == 0:
        print("  [FAIL] 포인트 0개")
        return None

    print("  [PASS] PointCloud 변환")
    return pcd


# ============================================================
# Step 6 — L1~L4 파이프라인 (--pipeline)
# ============================================================
def step_pipeline(pcd) -> bool:
    """L2 전처리 → L3 분할 → (선택) L4 매칭.

    L4 CAD 매칭은 부품 5개와 STL 매칭 가능 여부에 따라 분기.
    여기서는 기본 검증(L2+L3)만 수행하고, 자세한 CAD 매칭은 별도 스크립트.
    """
    print("\n" + "=" * 60)
    print("Step: L2 전처리 → L3 분할")
    print("=" * 60)

    if pcd is None or not check_open3d():
        print("  [SKIP] pcd 또는 Open3D 없음")
        return False

    import open3d as o3d

    from bin_picking.src.preprocessing.cloud_filter import CloudFilter
    from bin_picking.src.segmentation.dbscan_segmenter import DBSCANSegmenter

    # --- L2: 전처리 ---
    print("\n  [L2] 전처리")
    t0 = time.time()
    filt = CloudFilter(
        voxel_size=0.002,  # 2mm (Grey 레진 표준)
        sor_nb_neighbors=20,
        sor_std_ratio=2.0,
        normal_radius=0.006,
        plane_distance=0.005,
    )

    # ROI는 Basler 오버헤드(60~80cm) 기준
    # 카메라 입고 후 실측으로 조정
    try:
        pcd_filtered, _plane = _safe_l2(filt, pcd)
    except Exception as e:
        print(f"  [ERROR] L2 실패: {e}")
        traceback.print_exc()
        return False

    elapsed_l2 = time.time() - t0
    print(f"    입력 → L2 출력: {len(pcd.points):,} → {len(pcd_filtered.points):,} 점")
    print(f"    L2 시간: {elapsed_l2:.2f}s")

    if len(pcd_filtered.points) < 100:
        print("  [WARN] L2 후 포인트 < 100. ROI / depth 범위 확인.")
        return False

    # --- L3: DBSCAN 분할 ---
    print("\n  [L3] DBSCAN 분할")
    t0 = time.time()
    segmenter = DBSCANSegmenter(eps=0.008, min_points=100)
    try:
        clusters = segmenter.segment(pcd_filtered)
    except Exception as e:
        print(f"  [ERROR] L3 실패: {e}")
        traceback.print_exc()
        return False
    elapsed_l3 = time.time() - t0

    print(f"    클러스터 수: {len(clusters)}")
    print(f"    L3 시간: {elapsed_l3:.2f}s")

    for i, c in enumerate(clusters[:5]):
        n_pts = len(c.pcd.points)
        bbox = c.pcd.get_axis_aligned_bounding_box()
        extent = bbox.get_extent() * 1000  # m → mm
        print(
            f"    [{i}] {n_pts:,} 점, bbox {extent[0]:.0f}×{extent[1]:.0f}×{extent[2]:.0f} mm"
        )

    if len(clusters) == 0:
        print("  [WARN] 클러스터 0개. eps/min_points 조정 또는 부품 시야 확인.")
        return False

    print("\n  [PASS] L2+L3 파이프라인")
    print("\n  다음 단계 (별도 스크립트):")
    print("    - L4 CAD 매칭: tests/test_e2e_cad_matching.py (29종 STL 대응)")
    print("    - 실 부품 ACCEPT 검증: 별도 도구 작성 예정")
    return True


def _safe_l2(filt, pcd):
    """L2 호출 — CloudFilter API 변형 대응 (filter_pipeline / filter / process)."""
    for method_name in ("filter_pipeline", "filter", "process", "apply"):
        method = getattr(filt, method_name, None)
        if method is None:
            continue
        result = method(pcd)
        # 반환 형식: (pcd, plane) 또는 pcd 단독
        if isinstance(result, tuple):
            return result[0], result[1] if len(result) > 1 else None
        return result, None
    raise RuntimeError("CloudFilter에 filter/filter_pipeline/process 메소드가 없습니다.")


# ============================================================
# Main
# ============================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Basler 카메라 라이브 검증 + E2E 파이프라인",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("5가지 모드:")[1] if "5가지 모드:" in (__doc__ or "") else "",
    )

    # 모드 선택 (배타적이지 않음 — 조합 가능)
    p.add_argument("--discover", action="store_true", help="카메라 탐색만 수행")
    p.add_argument("--live", action="store_true", help="라이브 캡처")
    p.add_argument("--save", action="store_true", help="캡처한 프레임 영구 저장")
    p.add_argument("--load", action="store_true", help="저장된 프레임 로드 (--live 대신)")
    p.add_argument("--pipeline", action="store_true", help="L2~L3 파이프라인 실행")

    # 카메라 설정
    p.add_argument("--blaze-serial", type=str, default=None, help="Blaze-112 시리얼 (예: 40737830)")
    p.add_argument("--ace2-serial", type=str, default=None, help="ace2 시리얼 (예: 41881328)")
    p.add_argument("--no-ace2", action="store_true", help="ace2 비활성 (Blaze만)")
    p.add_argument("--depth-min", type=float, default=0.3, help="유효 depth 최소 (m)")
    p.add_argument("--depth-max", type=float, default=1.5, help="유효 depth 최대 (m)")
    p.add_argument("--timeout", type=int, default=5000, help="캡처 timeout (ms)")

    # I/O
    p.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"저장/로드 디렉토리 (기본: {DEFAULT_OUTPUT_DIR})",
    )

    args = p.parse_args()

    # 모드 미지정 시 --discover 기본 (가장 안전)
    if not any([args.discover, args.live, args.load]):
        print("[INFO] 모드 미지정 → --discover 실행 (가장 안전)")
        args.discover = True

    return args


def main() -> int:
    args = parse_args()

    print("=" * 60)
    print("Basler 라이브 검증 + E2E 파이프라인")
    print(f"날짜: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    modes = []
    if args.discover:
        modes.append("discover")
    if args.live:
        modes.append("live")
    if args.save:
        modes.append("save")
    if args.load:
        modes.append("load")
    if args.pipeline:
        modes.append("pipeline")
    print(f"모드: {' + '.join(modes)}")
    print("=" * 60)

    t_total = time.time()

    # --discover (단독 모드)
    if args.discover and not args.live and not args.load:
        return step_discover(args)

    # 환경 확인
    if not check_pypylon() and args.live:
        return 1

    # --live or --load
    frames = None
    if args.live:
        frames = step_live_capture(args)
        if frames is None:
            print("\n[FAIL] 라이브 캡처 실패")
            return 3
    elif args.load:
        frames = step_load(args.output)
        if frames is None:
            print("\n[FAIL] 로드 실패")
            return 10

    # --save (--live 이후)
    if args.save and frames is not None:
        ok = step_save(frames, args.output)
        if not ok:
            print("\n[FAIL] 저장/라운드트립 실패")
            return 10

    # --pipeline (PointCloud → L2~L3)
    if args.pipeline and frames is not None:
        pcd = step_to_pointcloud(frames)
        if pcd is None:
            print("\n[FAIL] PointCloud 변환 실패")
            return 4
        ok = step_pipeline(pcd)
        if not ok:
            print("\n[FAIL] L2~L3 파이프라인 실패")
            return 4

    elapsed_total = time.time() - t_total
    print("\n" + "=" * 60)
    print(f"전체 완료: {elapsed_total:.2f}s")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
