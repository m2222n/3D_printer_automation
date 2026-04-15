"""
Basler 카메라 캡처 모듈 — Blaze-112 (ToF) + ace2 (RGB 5MP)
============================================================

Basler Blaze-112 ToF 카메라에서 depth + confidence 프레임을 취득하고,
ace2 a2A2590-22gcPRO RGB 카메라에서 color 프레임을 취득한다.
두 카메라 데이터를 합쳐 Colored Point Cloud를 생성한다.

카메라 조합:
  - Blaze-112: 640x480, ToF(depth+confidence), GigE, 0.3~10m
  - ace2 a2A2590-22gcPRO: 2592x1944 (5MP), RGB, GigE

사용법 (카메라 연결 시):
    from bin_picking.src.acquisition.basler_capture import BaslerCapture
    cap = BaslerCapture()
    cap.start()
    frames = cap.capture()       # depth, color, intrinsics 한번에
    pcd = cap.to_pointcloud()    # Open3D PointCloud 직접 변환
    cap.stop()

사용법 (카메라 없이 — 저장된 프레임 로드):
    frames = BaslerCapture.load_frames("saved_dir/")

사용법 (단독 실행 — 장치 목록 + 시뮬 테스트):
    python bin_picking/src/acquisition/basler_capture.py --list
    python bin_picking/src/acquisition/basler_capture.py --test

실행 환경: source .venv/binpick/bin/activate
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

try:
    from pypylon import pylon
except ImportError:
    pylon = None


# ============================================================
# 카메라 스펙 상수
# ============================================================

# Basler Blaze-112 ToF (depth)
BLAZE_112_SPEC = {
    "model": "Basler Blaze-112",
    "type": "ToF",
    "width": 640,
    "height": 480,
    "fps": 30,
    "depth_min_m": 0.3,
    "depth_max_m": 10.0,     # 카탈로그 최대, 실용 ~1.5m
    "interface": "GigE",
    # 내부 파라미터 추정값 — 카메라 입고 후 캘리브레이션 필요
    "fx": 460.0,
    "fy": 460.0,
    "cx": 320.0,
    "cy": 240.0,
}

# Basler ace2 a2A2590-22gcPRO (RGB 5MP)
ACE2_5MP_SPEC = {
    "model": "Basler ace2 a2A2590-22gcPRO",
    "type": "RGB",
    "width": 2592,
    "height": 1944,
    "fps": 22,
    "interface": "GigE",
    "sensor": "Sony IMX334",
    # 내부 파라미터 추정값 — 카메라 입고 후 캘리브레이션 필요
    "fx": 2400.0,
    "fy": 2400.0,
    "cx": 1296.0,
    "cy": 972.0,
}


# ============================================================
# 데이터 클래스
# ============================================================
@dataclass
class BaslerIntrinsics:
    """Basler 카메라 내부 파라미터."""
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float

    def to_dict(self) -> dict:
        return {
            "width": self.width, "height": self.height,
            "fx": self.fx, "fy": self.fy, "cx": self.cx, "cy": self.cy,
        }

    @classmethod
    def from_dict(cls, d: dict) -> BaslerIntrinsics:
        return cls(
            width=int(d["width"]), height=int(d["height"]),
            fx=float(d["fx"]), fy=float(d["fy"]),
            cx=float(d["cx"]), cy=float(d["cy"]),
        )

    @classmethod
    def from_spec(cls, spec: dict) -> BaslerIntrinsics:
        """카메라 스펙 딕셔너리에서 생성."""
        return cls(
            width=spec["width"], height=spec["height"],
            fx=spec["fx"], fy=spec["fy"],
            cx=spec["cx"], cy=spec["cy"],
        )


@dataclass
class BaslerFrames:
    """캡처된 Basler 프레임 (depth + color + confidence)."""
    depth_map: np.ndarray               # (H, W) uint16, mm 단위
    color_image: Optional[np.ndarray]   # (H_color, W_color, 3) BGR 또는 None
    confidence_map: Optional[np.ndarray]  # (H, W) uint16 또는 None
    depth_intrinsics: BaslerIntrinsics  # depth 카메라 파라미터
    color_intrinsics: Optional[BaslerIntrinsics]  # color 카메라 파라미터 (None = 단일 카메라)
    depth_scale: float = 1000.0         # depth_map 값 → m 변환 (mm → m)

    def save(self, out_dir: str | Path) -> None:
        """프레임을 디스크에 저장."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        np.save(out / "depth.npy", self.depth_map)
        if self.color_image is not None:
            np.save(out / "color.npy", self.color_image)
        if self.confidence_map is not None:
            np.save(out / "confidence.npy", self.confidence_map)
        meta = {
            **self.depth_intrinsics.to_dict(),
            "depth_scale": self.depth_scale,
        }
        if self.color_intrinsics is not None:
            meta["color_intrinsics"] = self.color_intrinsics.to_dict()
        (out / "meta.json").write_text(json.dumps(meta, indent=2))


