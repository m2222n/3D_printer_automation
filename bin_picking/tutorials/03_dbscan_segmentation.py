"""
DBSCAN 클러스터링으로 씬에서 개별 부품 분할 (L3)
=================================================

빈(bin) 안에 여러 부품이 쌓여있는 포인트 클라우드를
DBSCAN으로 개별 부품 클러스터로 분할하는 실습.

파이프라인: L1 취득 → **L2 전처리 → L3 DBSCAN** → L4 인식/자세

실행: source .venv/binpick/bin/activate && python bin_picking/tutorials/03_dbscan_segmentation.py
"""

import copy
import numpy as np
import open3d as o3d

VOXEL_SIZE = 0.002  # 2mm


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 1. 시뮬레이션 씬 생성 (빈 안에 부품 5개 랜덤 배치)
# ============================================================
print_section("Step 1: 시뮬레이션 씬 생성 (부품 5개)")

np.random.seed(42)
scene_points = []

# SLA 부품 크기 ~20-40mm, 서로 떨어진 위치에 배치
shapes = [
    ("torus", o3d.geometry.TriangleMesh.create_torus(0.015, 0.005)),
    ("box", o3d.geometry.TriangleMesh.create_box(0.03, 0.02, 0.01)),
    ("sphere", o3d.geometry.TriangleMesh.create_sphere(0.012)),
    ("cylinder", o3d.geometry.TriangleMesh.create_cylinder(0.008, 0.025)),
    ("cone", o3d.geometry.TriangleMesh.create_cone(0.01, 0.03)),
]

part_clouds = []
for i, (name, mesh) in enumerate(shapes):
    mesh.compute_vertex_normals()
    pcd = mesh.sample_points_uniformly(2000)

    # 랜덤 위치에 배치 (빈 크기 ~200×200mm 가정)
    offset = np.array([
        np.random.uniform(-0.05, 0.05),
        np.random.uniform(-0.05, 0.05),
        np.random.uniform(0.0, 0.03),
    ])
    # 랜덤 회전
    R = pcd.get_rotation_matrix_from_xyz(np.random.uniform(0, np.pi, 3))
    pcd.rotate(R, center=pcd.get_center())
    pcd.translate(offset)

    part_clouds.append(pcd)
    print(f"  부품 {i+1} ({name}): center={offset*1000}")

# 모든 부품을 하나의 씬으로 합침
scene_pcd = o3d.geometry.PointCloud()
for pc in part_clouds:
    scene_pcd += pc

# 약간의 노이즈 추가 (ToF 카메라 노이즈 시뮬레이션)
noise = np.random.normal(0, 0.0003, size=np.asarray(scene_pcd.points).shape)
scene_pcd.points = o3d.utility.Vector3dVector(
    np.asarray(scene_pcd.points) + noise
)

print(f"\n  전체 씬: {len(scene_pcd.points):,} points")


# ============================================================
# 2. 전처리 (L2)
# ============================================================
print_section("Step 2: 전처리")

# 2-1. Statistical Outlier Removal (SOR) — 노이즈 제거
cl, ind = scene_pcd.remove_statistical_outlier(
    nb_neighbors=20,
    std_ratio=2.0,
)
scene_clean = scene_pcd.select_by_index(ind)
removed = len(scene_pcd.points) - len(scene_clean.points)
print(f"  SOR: {removed} outliers 제거 ({len(scene_clean.points):,} 남음)")

# 2-2. Voxel 다운샘플링
scene_down = scene_clean.voxel_down_sample(VOXEL_SIZE)
print(f"  다운샘플링: {len(scene_clean.points):,} → {len(scene_down.points):,}")

# 2-3. 법선 추정
scene_down.estimate_normals(
    o3d.geometry.KDTreeSearchParamHybrid(radius=VOXEL_SIZE * 4, max_nn=30)
)
scene_down.orient_normals_towards_camera_location(
    camera_location=np.array([0.0, 0.0, 0.5])  # 카메라가 위에서 내려다봄
)
print(f"  법선 추정 완료 (카메라 위치: z=0.5m)")


# ============================================================
# 3. 평면 제거 (빈 바닥 제거) — RANSAC Plane Segmentation
# ============================================================
print_section("Step 3: 빈 바닥 평면 제거 (RANSAC)")

# 실제 빈피킹에서는 빈 바닥이 가장 큰 평면
# 시뮬레이션에서는 z≈0 평면을 바닥으로 가정
plane_model, inliers = scene_down.segment_plane(
    distance_threshold=0.002,  # 2mm 이내 점들을 평면으로 판단
    ransac_n=3,
    num_iterations=1000,
)
a, b, c, d = plane_model
print(f"  감지된 평면: {a:.3f}x + {b:.3f}y + {c:.3f}z + {d:.3f} = 0")
print(f"  평면 포인트: {len(inliers):,}")

# 평면 제거 (부품만 남김)
objects_pcd = scene_down.select_by_index(inliers, invert=True)
print(f"  부품 포인트: {len(objects_pcd.points):,}")


# ============================================================
# 4. DBSCAN 클러스터링 (L3)
# ============================================================
print_section("Step 4: DBSCAN 클러스터링")

