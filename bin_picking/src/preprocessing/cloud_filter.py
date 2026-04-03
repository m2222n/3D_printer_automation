"""
L2 전처리 모듈 — 포인트 클라우드 필터링 파이프라인
===================================================
ToF 카메라(Basler Blaze-112) + SLA 레진 부품 환경에 맞춘 전처리.

파이프라인 5단계:
    1. ROI 크롭 (빈 영역만)
    2. 이상치 제거 (Statistical Outlier Removal)
    3. 다운샘플링 (Voxel Grid)
    4. 바닥면 제거 (RANSAC Plane Segmentation)
    5. 법선 추정 (orient toward camera)

사용법:
    from bin_picking.src.preprocessing.cloud_filter import CloudFilter
    cf = CloudFilter()
    pcd_objects = cf.process(raw_pcd)
"""

import numpy as np

try:
    import open3d as o3d
except ImportError:
    o3d = None


# 레진별 추천 파라미터 (논문 리뷰 + tutorials/11 결과)
RESIN_PRESETS = {
    "grey": {
        "voxel_size": 0.002,
        "sor_nb_neighbors": 20,
        "sor_std_ratio": 2.0,
        "normal_radius": 0.006,
        "normal_max_nn": 30,
        "plane_distance": 0.005,
    },
    "white": {
        "voxel_size": 0.002,
        "sor_nb_neighbors": 20,
        "sor_std_ratio": 2.0,
        "normal_radius": 0.006,
        "normal_max_nn": 30,
        "plane_distance": 0.005,
    },
    "clear": {
        "voxel_size": 0.003,  # 반투명 → 노이즈 큼 → voxel 증가
        "sor_nb_neighbors": 30,
        "sor_std_ratio": 1.5,  # 더 엄격하게
        "normal_radius": 0.009,
        "normal_max_nn": 30,
        "plane_distance": 0.005,
    },
    "flexible": {
        "voxel_size": 0.002,
        "sor_nb_neighbors": 20,
        "sor_std_ratio": 2.0,
        "normal_radius": 0.006,
        "normal_max_nn": 30,
        "plane_distance": 0.005,
    },
}