# ============================================================
# BaslerCapture
# ============================================================
class BaslerCapture:
    """Basler Blaze-112 (ToF) + ace2 (RGB) 듀얼 캡처.

    Blaze-112에서 depth/confidence를, ace2에서 color를 취득한다.
    ace2 없이 Blaze-112 단독으로도 동작한다.
    """

    def __init__(
        self,
        blaze_serial: Optional[str] = None,
        ace2_serial: Optional[str] = None,
        depth_width: int = 640,
        depth_height: int = 480,
        color_width: int = 2592,
        color_height: int = 1944,
        depth_min: float = 0.3,
        depth_max: float = 1.5,
        confidence_threshold: int = 100,
        color_downscale: Optional[int] = None,
    ):
        """
        Args:
            blaze_serial: Blaze-112 시리얼 번호 (None=자동 검색)
            ace2_serial: ace2 시리얼 번호 (None=자동 검색, ace2 없으면 depth만)
            depth_width, depth_height: Blaze-112 해상도 (기본 640x480)
            color_width, color_height: ace2 해상도 (기본 2592x1944)
            depth_min, depth_max: 유효 depth 범위 (m)
            confidence_threshold: Blaze-112 confidence 필터링 임계값
            color_downscale: color를 depth 해상도에 맞추기 위한 다운스케일 팩터
                            (None=원본 유지, 4=2592→648 근사)
        """
        if pylon is None:
            raise ImportError(
                "pypylon이 설치되지 않았습니다. pip install pypylon"
            )

        self.blaze_serial = blaze_serial
        self.ace2_serial = ace2_serial
        self.depth_width = depth_width
        self.depth_height = depth_height
        self.color_width = color_width
        self.color_height = color_height
        self.depth_min = depth_min
        self.depth_max = depth_max
        self.confidence_threshold = confidence_threshold
        self.color_downscale = color_downscale

        self._blaze_cam: Optional[pylon.InstantCamera] = None
        self._ace2_cam: Optional[pylon.InstantCamera] = None

    @staticmethod
    def list_devices() -> list[dict]:
        """연결된 Basler 카메라 목록을 반환한다."""
        if pylon is None:
            raise ImportError("pypylon이 설치되지 않았습니다.")

        tlf = pylon.TlFactory.GetInstance()
        devices = tlf.EnumerateDevices()
        result = []
        for dev in devices:
            result.append({
                "model": dev.GetModelName(),
                "serial": dev.GetSerialNumber(),
                "vendor": dev.GetVendorName(),
                "interface": dev.GetDeviceClass(),
                "ip": dev.GetIpAddress() if hasattr(dev, "GetIpAddress") else "N/A",
            })
        return result

    def _find_camera(self, model_keyword: str, serial: Optional[str] = None):
        """모델명 키워드 + 시리얼로 카메라를 찾아 InstantCamera를 반환."""
        tlf = pylon.TlFactory.GetInstance()
        devices = tlf.EnumerateDevices()

        for dev in devices:
            model = dev.GetModelName()
            sn = dev.GetSerialNumber()

            if serial and sn != serial:
                continue
            if model_keyword.lower() in model.lower():
                cam = pylon.InstantCamera(tlf.CreateDevice(dev))
                return cam

        return None

    def start(self) -> dict:
        """카메라를 열고 그래빙을 시작한다.

        Returns:
            {"blaze": bool, "ace2": bool} — 각 카메라 연결 성공 여부
        """
        result = {"blaze": False, "ace2": False}

        # Blaze-112 연결
        self._blaze_cam = self._find_camera("blaze", self.blaze_serial)
        if self._blaze_cam is not None:
            self._blaze_cam.Open()
            # Blaze-112 설정 (pypylon GenICam 노드)
            try:
                nodemap = self._blaze_cam.GetNodeMap()
                # 해상도 설정 (Blaze는 640x480 고정이지만 노드가 있을 수 있음)
                self._setup_blaze(nodemap)
            except Exception:
                pass  # 노드 없으면 기본값 사용
            self._blaze_cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            result["blaze"] = True

        # ace2 연결
        self._ace2_cam = self._find_camera("a2A", self.ace2_serial)
        if self._ace2_cam is not None:
            self._ace2_cam.Open()
            try:
                nodemap = self._ace2_cam.GetNodeMap()
                self._setup_ace2(nodemap)
            except Exception:
                pass
            self._ace2_cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            result["ace2"] = True

        if not result["blaze"]:
            raise RuntimeError(
                "Blaze-112 카메라를 찾을 수 없습니다. "
                "연결 상태 및 시리얼 번호를 확인하세요."
            )

        return result

    def _setup_blaze(self, nodemap) -> None:
        """Blaze-112 GenICam 노드 설정."""
        # Blaze-112은 depth + confidence를 멀티파트로 전송
        # 구체적인 노드명은 카메라 입고 후 확인 필요
        try:
            # 노출 시간 (ToF integration time)
            if nodemap.GetNode("ExposureTime") is not None:
                nodemap.GetNode("ExposureTime").SetValue(5000)  # 5ms 기본
        except Exception:
            pass

    def _setup_ace2(self, nodemap) -> None:
        """ace2 GenICam 노드 설정."""
        try:
            # 픽셀 포맷: BGR8
            if nodemap.GetNode("PixelFormat") is not None:
                nodemap.GetNode("PixelFormat").SetValue("BGR8")
        except Exception:
            try:
                # BGR8 없으면 BayerRG8 (소프트웨어 디베이어링)
                if nodemap.GetNode("PixelFormat") is not None:
                    nodemap.GetNode("PixelFormat").SetValue("BayerRG8")
            except Exception:
                pass

    def stop(self) -> None:
        """카메라 그래빙 중지 및 닫기."""
        for cam in [self._blaze_cam, self._ace2_cam]:
            if cam is not None:
                try:
                    if cam.IsGrabbing():
                        cam.StopGrabbing()
                    if cam.IsOpen():
                        cam.Close()
                except Exception:
                    pass
        self._blaze_cam = None
        self._ace2_cam = None

    def capture(self, timeout_ms: int = 5000) -> BaslerFrames:
        """depth + color 프레임을 캡처한다.

        Args:
            timeout_ms: 그랩 타임아웃 (ms)

        Returns:
            BaslerFrames: depth, color, confidence, intrinsics
        """
        if self._blaze_cam is None or not self._blaze_cam.IsGrabbing():
            raise RuntimeError("start()를 먼저 호출하세요.")

        # --- Blaze-112 depth 캡처 ---
        grab_result = self._blaze_cam.RetrieveResult(timeout_ms, pylon.TimeoutHandling_ThrowException)
        if not grab_result.GrabSucceeded():
            raise RuntimeError(f"Blaze-112 그랩 실패: {grab_result.ErrorCode}")

        # Blaze-112 출력 형식에 따라 파싱
        # Coord3D_C16: depth만 (uint16, mm)
        # Multipart: depth + confidence + intensity
        depth_map = grab_result.Array.copy()
        if depth_map.dtype != np.uint16:
            depth_map = depth_map.astype(np.uint16)

        # confidence map (Blaze 멀티파트 지원 시)
        confidence_map = None
        # 멀티파트 데이터 접근은 카메라 입고 후 구체화

        grab_result.Release()

        depth_intrinsics = BaslerIntrinsics.from_spec(BLAZE_112_SPEC)

        # --- ace2 color 캡처 ---
        color_image = None
        color_intrinsics = None

        if self._ace2_cam is not None and self._ace2_cam.IsGrabbing():
            grab_color = self._ace2_cam.RetrieveResult(timeout_ms, pylon.TimeoutHandling_ThrowException)
            if grab_color.GrabSucceeded():
                color_image = grab_color.Array.copy()

                # BayerRG8 → BGR 변환 (필요 시)
                if len(color_image.shape) == 2:
                    import cv2
                    color_image = cv2.cvtColor(color_image, cv2.COLOR_BayerRG2BGR)

                # 다운스케일 (depth 해상도에 근사)
                if self.color_downscale and self.color_downscale > 1:
                    import cv2
                    h, w = color_image.shape[:2]
                    new_w = w // self.color_downscale
                    new_h = h // self.color_downscale
                    color_image = cv2.resize(color_image, (new_w, new_h))

                color_intrinsics = BaslerIntrinsics.from_spec(ACE2_5MP_SPEC)
                if self.color_downscale and self.color_downscale > 1:
                    s = self.color_downscale
                    color_intrinsics = BaslerIntrinsics(
                        width=color_intrinsics.width // s,
                        height=color_intrinsics.height // s,
                        fx=color_intrinsics.fx / s,
                        fy=color_intrinsics.fy / s,
                        cx=color_intrinsics.cx / s,
                        cy=color_intrinsics.cy / s,
                    )

            grab_color.Release()

        return BaslerFrames(
            depth_map=depth_map,
            color_image=color_image,
            confidence_map=confidence_map,
            depth_intrinsics=depth_intrinsics,
            color_intrinsics=color_intrinsics,
            depth_scale=1000.0,
        )

    def to_pointcloud(self, frames: Optional[BaslerFrames] = None):
        """BaslerFrames → Open3D PointCloud.

        color와 depth 해상도가 다를 경우 color를 depth 해상도에 맞춰 리사이즈한다.
        """
        from bin_picking.src.acquisition.depth_to_pointcloud import depth_to_pointcloud

        if frames is None:
            frames = self.capture()

        # color를 depth 해상도에 맞추기
        color_for_pcd = None
        if frames.color_image is not None:
            color_for_pcd = frames.color_image
            dh, dw = frames.depth_map.shape[:2]
            ch, cw = color_for_pcd.shape[:2]
            if (ch, cw) != (dh, dw):
                import cv2
                color_for_pcd = cv2.resize(color_for_pcd, (dw, dh))

        intr = frames.depth_intrinsics
        return depth_to_pointcloud(
            depth_map=frames.depth_map,
            fx=intr.fx,
            fy=intr.fy,
            cx=intr.cx,
            cy=intr.cy,
            color_image=color_for_pcd,
            depth_scale=frames.depth_scale,
            depth_min=self.depth_min,
            depth_max=self.depth_max,
            confidence_map=frames.confidence_map,
            confidence_threshold=self.confidence_threshold,
        )

    @staticmethod
    def load_frames(frame_dir: str | Path) -> BaslerFrames:
        """저장된 프레임 로드 (카메라 없는 환경용)."""
        d = Path(frame_dir)
        depth_map = np.load(d / "depth.npy")
        meta = json.loads((d / "meta.json").read_text())

        color_image = None
        color_path = d / "color.npy"
        if color_path.exists():
            color_image = np.load(color_path)

        confidence_map = None
        conf_path = d / "confidence.npy"
        if conf_path.exists():
            confidence_map = np.load(conf_path)

        depth_scale = meta.pop("depth_scale", 1000.0)
        color_intr_dict = meta.pop("color_intrinsics", None)
        depth_intrinsics = BaslerIntrinsics.from_dict(meta)
        color_intrinsics = (BaslerIntrinsics.from_dict(color_intr_dict)
                           if color_intr_dict else None)

        return BaslerFrames(
            depth_map=depth_map,
            color_image=color_image,
            confidence_map=confidence_map,
            depth_intrinsics=depth_intrinsics,
            color_intrinsics=color_intrinsics,
            depth_scale=depth_scale,
        )

    @staticmethod
    def create_simulated_frames() -> BaslerFrames:
        """시뮬레이션 프레임 생성 (카메라 없이 테스트용).

        Blaze-112 해상도(640x480) depth + ace2 리사이즈(640x480) color 시뮬.
        """
        H, W = 480, 640
        np.random.seed(42)

        # 시뮬 depth: 빈(bin) 내부를 바라보는 오버헤드 카메라 시뮬
        # 바닥 500mm + 부품들 300~450mm
        depth_mm = np.full((H, W), 500, dtype=np.uint16)  # 바닥 500mm

        # 부품 3개 시뮬 (다른 높이)
        parts = [
            (200, 150, 60, 40, 350),   # y, x, h, w, depth_mm
            (300, 350, 45, 80, 400),
            (100, 400, 30, 30, 320),
        ]
        for py, px, ph, pw, pd in parts:
            depth_mm[py:py+ph, px:px+pw] = pd

        # depth 노이즈 (ToF 특성: ±2mm)
        noise = np.random.normal(0, 2, (H, W)).astype(np.int16)
        depth_mm = np.clip(depth_mm.astype(np.int32) + noise, 0, 65535).astype(np.uint16)

        # 시뮬 color: 부품마다 다른 색상
        color = np.full((H, W, 3), (200, 200, 200), dtype=np.uint8)  # 바닥 회색
        colors_bgr = [(50, 50, 200), (50, 200, 50), (200, 50, 50)]  # BGR
        for i, (py, px, ph, pw, _) in enumerate(parts):
            color[py:py+ph, px:px+pw] = colors_bgr[i]

        # confidence (높은 값 = 신뢰도 높음)
        confidence = np.full((H, W), 200, dtype=np.uint16)
        # 부품 경계에서 confidence 낮음
        confidence[:10, :] = 30
        confidence[-10:, :] = 30

        depth_intrinsics = BaslerIntrinsics.from_spec(BLAZE_112_SPEC)

        return BaslerFrames(
            depth_map=depth_mm,
            color_image=color,
            confidence_map=confidence,
            depth_intrinsics=depth_intrinsics,
            color_intrinsics=BaslerIntrinsics(
                width=W, height=H,
                fx=ACE2_5MP_SPEC["fx"] / 4, fy=ACE2_5MP_SPEC["fy"] / 4,
                cx=ACE2_5MP_SPEC["cx"] / 4, cy=ACE2_5MP_SPEC["cy"] / 4,
            ),
            depth_scale=1000.0,
        )


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="Basler 카메라 캡처 (Blaze-112 + ace2)")
    parser.add_argument("--list", action="store_true", help="연결된 Basler 장치 목록")
    parser.add_argument("--test", action="store_true", help="시뮬 프레임 테스트 (카메라 불필요)")
    parser.add_argument("--save", type=str, help="프레임 저장 경로")
    args = parser.parse_args()

    if args.list:
        print("=" * 60)
        print("  연결된 Basler 카메라 목록")
        print("=" * 60)
        devices = BaslerCapture.list_devices()
        if not devices:
            print("  장치 없음")
        for i, dev in enumerate(devices):
            print(f"  [{i}] {dev['model']} (S/N: {dev['serial']}, {dev['interface']})")
        return

    if args.test:
        print("=" * 60)
        print("  Basler 캡처 시뮬 테스트")
        print("=" * 60)

        frames = BaslerCapture.create_simulated_frames()
        print(f"\n  depth: {frames.depth_map.shape}, dtype={frames.depth_map.dtype}")
        print(f"  color: {frames.color_image.shape}, dtype={frames.color_image.dtype}")
        print(f"  confidence: {frames.confidence_map.shape}, dtype={frames.confidence_map.dtype}")
        print(f"  depth intrinsics: {frames.depth_intrinsics.to_dict()}")
        print(f"  depth_scale: {frames.depth_scale}")

        # depth 통계
        valid = frames.depth_map > 0
        print(f"\n  depth 유효: {valid.sum():,} / {valid.size:,} ({valid.mean()*100:.1f}%)")
        print(f"  depth 범위: {frames.depth_map[valid].min()}~{frames.depth_map[valid].max()} mm")

        # 저장/로드 라운드트립
        if args.save:
            save_dir = Path(args.save)
        else:
            save_dir = Path("/tmp/basler_sim_test")
        frames.save(save_dir)
        print(f"\n  저장: {save_dir}")

        loaded = BaslerCapture.load_frames(save_dir)
        assert np.array_equal(loaded.depth_map, frames.depth_map), "depth 불일치!"
        assert np.array_equal(loaded.color_image, frames.color_image), "color 불일치!"
        assert np.array_equal(loaded.confidence_map, frames.confidence_map), "confidence 불일치!"
        assert loaded.depth_intrinsics.fx == frames.depth_intrinsics.fx, "intrinsics 불일치!"
        print("  로드 검증: OK (라운드트립 일치)")

        print("\n  테스트 완료!")
        return

    # 라이브 캡처
    print("=" * 60)
    print("  Basler 라이브 캡처")
    print("=" * 60)

    cap = BaslerCapture()
    result = cap.start()
    print(f"  Blaze-112: {'OK' if result['blaze'] else 'FAIL'}")
    print(f"  ace2:      {'OK' if result['ace2'] else 'N/A'}")

    frames = cap.capture()
    print(f"\n  depth: {frames.depth_map.shape}")
    if frames.color_image is not None:
        print(f"  color: {frames.color_image.shape}")
    if frames.confidence_map is not None:
        print(f"  confidence: {frames.confidence_map.shape}")

    if args.save:
        frames.save(args.save)
        print(f"\n  저장: {args.save}")

    cap.stop()
    print("\n  캡처 완료!")


if __name__ == "__main__":
    main()