# DBSCAN 파라미터:
#   eps: 이웃 판단 거리 (voxel_size의 2~3배)
#   min_points: 클러스터 최소 포인트 수 (노이즈 필터링)
eps = VOXEL_SIZE * 2.5  # 5mm
min_points = 10  # SLA 부품은 작으므로 낮게

labels = np.array(objects_pcd.cluster_dbscan(
    eps=eps,
    min_points=min_points,
    print_progress=True,
))

max_label = labels.max()
n_clusters = max_label + 1
n_noise = (labels == -1).sum()

print(f"\n  DBSCAN 결과:")
print(f"    eps: {eps*1000:.1f}mm")
print(f"    min_points: {min_points}")
print(f"    클러스터 수: {n_clusters}")
print(f"    노이즈 포인트: {n_noise}")

# 클러스터별 정보
clusters = []
for i in range(n_clusters):
    cluster_idx = np.where(labels == i)[0]
    cluster_pcd = objects_pcd.select_by_index(cluster_idx)
    bbox = cluster_pcd.get_axis_aligned_bounding_box()
    extent = bbox.get_extent() * 1000  # mm

    clusters.append({
        "id": i,
        "n_points": len(cluster_idx),
        "center": np.asarray(cluster_pcd.get_center()) * 1000,
        "extent_mm": extent,
        "pcd": cluster_pcd,
    })
    print(f"    클러스터 {i}: {len(cluster_idx):,} points, "
          f"크기 {extent[0]:.0f}×{extent[1]:.0f}×{extent[2]:.0f}mm")


# ============================================================
# 5. 클러스터 필터링 (크기/포인트 수 기반)
# ============================================================
print_section("Step 5: 클러스터 필터링")

MIN_CLUSTER_POINTS = 50   # 너무 작은 클러스터 제외
MIN_EXTENT_MM = 5.0       # 5mm 미만 제외
MAX_EXTENT_MM = 100.0     # 100mm 초과 제외 (부품이 아닌 것)

valid_clusters = []
for c in clusters:
    ext = c["extent_mm"]
    if c["n_points"] < MIN_CLUSTER_POINTS:
        print(f"  클러스터 {c['id']}: 제외 (포인트 {c['n_points']} < {MIN_CLUSTER_POINTS})")
        continue
    if max(ext) > MAX_EXTENT_MM or max(ext) < MIN_EXTENT_MM:
        print(f"  클러스터 {c['id']}: 제외 (크기 {max(ext):.0f}mm)")
        continue
    valid_clusters.append(c)
    print(f"  클러스터 {c['id']}: ✅ 유효 ({c['n_points']} points)")

print(f"\n  유효 클러스터: {len(valid_clusters)}/{n_clusters}")


# ============================================================
# 6. 시각화
# ============================================================
print_section("Step 6: 시각화")

# 클러스터별 랜덤 색상
colors = np.zeros((len(labels), 3))
cmap = [
    [1, 0, 0],     # 빨강
    [0, 1, 0],     # 초록
    [0, 0, 1],     # 파랑
    [1, 1, 0],     # 노랑
    [1, 0, 1],     # 마젠타
    [0, 1, 1],     # 시안
    [1, 0.5, 0],   # 주황
    [0.5, 0, 1],   # 보라
]

for i in range(n_clusters):
    color = cmap[i % len(cmap)]
    colors[labels == i] = color

# 노이즈는 회색
colors[labels == -1] = [0.5, 0.5, 0.5]

vis_pcd = copy.deepcopy(objects_pcd)
vis_pcd.colors = o3d.utility.Vector3dVector(colors)

# 바운딩 박스 추가
bboxes = []
for c in valid_clusters:
    bbox = c["pcd"].get_axis_aligned_bounding_box()
    bbox.color = cmap[c["id"] % len(cmap)]
    bboxes.append(bbox)

coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.03)

print("  클러스터 색상: 부품별 다른 색, 회색=노이즈")
print("  바운딩 박스: 유효 클러스터만 표시")
print("  창을 닫으면 종료합니다.")
o3d.visualization.draw_geometries(
    [vis_pcd, coord] + bboxes,
    window_name="DBSCAN Segmentation Result",
    width=1024,
    height=768,
)


# ============================================================
# 7. 다음 단계: 각 클러스터를 L4 인식 파이프라인으로 전달
# ============================================================
print_section("Step 7: L4 연결 (각 클러스터 → FPFH+RANSAC+ICP)")

print("""
  실제 빈피킹에서는 각 유효 클러스터를 순회하며:

  for cluster in valid_clusters:
      # 1. 클러스터 전처리 (이미 다운샘플링+법선 완료)
      cluster_fpfh = compute_fpfh_feature(cluster["pcd"], ...)

      # 2. 30종 레퍼런스와 매칭 (가장 높은 fitness 선택)
      best_match = None
      for ref in reference_models:  # pickle 캐시에서 로드
          result = registration_ransac(cluster, ref, ...)
          if result.fitness > best_match.fitness:
              best_match = result

      # 3. ICP 정밀 정합
      result_icp = registration_icp(cluster, best_ref, init=best_match, ...)

      # 4. 6DoF 자세 추출 → L5 그래스프 포인트 계산
      T = result_icp.transformation
      grasp_pose = compute_grasp(T, part_type)

      # 5. Modbus TCP → HCR-10L 로봇
      send_to_robot(grasp_pose)
""")

print("\n✅ DBSCAN 분할 튜토리얼 완료!")
