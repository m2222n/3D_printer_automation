"""
Depth Map → Open3D Point Cloud 변환
=====================================
Basler Blaze-112 ToF 카메라 depth map을 Open3D PointCloud로 변환.

사용법:
    from bin_picking.src.acquisition.depth_to_pointcloud import depth_to_pointcloud
    pcd = depth_to_pointcloud(depth_map, fx, fy, cx, cy)
    pcd = depth_to_pointcloud(depth_map, fx, fy, cx, cy, color_image=bgr)
"""

import numpy as np

try:
    import open3d as o3d
except ImportError:
    o3d = None


def depth_to_pointcloud(
    depth_map: np.ndarray,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    color_image: np.ndarray | None = None,
    depth_scale: float = 1000.0,
    depth_min: float = 0.3,
    depth_max: float = 3.0,
    confidence_map: np.ndarray | None = None,
    confidence_threshold: int = 100,
) -> "o3d.geometry.PointCloud":
    """
    Depth map을 Open3D PointCloud로 변환.

    Parameters
    ----------
    depth_map : np.ndarray
        (H, W) depth 이미지. 단위는 depth_scale에 따라 다름.
        Blaze-112 Coord3D_C16 → mm 단위 uint16.
        Blaze-112 Coord3D_ABC32f → m 단위 float32 (depth_scale=1.0).
    fx, fy : float
        카메라 초점 거리 (pixels).
    cx, cy : float
        카메라 주점 (pixels).
    color_image : np.ndarray, optional
        (H, W, 3) BGR 칼라 이미지. 제공 시 Colored Point Cloud 생성.
    depth_scale : float
        depth 값을 미터로 변환하는 스케일. 기본 1000.0 (mm→m).
        Coord3D_ABC32f 사용 시 1.0으로 설정.
    depth_min : float
        최소 유효 깊이 (m). Blaze-112 최소 0.3m.
    depth_max : float
        최대 유효 깊이 (m). Blaze-112 최대 3.0m (실용 1.5m).
    confidence_map : np.ndarray, optional
        (H, W) uint16 confidence map. Blaze-112이 제공.
        제공 시 threshold 미만 픽셀 제거.
    confidence_threshold : int
        confidence map 필터링 임계값. 기본 100.

    Returns
    -------
    o3d.geometry.PointCloud
        변환된 포인트 클라우드.
    """
    if o3d is None:
        raise ImportError("open3d가 설치되지 않았습니다. pip install open3d")

    H, W = depth_map.shape[:2]

    # depth를 미터 단위로 변환
    depth_m = depth_map.astype(np.float64) / depth_scale

    # 유효 마스크: depth 범위
    valid = (depth_m > depth_min) & (depth_m < depth_max) & np.isfinite(depth_m)

    # confidence 필터링
    if confidence_map is not None:
        valid &= confidence_map >= confidence_threshold

    # 픽셀 좌표 생성
    u = np.arange(W)
    v = np.arange(H)
    u, v = np.meshgrid(u, v)

    # Pinhole 모델: (u,v,depth) → (X,Y,Z)
    z = depth_m
    x = (u - cx) * z / fx
    y = (v - cy) * z / fy

    # 유효 포인트만 추출
    points = np.stack([x[valid], y[valid], z[valid]], axis=-1)

    # Open3D PointCloud 생성
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)

    # 칼라 매핑
    if color_image is not None:
        if color_image.shape[:2] != (H, W):
            raise ValueError(
                f"color_image shape {color_image.shape[:2]} != depth_map shape ({H}, {W})"
            )
        # BGR → RGB, 0~1 범위
        rgb = color_image[..., ::-1].astype(np.float64) / 255.0
        colors = rgb[valid]
        pcd.colors = o3d.utility.Vector3dVector(colors)

    return pcd


def create_rgbd_from_blaze(
    depth_map: np.ndarray,
    color_image: np.ndarray,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    depth_scale: float = 1000.0,
    depth_max: float = 3.0,
) -> "o3d.geometry.PointCloud":
    """
    Open3D RGBDImage 경유 변환 (Open3D 내장 함수 활용).
    color_image와 depth_map 해상도가 같아야 함.
    Blaze-112(640x480) + ace2(2448x2048)는 해상도가 다르므로
    ace2를 640x480으로 리사이즈하거나, depth_to_pointcloud()를 직접 사용.
    """
    if o3d is None:
        raise ImportError("open3d가 설치되지 않았습니다. pip install open3d")

    # Open3D Image 생성
    depth_o3d = o3d.geometry.Image(depth_map.astype(np.uint16))
    color_rgb = color_image[..., ::-1].copy()  # BGR → RGB
    color_o3d = o3d.geometry.Image(color_rgb.astype(np.uint8))

    rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
        color_o3d,
        depth_o3d,
        depth_scale=depth_scale,
        depth_trunc=depth_max,
        convert_rgb_to_intensity=False,
    )

    intrinsic = o3d.camera.PinholeCameraIntrinsic()
    intrinsic.set_intrinsics(
        width=depth_map.shape[1],
        height=depth_map.shape[0],
        fx=fx, fy=fy, cx=cx, cy=cy,
    )

    pcd = o3d.geometry.PointCloud.create_from_rgbd_image(rgbd, intrinsic)
    return pcd


# Blaze-112 기본 카메라 파라미터 (추정값, 실제 캘리브레이션 필요)
BLAZE_112_INTRINSICS = {
    "width": 640,
    "height": 480,
    "fx": 460.0,  # 추정값 — 카메라 입고 후 캘리브레이션
    "fy": 460.0,
    "cx": 320.0,
    "cy": 240.0,
}
