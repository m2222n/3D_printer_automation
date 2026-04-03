"""
L3 분할 모듈 — DBSCAN 클러스터링
==================================
전처리된 포인트 클라우드에서 개별 부품을 분할.

빈피킹 특성:
    - 부품은 종류별 정리 (랜덤 힙 아님), 간격 5~15mm
    - 목표: 과분할 <5%, 미분할 <3%, 프레임당 500ms 이내

사용법:
    from bin_picking.src.segmentation.dbscan_segmenter import DBSCANSegmenter
    segmenter = DBSCANSegmenter()
    clusters = segmenter.segment(pcd_objects)
"""

import numpy as np

try:
    import open3d as o3d
except ImportError:
    o3d = None


class Cluster:
    """분할된 개별 부품 클러스터."""

    def __init__(self, pcd: "o3d.geometry.PointCloud", label: int):
        self.pcd = pcd
        self.label = label
        self._bbox = None
        self._center = None
        self._extent = None

    @property
    def n_points(self) -> int:
        return len(self.pcd.points)

    @property
    def bbox(self) -> "o3d.geometry.AxisAlignedBoundingBox":
        if self._bbox is None:
            self._bbox = self.pcd.get_axis_aligned_bounding_box()
        return self._bbox

    @property
    def center(self) -> np.ndarray:
        if self._center is None:
            self._center = self.bbox.get_center()
        return self._center

    @property
    def extent(self) -> np.ndarray:
        """바운딩 박스 크기 [x, y, z] (m)."""
        if self._extent is None:
            self._extent = self.bbox.get_extent()
        return self._extent

    @property
    def extent_mm(self) -> np.ndarray:
        """바운딩 박스 크기 [x, y, z] (mm)."""
        return self.extent * 1000.0

    @property
    def max_dim_mm(self) -> float:
        """최대 치수 (mm)."""
        return float(self.extent_mm.max())

    @property
    def min_dim_mm(self) -> float:
        """최소 치수 (mm)."""
        return float(self.extent_mm.min())

    def __repr__(self) -> str:
        e = self.extent_mm
        return (
            f"Cluster(label={self.label}, pts={self.n_points:,}, "
            f"size={e[0]:.0f}x{e[1]:.0f}x{e[2]:.0f}mm)"
        )


class DBSCANSegmenter:
    """L3 DBSCAN 기반 부품 분할."""

    def __init__(
        self,
        eps: float = 0.008,
        min_points: int = 100,
        min_cluster_points: int = 50,
        max_cluster_points: int = 100000,
        min_size_mm: float = 5.0,
        max_size_mm: float = 200.0,
    ):
        """
        Parameters
        ----------
        eps : float
            DBSCAN 이웃 거리 (m). 기본 8mm.
            부품 간격 5~15mm → eps < 5mm이면 과분할, > 15mm이면 미분할.
        min_points : int
            DBSCAN 최소 클러스터 포인트 수. 기본 100.
        min_cluster_points : int
            결과에서 제외할 최소 포인트 수. 기본 50.
        max_cluster_points : int
            결과에서 제외할 최대 포인트 수. 기본 100,000.
        min_size_mm : float
            최소 바운딩 박스 치수 (mm). 기본 5mm.
        max_size_mm : float
            최대 바운딩 박스 치수 (mm). 기본 200mm.
        """
        if o3d is None:
            raise ImportError("open3d가 설치되지 않았습니다.")

        self.eps = eps
        self.min_points = min_points
        self.min_cluster_points = min_cluster_points
        self.max_cluster_points = max_cluster_points
        self.min_size_mm = min_size_mm
        self.max_size_mm = max_size_mm

        # 통계
        self.stats = {}

    def segment(
        self, pcd: "o3d.geometry.PointCloud"
    ) -> list[Cluster]:
        """DBSCAN으로 부품 분할.

        Parameters
        ----------
        pcd : o3d.geometry.PointCloud
            전처리 완료된 포인트 클라우드 (바닥면 제거 후).

        Returns
        -------
        list[Cluster]
            크기 필터 통과한 클러스터 목록 (포인트 수 내림차순).
        """
        n_input = len(pcd.points)

        # DBSCAN 클러스터링
        labels = np.asarray(
            pcd.cluster_dbscan(
                eps=self.eps,
                min_points=self.min_points,
                print_progress=False,
            )
        )

        n_total = labels.max() + 1
        n_noise = int((labels == -1).sum())

        # 클러스터 추출 + 필터링
        clusters = []
        rejected_small = 0
        rejected_large = 0
        rejected_size = 0

        for i in range(n_total):
            mask = labels == i
            indices = np.where(mask)[0]
            n_pts = len(indices)

            # 포인트 수 필터
            if n_pts < self.min_cluster_points:
                rejected_small += 1
                continue
            if n_pts > self.max_cluster_points:
                rejected_large += 1
                continue

            cluster_pcd = pcd.select_by_index(indices)
            cluster = Cluster(cluster_pcd, label=i)

            # 크기 필터
            if cluster.max_dim_mm < self.min_size_mm:
                rejected_size += 1
                continue
            if cluster.max_dim_mm > self.max_size_mm:
                rejected_size += 1
                continue

            clusters.append(cluster)

        # 포인트 수 내림차순 정렬
        clusters.sort(key=lambda c: c.n_points, reverse=True)

        # 통계 저장
        self.stats = {
            "input_points": n_input,
            "total_clusters": n_total,
            "noise_points": n_noise,
            "rejected_small": rejected_small,
            "rejected_large": rejected_large,
            "rejected_size": rejected_size,
            "valid_clusters": len(clusters),
        }

        return clusters

    def print_stats(self):
        """분할 통계 출력."""
        s = self.stats
        print(f"  입력: {s.get('input_points', '?'):,} pts")
        print(f"  DBSCAN 파라미터: eps={self.eps*1000:.0f}mm, min_points={self.min_points}")
        print(f"  전체 클러스터: {s.get('total_clusters', '?')}")
        print(f"  노이즈: {s.get('noise_points', '?')} pts")
        if s.get("rejected_small", 0) > 0:
            print(f"  거부 (포인트 부족): {s['rejected_small']}")
        if s.get("rejected_large", 0) > 0:
            print(f"  거부 (포인트 과다): {s['rejected_large']}")
        if s.get("rejected_size", 0) > 0:
            print(f"  거부 (크기 범위 초과): {s['rejected_size']}")
        print(f"  유효 클러스터: {s.get('valid_clusters', '?')}")

    def print_clusters(self, clusters: list[Cluster]):
        """클러스터 목록 출력."""
        for c in clusters:
            print(f"  {c}")
