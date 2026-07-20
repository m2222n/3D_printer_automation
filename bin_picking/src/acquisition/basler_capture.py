"""
Basler 카메라 캡처 모듈 — Blaze-112 (ToF) + ace2 (RGB 5MP)
============================================================

Basler Blaze-112 ToF 카메라에서 depth + confidence 프레임을 취득하고,
ace2 a2A2448-23gcBAS RGB 카메라에서 color 프레임을 취득한다.
두 카메라 데이터를 합쳐 Colored Point Cloud를 생성한다.

카메라 조합:
  - Blaze-112: 848×480, ToF(depth+intensity multipart), GigE, 0.3~10m
                FOV 75°(H) × 104°(V) → fx≈553, fy≈188 (5/12 실측 정정)
  - ace2 a2A2448-23gcBAS: 2448×2048 (5MP), RGB, GigE
                Sony IMX392, 픽셀 피치 3.45µm, C-mount 렌즈 별매 (한솔 보유)

이력:
  - 5/8 박스 개봉 시 ace2 실제 모델 a2A2448-23gcBAS 확인 (코드 가정 a2A2590-22gcPRO와 다름)
  - 5/11 BLAZE fx/fy 460→417/188 정정 (FOV 75°×104° 기반, width 640 가정)
  - 5/11 ACE2 모델명 + 해상도 (2592×1944 → 2448×2048) 정정
  - 5/12 실측: Blaze 실 해상도 848×480 확인 (매뉴얼 640×480 가정 오류). fx 417→553 재계산
  - 5/12 macOS Blaze 풀 작동 검증 — Blaze Supplementary 없이 pypylon만으로 OK
  - 5/12 IP 직접 fallback 추가 (EnumerateDevices 미동작 → BASLER_BLAZE_IP / BASLER_ACE2_IP 환경변수)
  - 5/12 Coord3D_C16 사용 불가 (Supplementary 필요) → Range component만 enable, Mono16 mm depth로 사용
  - fx/fy 추정값은 카메라 입고 후 ChAruco 보드로 정식 캘리브 예정

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
import os
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
# 5/8 박스 개봉 시 실 사양 확인 (S/N 40737830, MAC 00:30:53:37:BB:6E)
# 5/12 라이브 검증 시 실 해상도 848×480 확인 (매뉴얼 640×480 가정 오류)
# FOV 75°(H) × 104°(V) → fx/fy 재계산
#   fx = 848 / (2 × tan(75°/2)) = 848 / (2 × 0.7673) ≈ 553
#   fy = 480 / (2 × tan(104°/2)) = 480 / (2 × 1.2799) ≈ 188
# ⚠️ 추정값. 카메라 입고 후 ChAruco 보드로 정식 캘리브레이션 필요
BLAZE_112_SPEC = {
    "model": "Basler Blaze-112",
    "type": "ToF",
    "width": 848,            # 5/12 실측 (매뉴얼 640 가정 오류)
    "height": 480,
    "fps": 30,
    "depth_min_m": 0.3,
    "depth_max_m": 10.0,     # 카탈로그 최대, 실용 ~1.5m
    "interface": "GigE",
    "fov_h_deg": 75.0,
    "fov_v_deg": 104.0,
    "voltage_v": 24.0,       # 24VDC 고정 (PoE 아님, 21V 미만 손상)
    # 내부 파라미터 — FOV 기반 추정 (5/12: 417/188 → 553/188, width 정정 반영)
    "fx": 553.0,
    "fy": 188.0,
    "cx": 424.0,             # width/2
    "cy": 240.0,
}

# Basler ace2 a2A2448-23gcBAS (RGB 5MP)
# 5/8 박스 개봉 시 실 모델명 확인 (S/N 41881328) — 코드 가정과 다름
# Sony IMX392 센서, 픽셀 피치 3.45µm, C-mount 렌즈 별매 (한솔 보유)
# fx/fy는 렌즈 초점거리에 따라 가변:
#   12mm 렌즈: fx = fy = 12 / 3.45e-3 ≈ 3478 px
#   8mm 렌즈:  fx = fy = 8 / 3.45e-3 ≈ 2319 px
#   16mm 렌즈: fx = fy = 16 / 3.45e-3 ≈ 4638 px
# ⚠️ 일단 12mm 가정. 한솔 렌즈 인수 + 캘리브 후 정확값으로 교체
ACE2_5MP_SPEC = {
    "model": "Basler ace2 a2A2448-23gcBAS",
    "type": "RGB",
    "width": 2448,
    "height": 2048,
    "fps": 23,
    "interface": "GigE",
    "sensor": "Sony IMX392",
    "pixel_pitch_um": 3.45,
    "lens": "C-mount, 별매 (한솔 보유)",
    "lens_focal_mm_assumed": 12.0,
    # 내부 파라미터 — 12mm 렌즈 가정 (5/11 정정: 2400 → 3478)
    "fx": 3478.0,
    "fy": 3478.0,
    "cx": 1224.0,
    "cy": 1024.0,
}


# ============================================================
# 데이터 클래스
# ============================================================
# 카메라 intrinsics 버전 식별자
# 추후 ChArUco 정식 캘리브 시 "calibrated_v1" 등으로 변경
# 라벨 json + meta.json 에 박혀서 어느 캘리브로 만든 데이터인지 추적 가능
INTRINSICS_VERSION = "estimated_v2_20260513"
# v1 (사전): BLAZE fx=460 (잘못, FOV 미반영)
# v2 (현재, 5/12): BLAZE fx=553 (width 848 + FOV 75° 기반), ACE2 fx=3478 (12mm 렌즈 가정)


@dataclass
class BaslerIntrinsics:
    """Basler 카메라 내부 파라미터."""
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float
    version: str = INTRINSICS_VERSION  # 캘리브 버전 (정식 캘리브 시 갱신)

    def to_dict(self) -> dict:
        return {
            "width": self.width, "height": self.height,
            "fx": self.fx, "fy": self.fy, "cx": self.cx, "cy": self.cy,
            "intrinsics_version": self.version,
        }

    @classmethod
    def from_dict(cls, d: dict) -> BaslerIntrinsics:
        return cls(
            width=int(d["width"]), height=int(d["height"]),
            fx=float(d["fx"]), fy=float(d["fy"]),
            cx=float(d["cx"]), cy=float(d["cy"]),
            version=str(d.get("intrinsics_version", "unknown")),
        )

    @classmethod
    def from_spec(cls, spec: dict) -> BaslerIntrinsics:
        """카메라 스펙 딕셔너리에서 생성."""
        return cls(
            width=spec["width"], height=spec["height"],
            fx=spec["fx"], fy=spec["fy"],
            cx=spec["cx"], cy=spec["cy"],
            version=spec.get("intrinsics_version", INTRINSICS_VERSION),
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
        blaze_ip: Optional[str] = None,
        ace2_ip: Optional[str] = None,
        depth_width: int = 848,    # 5/12 실측 정정 (640 → 848)
        depth_height: int = 480,
        color_width: int = 2448,    # 5/11 정정: a2A2448-23gcBAS 실 해상도
        color_height: int = 2048,
        depth_min: float = 0.3,
        depth_max: float = 1.5,
        confidence_threshold: int = 100,
        color_downscale: Optional[int] = None,
    ):
        """
        Args:
            blaze_serial: Blaze-112 시리얼 번호 (None=자동 검색)
            ace2_serial: ace2 시리얼 번호 (None=자동 검색, ace2 없으면 depth만)
            blaze_ip: Blaze 직접 IP 주소 (None이면 환경변수 BASLER_BLAZE_IP 시도).
                      macOS pypylon EnumerateDevices가 Blaze 미발견 시 fallback 필수
            ace2_ip: ace2 직접 IP 주소 (None이면 환경변수 BASLER_ACE2_IP 시도)
            depth_width, depth_height: Blaze-112 해상도 (5/12 실측 848x480)
            color_width, color_height: ace2 해상도 (a2A2448-23gcBAS 기본 2448x2048)
            depth_min, depth_max: 유효 depth 범위 (m)
            confidence_threshold: Blaze-112 confidence 필터링 임계값
            color_downscale: color를 depth 해상도에 맞추기 위한 다운스케일 팩터
                            (None=원본 유지, 4=2448→612 근사)
        """
        if pylon is None:
            raise ImportError(
                "pypylon이 설치되지 않았습니다. pip install pypylon"
            )

        self.blaze_serial = blaze_serial
        self.ace2_serial = ace2_serial
        self.blaze_ip = blaze_ip or os.environ.get("BASLER_BLAZE_IP")
        self.ace2_ip = ace2_ip or os.environ.get("BASLER_ACE2_IP")
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

    def _find_camera(
        self,
        model_keyword: str,
        serial: Optional[str] = None,
        ip: Optional[str] = None,
    ):
        """모델명 키워드 + 시리얼로 카메라를 찾아 InstantCamera를 반환.

        1) EnumerateDevices로 검색
        2) 실패 시 ip 인자로 직접 CreateDevice fallback
        macOS는 Blaze에 대해 broadcast discovery가 동작하지 않아 IP fallback 필수.
        """
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

        # Fallback: IP 직접 지정 (macOS Blaze 브로드캐스트 미동작 회피)
        if ip:
            try:
                info = pylon.DeviceInfo()
                info.SetIpAddress(ip)
                info.SetDeviceClass("BaslerGigE")
                cam = pylon.InstantCamera(tlf.CreateDevice(info))
                return cam
            except Exception:
                return None

        return None

    def start(self) -> dict:
        """카메라를 열고 그래빙을 시작한다.

        Returns:
            {"blaze": bool, "ace2": bool} — 각 카메라 연결 성공 여부
        """
        result = {"blaze": False, "ace2": False}

        # Blaze-112 연결
        self._blaze_cam = self._find_camera("blaze", self.blaze_serial, self.blaze_ip)
        if self._blaze_cam is not None:
            self._blaze_cam.Open()
            # Blaze-112 설정 (pypylon GenICam 노드)
            try:
                nodemap = self._blaze_cam.GetNodeMap()
                # 해상도 설정 (Blaze는 640x480 고정이지만 노드가 있을 수 있음)
                self._setup_blaze(nodemap)
                # GigE 스트리밍 튜닝 (macOS + USB 이더넷 어댑터 buffer underrun 방지)
                self._tune_gige(self._blaze_cam, nodemap)
            except Exception:
                pass  # 노드 없으면 기본값 사용
            self._blaze_cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
            result["blaze"] = True

        # ace2 연결
        self._ace2_cam = self._find_camera("a2A", self.ace2_serial, self.ace2_ip)
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

    # GigE 스트리밍 튜닝 상수 (2026-07-20 macOS Tahoe + ipTIME U1G-C 실측)
    # 원인: macOS + USB 이더넷 어댑터가 기본 66Mbps GigE 스트림을 못 따라가
    #       "buffer was incompletely grabbed" (0xE1000014) 발생. on-board adapter가
    #       아니면 throughput를 낮춰야 함 (Basler README도 on-board 권장).
    # 실측: 66Mbps=grab실패 / 20Mbps=4/5 / 15Mbps=10/10 안정 / 8Mbps=10/10.
    #       15Mbps 채택(안정하면서 최대 속도). 빈피킹은 정지물체 top-down이라 fps 무관.
    _GIGE_THROUGHPUT_LIMIT = 15_000_000  # bytes/s (DeviceLinkThroughputLimit)
    _GIGE_MAX_NUM_BUFFER = 30            # grab 버퍼 개수 (언더런 여유)

    def _tune_gige(self, cam, nodemap) -> None:
        """GigE 스트리밍 파라미터 튜닝 (buffer underrun 방지).

        macOS/USB 어댑터 조합에서만 필요하나, on-board(공장 IPC 등)에서는
        높은 throughput를 그대로 견디므로 이 낮은 값이어도 무해(fps만 소폭↓).
        노드 없거나 실패해도 무시 — 기존 동작 유지.
        """
        try:
            n = nodemap.GetNode("DeviceLinkThroughputLimit")
            if n is not None:
                # 카메라 지원 범위로 클램프
                val = max(int(n.Min), min(self._GIGE_THROUGHPUT_LIMIT, int(n.Max)))
                n.SetValue(val)
        except Exception:
            pass
        try:
            cam.MaxNumBuffer.SetValue(self._GIGE_MAX_NUM_BUFFER)
        except Exception:
            pass

    def _setup_blaze(self, nodemap) -> None:
        """Blaze-112 GenICam 노드 설정.

        Blaze는 ComponentSelector(Intensity/Range/Confidence)로 출력 컴포넌트를 선택한다.
        기본 상태에서는 Intensity + Range 둘 다 enabled → multipart 848×960 raw frame.
        Range만 enable하면 깨끗한 단일 컴포넌트 848×480 uint16 (mm 단위 depth) 출력.

        5/12 검증: Coord3D_C16 PixelFormat은 Blaze Supplementary 필요 → 사용 불가.
        Mono16 raw + Range single component로 mm depth uint16 직접 수신.
        """
        # 1) Intensity component 끄기
        try:
            cs = nodemap.GetNode("ComponentSelector")
            ce = nodemap.GetNode("ComponentEnable")
            if cs is not None and ce is not None:
                cs.FromString("Intensity")
                ce.SetValue(False)
                # 2) Range component 켜기 (depth)
                cs.FromString("Range")
                ce.SetValue(True)
        except Exception:
            pass  # 노드 없으면 기본 multipart 모드 유지

        # 3) 노출 시간 (ToF integration time, µs 단위)
        try:
            if nodemap.GetNode("ExposureTime") is not None:
                nodemap.GetNode("ExposureTime").SetValue(1000)  # 1ms (Blaze 기본값)
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
