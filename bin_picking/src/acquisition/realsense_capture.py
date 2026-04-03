"""
Intel RealSense D435 캡처 모듈
===============================
RealSense D435 카메라에서 depth + color 프레임을 취득하고,
기존 depth_to_pointcloud() 파이프라인에 연결.
D435: 스테레오 depth (GS OV9282 x2) + RGB (OV2740), USB 3.0, 0.105~10m.

사용법 (카메라 연결 시):
    from bin_picking.src.acquisition.realsense_capture import RealSenseCapture
    cap = RealSenseCapture()
    cap.start()
    frames = cap.capture()       # depth, color, intrinsics 한번에
    pcd = cap.to_pointcloud()    # Open3D PointCloud 직접 변환
    cap.stop()

사용법 (카메라 없이 — 저장된 프레임 로드):
    frames = RealSenseCapture.load_frames("saved_dir/")
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

try:
    import pyrealsense2 as rs
except ImportError:
    rs = None

@dataclass
class RSIntrinsics:
    """RealSense 카메라 내부 파라미터."""
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
    def from_dict(cls, d: dict) -> RSIntrinsics:
        return cls(
            width=int(d["width"]), height=int(d["height"]),
            fx=float(d["fx"]), fy=float(d["fy"]),
            cx=float(d["cx"]), cy=float(d["cy"]),
        )

    @classmethod
    def from_rs_intrinsics(cls, intr) -> RSIntrinsics:
        """pyrealsense2 intrinsics 객체에서 변환."""
        return cls(
            width=intr.width, height=intr.height,
            fx=intr.fx, fy=intr.fy, cx=intr.ppx, cy=intr.ppy,
        )


@dataclass
class CapturedFrames:
    """캡처된 depth + color 프레임 + 카메라 파라미터."""
    depth_map: np.ndarray       # (H, W) uint16, mm 단위
    color_image: np.ndarray     # (H, W, 3) BGR
    intrinsics: RSIntrinsics
    depth_scale: float          # depth_map 값 → m 변환 계수 (보통 1000.0)

    def save(self, out_dir: str | Path) -> None:
        """프레임을 디스크에 저장 (카메라 없는 환경에서 재사용)."""
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        np.save(out / "depth.npy", self.depth_map)
        np.save(out / "color.npy", self.color_image)
        meta = {**self.intrinsics.to_dict(), "depth_scale": self.depth_scale}
        (out / "meta.json").write_text(json.dumps(meta, indent=2))


class RealSenseCapture:
    """Intel RealSense depth + color 캡처."""

    def __init__(
        self,
        width: int = 640,
        height: int = 480,
        fps: int = 30,
        enable_color: bool = True,
        align_to_color: bool = True,
        depth_min: float = 0.1,
        depth_max: float = 3.0,
    ):
        if rs is None:
            raise ImportError(
                "pyrealsense2가 설치되지 않았습니다. pip install pyrealsense2"
            )

        self.width = width
        self.height = height
        self.fps = fps
        self.enable_color = enable_color
        self.align_to_color = align_to_color
        self.depth_min = depth_min
        self.depth_max = depth_max

        self._pipeline: rs.pipeline | None = None
        self._align: rs.align | None = None
        self._depth_scale: float = 1.0  # 장치에서 읽어옴

    def start(self) -> None:
        """파이프라인 시작. 카메라 연결 필요."""
        config = rs.config()
        config.enable_stream(
            rs.stream.depth, self.width, self.height, rs.format.z16, self.fps
        )
        if self.enable_color:
            config.enable_stream(
                rs.stream.color, self.width, self.height, rs.format.bgr8, self.fps
            )

        self._pipeline = rs.pipeline()
        profile = self._pipeline.start(config)

        # depth scale 읽기 (장치마다 다름)
        depth_sensor = profile.get_device().first_depth_sensor()
        self._depth_scale = depth_sensor.get_depth_scale()

        if self.align_to_color and self.enable_color:
            self._align = rs.align(rs.stream.color)

    def stop(self) -> None:
        """파이프라인 정지."""
        if self._pipeline:
            self._pipeline.stop()
            self._pipeline = None
            self._align = None

    def capture(self, timeout_ms: int = 5000) -> CapturedFrames:
        """
        한 프레임 캡처.

        Returns
        -------
        CapturedFrames
            depth_map (uint16, mm), color_image (BGR), intrinsics, depth_scale=1000.0
        """
        if self._pipeline is None:
            raise RuntimeError("start()를 먼저 호출하세요.")

        frameset = self._pipeline.wait_for_frames(timeout_ms)

        if self._align:
            frameset = self._align.process(frameset)

        depth_frame = frameset.get_depth_frame()
        if not depth_frame:
            raise RuntimeError("depth 프레임을 가져올 수 없습니다.")

        # depth → numpy (uint16). RealSense 기본: depth * depth_scale = meters
        depth_raw = np.asanyarray(depth_frame.get_data())  # uint16

        # depth_scale을 mm 단위로 정규화: raw * device_scale * 1000 = mm
        # 예: device_scale=0.001 → raw값이 이미 mm. device_scale=0.0001 → raw*0.1=mm
        depth_mm = (depth_raw.astype(np.float64) * self._depth_scale * 1000.0).astype(
            np.uint16
        )

        # intrinsics 추출 (depth 또는 color 기준)
        if self._align and self.enable_color:
            intr_source = frameset.get_color_frame().get_profile()
        else:
            intr_source = depth_frame.get_profile()
        rs_intr = intr_source.as_video_stream_profile().get_intrinsics()
        intrinsics = RSIntrinsics.from_rs_intrinsics(rs_intr)

        # color
        color_image = np.zeros((intrinsics.height, intrinsics.width, 3), np.uint8)
        if self.enable_color:
            color_frame = frameset.get_color_frame()
            if color_frame:
                color_image = np.asanyarray(color_frame.get_data())

        return CapturedFrames(
            depth_map=depth_mm,
            color_image=color_image,
            intrinsics=intrinsics,
            depth_scale=1000.0,  # mm → m
        )

    def to_pointcloud(self, frames: CapturedFrames | None = None):
        """
        CapturedFrames → Open3D PointCloud.
        frames가 None이면 capture() 호출.
        Open3D가 필요하므로 호출 시점에 import.
        """
        from bin_picking.src.acquisition.depth_to_pointcloud import depth_to_pointcloud

        if frames is None:
            frames = self.capture()

        return depth_to_pointcloud(
            depth_map=frames.depth_map,
            fx=frames.intrinsics.fx,
            fy=frames.intrinsics.fy,
            cx=frames.intrinsics.cx,
            cy=frames.intrinsics.cy,
            color_image=frames.color_image,
            depth_scale=frames.depth_scale,
            depth_min=self.depth_min,
            depth_max=self.depth_max,
        )

    @staticmethod
    def load_frames(frame_dir: str | Path) -> CapturedFrames:
        """저장된 프레임 로드 (카메라 없는 환경용)."""
        d = Path(frame_dir)
        depth_map = np.load(d / "depth.npy")
        color_image = np.load(d / "color.npy")
        meta = json.loads((d / "meta.json").read_text())
        depth_scale = meta.pop("depth_scale", 1000.0)
        intrinsics = RSIntrinsics.from_dict(meta)
        return CapturedFrames(
            depth_map=depth_map,
            color_image=color_image,
            intrinsics=intrinsics,
            depth_scale=depth_scale,
        )


# Intel RealSense D435 참고 사양
# - Depth: 최대 1280x720, 기본 640x480, GS OV9282 x2 (스테레오)
# - RGB: 1920x1080, 기본 640x480, RS OV2740
# - Depth FOV: 87° x 58°, 측정 범위 0.105m ~ 10m (실용 ~3m)
# - USB 3.0 Type-C, 무게 72g
# - 실제 intrinsics는 장치 펌웨어에서 자동 읽어옴 (capture() 시)
REALSENSE_D435_INTRINSICS = {
    "width": 640,
    "height": 480,
    "fx": 383.0,    # 640x480 기준 대략값, 실제는 장치마다 다름
    "fy": 383.0,
    "cx": 320.0,
    "cy": 240.0,
    "depth_min": 0.105,  # D435 최소 측정 거리
    "depth_max": 3.0,    # 실용 최대 거리
}