class CloudFilter:
    """L2 전처리 파이프라인."""

    def __init__(
        self,
        voxel_size: float = 0.002,
        sor_nb_neighbors: int = 20,
        sor_std_ratio: float = 2.0,
        normal_radius: float = 0.006,
        normal_max_nn: int = 30,
        plane_distance: float = 0.005,
        plane_ransac_n: int = 3,
        plane_iterations: int = 1000,
        roi_min: np.ndarray | None = None,
        roi_max: np.ndarray | None = None,
    ):
        """
        Parameters
        ----------
        voxel_size : float
            다운샘플링 voxel 크기 (m). 기본 2mm.
        sor_nb_neighbors : int
            SOR 이웃 수. 기본 20.
        sor_std_ratio : float
            SOR 표준편차 비율. 기본 2.0.
        normal_radius : float
            법선 추정 검색 반경 (m). 기본 6mm.
        normal_max_nn : int
            법선 추정 최대 이웃 수. 기본 30.
        plane_distance : float
            바닥면 RANSAC 거리 임계값 (m). 기본 5mm.
        plane_ransac_n : int
            RANSAC 평면 최소 점 수. 기본 3.
        plane_iterations : int
            RANSAC 반복 수. 기본 1000.
        roi_min, roi_max : np.ndarray, optional
            ROI 크롭 범위 [x, y, z]. None이면 크롭 안 함.
        """
        if o3d is None:
            raise ImportError("open3d가 설치되지 않았습니다.")

        self.voxel_size = voxel_size
        self.sor_nb_neighbors = sor_nb_neighbors
        self.sor_std_ratio = sor_std_ratio
        self.normal_radius = normal_radius
        self.normal_max_nn = normal_max_nn
        self.plane_distance = plane_distance
        self.plane_ransac_n = plane_ransac_n
        self.plane_iterations = plane_iterations
        self.roi_min = roi_min
        self.roi_max = roi_max

        # 처리 결과 저장
        self.stats = {}

    @classmethod
    def from_resin(cls, resin_type: str, **overrides) -> "CloudFilter":
        """레진 타입에 맞는 프리셋으로 생성.

        Parameters
        ----------
        resin_type : str
            "grey", "white", "clear", "flexible" 중 하나.
        **overrides
            프리셋 값을 덮어쓸 키워드 인자.
        """
        resin_type = resin_type.lower()
        if resin_type not in RESIN_PRESETS:
            raise ValueError(
                f"알 수 없는 레진: {resin_type}. "
                f"사용 가능: {list(RESIN_PRESETS.keys())}"
            )
        params = {**RESIN_PRESETS[resin_type], **overrides}
        return cls(**params)

    def crop_roi(self, pcd: "o3d.geometry.PointCloud") -> "o3d.geometry.PointCloud":
        """1단계: ROI 크롭."""
        if self.roi_min is None or self.roi_max is None:
            return pcd

        bbox = o3d.geometry.AxisAlignedBoundingBox(
            min_bound=self.roi_min, max_bound=self.roi_max
        )
        cropped = pcd.crop(bbox)
        self.stats["roi_before"] = len(pcd.points)
        self.stats["roi_after"] = len(cropped.points)
        return cropped

    def remove_outliers(
        self, pcd: "o3d.geometry.PointCloud"
    ) -> "o3d.geometry.PointCloud":
        """2단계: 통계적 이상치 제거 (SOR)."""
        n_before = len(pcd.points)
        pcd_clean, _ = pcd.remove_statistical_outlier(
            nb_neighbors=self.sor_nb_neighbors,
            std_ratio=self.sor_std_ratio,
        )
        self.stats["sor_before"] = n_before
        self.stats["sor_after"] = len(pcd_clean.points)
        self.stats["sor_removed"] = n_before - len(pcd_clean.points)
        return pcd_clean

    def downsample(self, pcd: "o3d.geometry.PointCloud") -> "o3d.geometry.PointCloud":
        """3단계: Voxel 다운샘플링."""
        n_before = len(pcd.points)
        pcd_down = pcd.voxel_down_sample(self.voxel_size)
        self.stats["downsample_before"] = n_before
        self.stats["downsample_after"] = len(pcd_down.points)
        return pcd_down

    def remove_plane(
        self, pcd: "o3d.geometry.PointCloud"
    ) -> tuple["o3d.geometry.PointCloud", np.ndarray]:
        """4단계: 바닥면 제거 (RANSAC)."""
        plane_model, inliers = pcd.segment_plane(
            distance_threshold=self.plane_distance,
            ransac_n=self.plane_ransac_n,
            num_iterations=self.plane_iterations,
        )
        pcd_objects = pcd.select_by_index(inliers, invert=True)
        self.stats["plane_model"] = plane_model
        self.stats["plane_inliers"] = len(inliers)
        self.stats["plane_after"] = len(pcd_objects.points)
        return pcd_objects, np.array(plane_model)

    def estimate_normals(
        self,
        pcd: "o3d.geometry.PointCloud",
        camera_location: np.ndarray = np.array([0, 0, 0]),
    ) -> "o3d.geometry.PointCloud":
        """5단계: 법선 추정 + 카메라 방향 정렬."""
        pcd.estimate_normals(
            search_param=o3d.geometry.KDTreeSearchParamHybrid(
                radius=self.normal_radius, max_nn=self.normal_max_nn
            )
        )
        pcd.orient_normals_towards_camera_location(camera_location)
        self.stats["normals_count"] = len(pcd.normals)
        return pcd

    def process(
        self,
        pcd: "o3d.geometry.PointCloud",
        camera_location: np.ndarray = np.array([0, 0, 0]),
        skip_plane: bool = False,
    ) -> "o3d.geometry.PointCloud":
        """전처리 파이프라인 전체 실행.

        Parameters
        ----------
        pcd : o3d.geometry.PointCloud
            원본 포인트 클라우드.
        camera_location : np.ndarray
            카메라 위치 (법선 방향 정렬용).
        skip_plane : bool
            True면 바닥면 제거 건너뛰기 (이미 제거된 경우).

        Returns
        -------
        o3d.geometry.PointCloud
            전처리 완료된 포인트 클라우드 (부품만).
        """
        self.stats = {"input_points": len(pcd.points)}

        # 1. ROI 크롭
        pcd = self.crop_roi(pcd)

        # 2. 이상치 제거
        pcd = self.remove_outliers(pcd)

        # 3. 다운샘플링
        pcd = self.downsample(pcd)

        # 4. 바닥면 제거
        if not skip_plane:
            pcd, _ = self.remove_plane(pcd)

        # 5. 법선 추정
        pcd = self.estimate_normals(pcd, camera_location)

        self.stats["output_points"] = len(pcd.points)
        return pcd

    def print_stats(self):
        """전처리 통계 출력."""
        s = self.stats
        print(f"  입력: {s.get('input_points', '?'):,}")
        if "roi_after" in s:
            print(f"  ROI 크롭: {s['roi_before']:,} → {s['roi_after']:,}")
        if "sor_removed" in s:
            print(f"  이상치 제거: {s['sor_before']:,} → {s['sor_after']:,} ({s['sor_removed']} 제거)")
        if "downsample_after" in s:
            print(f"  다운샘플링: {s['downsample_before']:,} → {s['downsample_after']:,} ({self.voxel_size*1000:.0f}mm)")
        if "plane_model" in s:
            a, b, c, d = s["plane_model"]
            print(f"  바닥면: {a:.3f}x+{b:.3f}y+{c:.3f}z+{d:.3f}=0 ({s['plane_inliers']} inliers)")
        if "normals_count" in s:
            print(f"  법선: {s['normals_count']:,}")
        print(f"  출력: {s.get('output_points', '?'):,}")
