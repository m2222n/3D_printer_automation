"""
Basler 카메라 wrapper for YOLO track (트랙 2).

협력사 인계받은 `realsense_pure_python.py`의 인터페이스 패턴을
우리 Basler 환경에 맞춰 적용. 기존 `bin_picking.src.acquisition.basler_capture.BaslerCapture`를
감싸서 단순한 `get_frames()` 3-tuple 반환 API 제공.

협력사 RealSenseCamera 인터페이스 호환:
    cam = BaslerWrapper()
    color_img, depth_obj, depth_np = cam.get_frames()
    intrinsics_dict = cam.intrinsics       # {"fx","fy","ppx","ppy","width","height"}
    cam.release()

차이점:
    - 협력사 RealSense는 BGR8 align(depth→color). 우리 Blaze는 ToF 단독 → color는 ACE2 별도
    - ACE2 미연결 환경에서는 depth만 사용 가능 (`get_frames()` color=None)
    - intrinsics 키 이름: ppx/ppy = cx/cy (호환 + 내부 cx/cy 둘 다 지원)

ACE2 셋업 후 듀얼 캡처로 확장 예정.
실 실행은 Mac venv binpick에서 (Basler pypylon은 macOS 검증됨).

작성 이력:
    - 5/19 W21 화 KAIST 점심/저녁 (Phase 2.1)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

# 기존 BaslerCapture 재활용 — 5/12 macOS 검증된 코드
from bin_picking.src.acquisition.basler_capture import (
    BaslerCapture,
    BaslerFrames,
    BaslerIntrinsics,
)

logger = logging.getLogger(__name__)


class BaslerWrapper:
    """
    협력사 RealSenseCamera 패턴을 따르는 Basler wrapper.

    내부적으로 기존 `BaslerCapture`를 사용. YOLO 트랙 메인 파이프라인이
    카메라 종류에 무관하게 동일 인터페이스로 사용할 수 있도록 한다.

    Args:
        use_ace2: ACE2 RGB 동시 캡처 (False면 Blaze depth만)
        depth_only_fallback: ACE2 캡처 실패 시 Blaze만으로 진행 (True 권장)
        blaze_serial: Blaze 시리얼 명시. None이면 BASLER_BLAZE_IP 환경변수 또는 자동 검색
        ace2_serial: ACE2 시리얼. None이면 자동 검색

    환경변수:
        BASLER_BLAZE_IP — Blaze 직접 IP. Mac 검증 시 사용
        BASLER_ACE2_IP — ACE2 직접 IP

    Note:
        ToF Blaze는 align(depth→color) 같은 RealSense 정렬 함수가 없다.
        ACE2가 다른 카메라이므로 두 시점이 다름. 정밀 align은 ChArUco
        캘리브레이션으로 별도 처리 (calibration/handeye_calibration.py).
    """

    def __init__(
        self,
        use_ace2: bool = False,
        depth_only_fallback: bool = True,
        blaze_serial: Optional[str] = None,
        ace2_serial: Optional[str] = None,
    ):
        self.use_ace2 = use_ace2
        self.depth_only_fallback = depth_only_fallback

        self._capture = BaslerCapture(
            blaze_serial=blaze_serial,
            ace2_serial=ace2_serial if use_ace2 else None,
        )
        self._started = False

        # intrinsics는 start() 이후 cached
        self._intrinsics_cache: Optional[dict] = None

    def start(self) -> dict:
        """카메라 스트리밍 시작.

        Returns:
            intrinsics 딕셔너리 (협력사 호환 키: fx/fy/ppx/ppy/width/height)
        """
        info = self._capture.start()
        self._started = True

        # 협력사 RealSenseCamera 인터페이스 호환을 위해 변환
        # 우리는 cx/cy 사용, 협력사은 ppx/ppy 사용
        depth_intr: BaslerIntrinsics = self._capture.depth_intrinsics
        self._intrinsics_cache = {
            "fx": depth_intr.fx,
            "fy": depth_intr.fy,
            "ppx": depth_intr.cx,   # 협력사 호환 (RealSense principal point x)
            "ppy": depth_intr.cy,   # 협력사 호환 (RealSense principal point y)
            "cx": depth_intr.cx,    # 우리 내부 표준
            "cy": depth_intr.cy,
            "width": depth_intr.width,
            "height": depth_intr.height,
            "intrinsics_version": depth_intr.version,
        }

        logger.info(
            "BaslerWrapper started: %dx%d, fx=%.1f, cx=%.1f, version=%s",
            depth_intr.width, depth_intr.height,
            depth_intr.fx, depth_intr.cx, depth_intr.version,
        )
        return self._intrinsics_cache

    @property
    def intrinsics(self) -> dict:
        """카메라 내부 파라미터 (협력사 호환 dict)."""
        if self._intrinsics_cache is None:
            raise RuntimeError("Call start() first before accessing intrinsics")
        return self._intrinsics_cache

    def get_frames(self, timeout_ms: int = 5000):
        """
        프레임 캡처. 협력사 RealSenseCamera.get_frames() 인터페이스 호환.

        Returns:
            (color_image_bgr_or_None, depth_frame_obj, depth_image_numpy)
            - color_image: ACE2 RGB BGR uint8 또는 None (use_ace2=False or 캡처 실패 + fallback)
            - depth_frame_obj: BaslerFrames 전체 객체 (협력사의 depth_frame 자리 — 호환용)
            - depth_image: depth_map ndarray (H, W) uint16, mm 단위

        Note:
            협력사 코드는 RealSense의 aligned_depth_frame을 두 번째로 반환하지만
            우리 Basler에는 align 개념이 다름. 두 번째 자리에 BaslerFrames 전체를 반환해
            메인 파이프라인에서 필요 시 추가 정보(confidence_map 등) 접근 가능.
        """
        if not self._started:
            raise RuntimeError("Call start() first")

        try:
            frames: BaslerFrames = self._capture.capture(timeout_ms=timeout_ms)
        except Exception as e:
            logger.error("Basler capture failed: %s", e)
            return None, None, None

        color = frames.color_image  # ACE2 미사용/실패 시 None
        depth = frames.depth_map

        return color, frames, depth

    def get_depth_pixel(self, u: int, v: int, depth_image: np.ndarray) -> float:
        """
        협력사 get_depth_pixel_value() 호환 헬퍼.
        특정 픽셀의 depth (mm) 값을 반환. 범위 밖이면 0.0.
        """
        if 0 <= u < depth_image.shape[1] and 0 <= v < depth_image.shape[0]:
            return float(depth_image[v, u])
        return 0.0

    def release(self) -> None:
        """카메라 스트리밍 종료 + 자원 해제."""
        if self._started:
            try:
                self._capture.stop()
                logger.info("BaslerWrapper released safely.")
            except Exception as e:
                logger.error("Failed to stop Basler: %s", e)
            self._started = False

    # 컨텍스트 매니저 지원
    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


# ============================================================
# 단독 실행 — 환경 점검 + 1프레임 캡처 테스트
# ============================================================
def _main():
    import argparse
    import cv2

    parser = argparse.ArgumentParser(description="BaslerWrapper 단독 테스트")
    parser.add_argument("--ace2", action="store_true", help="ACE2 RGB 동시 캡처 (어댑터 도착 후)")
    parser.add_argument("--save", type=str, default=None, help="저장 디렉토리 (예: /tmp/wrapper_test)")
    parser.add_argument("--live", action="store_true", help="OpenCV 윈도우 라이브 표시")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print("=== BaslerWrapper 테스트 시작 ===")
    with BaslerWrapper(use_ace2=args.ace2) as cam:
        print(f"Intrinsics: {cam.intrinsics}")

        if args.live:
            print("Live 모드 — 'q' 키로 종료")
            while True:
                color, frames, depth = cam.get_frames()
                if depth is None:
                    continue
                depth_vis = cv2.convertScaleAbs(depth, alpha=0.03)
                depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
                if color is not None:
                    h, w = depth_color.shape[:2]
                    color_resized = cv2.resize(color, (w, h))
                    display = np.hstack((color_resized, depth_color))
                else:
                    display = depth_color
                cv2.imshow("BaslerWrapper Live", display)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            cv2.destroyAllWindows()
        else:
            # 단일 프레임 + 통계
            color, frames, depth = cam.get_frames()
            if depth is None:
                print("❌ depth 캡처 실패")
                return
            valid = depth[depth > 0]
            print(f"Depth: shape={depth.shape}, dtype={depth.dtype}")
            print(f"  valid={len(valid)/depth.size*100:.1f}%")
            if len(valid) > 0:
                print(f"  range={valid.min()}~{valid.max()}mm, median={np.median(valid):.0f}mm")
            if color is not None:
                print(f"Color: shape={color.shape}")
            else:
                print("Color: None (ACE2 미사용 또는 미연결)")

            if args.save:
                save_path = Path(args.save)
                frames.save(save_path)
                print(f"저장 완료: {save_path}")

    print("=== 테스트 종료 ===")


if __name__ == "__main__":
    _main()
