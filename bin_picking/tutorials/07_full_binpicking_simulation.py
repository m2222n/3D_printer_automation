"""
빈피킹 전체 파이프라인 시뮬레이션 (L2→L3→L4→L5)
================================================

30종 SLA 부품 빈피킹의 전체 흐름을 하나의 스크립트로 구현.
실제 카메라/로봇 없이 시뮬레이션 데이터로 파이프라인 검증.

파이프라인:
  Step 1: 레퍼런스 모델 3종 생성 + FPFH 캐시 (pickle)
  Step 2: 시뮬레이션 씬 생성 (5개 부품, 랜덤 자세 + 노이즈)
  Step 3: L2 전처리 (SOR → 다운샘플링 → 법선)
  Step 4: 바닥 평면 제거 (RANSAC Plane Segmentation)
  Step 5: L3 DBSCAN 클러스터 분할
  Step 6: L4 각 클러스터 × 전체 레퍼런스 매칭 (FPFH+RANSAC+ICP)
  Step 7: 최적 매칭 선택 + 임계값 거부
  Step 8: L5 6DoF 자세 + 그래스프 포인트 계산
  Step 9: 결과 테이블
  Step 10: 성능 요약 (총 시간, 부품당 시간, 인식률)

목표: 부품당 2초 이내, 인식률 85% 이상

실행: source .venv/binpick/bin/activate && python bin_picking/tutorials/07_full_binpicking_simulation.py
"""

import argparse
import copy
import os
import pickle
import time
import numpy as np
import open3d as o3d

parser = argparse.ArgumentParser()
parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기 (터미널 전용)")
args = parser.parse_args()

# ============================================================
# 0. 빈피킹 파라미터 (실제 SLA 부품 스케일, 2mm voxel)
# ============================================================
VOXEL_SIZE = 0.002       # 2mm — 빈피킹 SLA 부품용
FPFH_RADIUS = VOXEL_SIZE * 5       # 10mm
FPFH_MAX_NN = 100
NORMAL_RADIUS = VOXEL_SIZE * 4     # 8mm
NORMAL_MAX_NN = 30
RANSAC_DISTANCE = VOXEL_SIZE * 1.5  # 3mm
RANSAC_MAX_ITERATION = 100000
RANSAC_CONFIDENCE = 0.999
ICP_DISTANCE = VOXEL_SIZE * 0.5     # 1mm

# 빈피킹 판정 임계값
FITNESS_THRESHOLD = 0.3   # 이 이상이면 매칭 수락
RMSE_THRESHOLD = 0.003    # 3mm 초과하면 거부
MIN_CORRESPONDENCES = 30  # 대응점 30개 미만이면 거부

# DBSCAN 파라미터
DBSCAN_EPS = VOXEL_SIZE * 2.5  # 5mm
DBSCAN_MIN_POINTS = 10

# 클러스터 필터
MIN_CLUSTER_POINTS = 30
MIN_EXTENT_MM = 5.0
MAX_EXTENT_MM = 100.0

# 캐시 디렉토리
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# 시뮬레이션 씬 부품 수 + 카메라 위치
N_SCENE_PARTS = 5
CAMERA_LOCATION = np.array([0.0, 0.0, 0.5])  # 카메라가 50cm 위에서 내려다봄

# 재현 가능하도록 시드 고정
np.random.seed(42)


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 유틸리티 함수
# ============================================================
def preprocess(pcd, voxel_size=VOXEL_SIZE):
    """전처리: 다운샘플링 → 법선 → 카메라 방향 정렬 → FPFH"""
    pcd_down = pcd.voxel_down_sample(voxel_size)
    pcd_down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=NORMAL_RADIUS, max_nn=NORMAL_MAX_NN
        )
    )
    pcd_down.orient_normals_towards_camera_location(
        camera_location=CAMERA_LOCATION
    )
    fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        pcd_down,
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=FPFH_RADIUS, max_nn=FPFH_MAX_NN
        ),
    )
    return pcd_down, fpfh


def run_registration(source_down, source_fpfh, target_down, target_fpfh):
    """FPFH+RANSAC 초기 정합 → ICP Point-to-Plane 정밀 정합"""
    # RANSAC
    result_ransac = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
        source_down, target_down, source_fpfh, target_fpfh,
        mutual_filter=True,
        max_correspondence_distance=RANSAC_DISTANCE,
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(
            with_scaling=False
        ),
        ransac_n=3,
        checkers=[
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(RANSAC_DISTANCE),
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
        ],
        criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(
            max_iteration=RANSAC_MAX_ITERATION,
            confidence=RANSAC_CONFIDENCE,
        ),
    )

    # ICP Point-to-Plane + TukeyLoss
    loss = o3d.pipelines.registration.TukeyLoss(k=ICP_DISTANCE)
    estimation = o3d.pipelines.registration.TransformationEstimationPointToPlane(loss)
    result_icp = o3d.pipelines.registration.registration_icp(
        source_down, target_down,
        max_correspondence_distance=ICP_DISTANCE * 3,
        init=result_ransac.transformation,
        estimation_method=estimation,
        criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
            relative_fitness=1e-6, relative_rmse=1e-6, max_iteration=50
        ),
    )
    return result_icp


# ============================================================
# Step 1: 레퍼런스 모델 생성 + FPFH 캐시 (pickle)
# ============================================================
print_section("Step 1: 레퍼런스 모델 3종 + FPFH 캐시")

CACHE_FILE = os.path.join(CACHE_DIR, "sim_references.pkl")

# 레퍼런스 메쉬 정의 (빈피킹 스케일 20~40mm)
REF_DEFINITIONS = {
    "torus": lambda: _center(o3d.geometry.TriangleMesh.create_torus(
        torus_radius=0.015, tube_radius=0.005  # 외경 ~30mm
    )),
    "box": lambda: _center(o3d.geometry.TriangleMesh.create_box(
        0.030, 0.020, 0.010  # 30×20×10mm
    )),
    "cylinder": lambda: _center(o3d.geometry.TriangleMesh.create_cylinder(
        radius=0.008, height=0.025  # 지름 16mm × 높이 25mm
    )),
}


def _center(mesh):
    """메쉬 중심을 원점으로 이동"""
    mesh.translate(-mesh.get_center())
    mesh.compute_vertex_normals()
    return mesh


# 캐시가 있으면 로드, 없으면 생성
if os.path.exists(CACHE_FILE):
    print(f"  캐시 로드: {CACHE_FILE}")
    with open(CACHE_FILE, "rb") as f:
        raw_cache = pickle.load(f)
    reference_cache = {}
    for name, data in raw_cache.items():
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(data["points"])
        pcd.normals = o3d.utility.Vector3dVector(data["normals"])
        fpfh = o3d.pipelines.registration.Feature()
        fpfh.data = data["fpfh"]
        reference_cache[name] = {"pcd_down": pcd, "fpfh": fpfh}
        print(f"    {name}: {len(pcd.points)} points (캐시)")
else:
    print("  캐시 없음 → 새로 생성")
    reference_cache = {}
    for name, mesh_fn in REF_DEFINITIONS.items():
        t0 = time.time()
        mesh = mesh_fn()
        pcd = mesh.sample_points_uniformly(5000)
        pcd_down, fpfh = preprocess(pcd)
        reference_cache[name] = {
            "pcd_down": pcd_down,
            "fpfh": fpfh,
        }
        elapsed = time.time() - t0
        print(f"    {name}: {len(pcd_down.points)} points, "
              f"FPFH {fpfh.dimension()}D × {fpfh.num()}, {elapsed:.2f}s")

    # pickle 저장 (Open3D 객체 → numpy 변환)
    serializable = {}
    for name, data in reference_cache.items():
        serializable[name] = {
            "points": np.asarray(data["pcd_down"].points),
            "normals": np.asarray(data["pcd_down"].normals),
            "fpfh": np.asarray(data["fpfh"].data),
        }
    with open(CACHE_FILE, "wb") as f:
        pickle.dump(serializable, f)
    print(f"  캐시 저장: {CACHE_FILE}")


# ============================================================
# Step 2: 시뮬레이션 씬 생성 (5개 부품, 랜덤 자세 + 노이즈)
# ============================================================
print_section("Step 2: 시뮬레이션 씬 생성 (부품 5개)")

# 씬에 배치할 부품 (3종에서 랜덤 선택)
ref_names = list(REF_DEFINITIONS.keys())
scene_assignments = []  # (이름, ground_truth_T) 기록

scene_pcd = o3d.geometry.PointCloud()

# 바닥 평면 추가 (200×200mm, z=0)
# 실제 빈피킹에서는 빈 바닥이 항상 있음
ground_x = np.random.uniform(-0.10, 0.10, 3000)
ground_y = np.random.uniform(-0.10, 0.10, 3000)
ground_z = np.random.normal(0.0, 0.0002, 3000)  # z≈0, 약간의 노이즈
ground_pcd = o3d.geometry.PointCloud()
ground_pcd.points = o3d.utility.Vector3dVector(
    np.column_stack([ground_x, ground_y, ground_z])
)
scene_pcd += ground_pcd
print(f"  바닥 평면: {len(ground_pcd.points)} points (200×200mm)")

# 부품 5개 배치
for i in range(N_SCENE_PARTS):
    # 랜덤으로 부품 종류 선택
    part_name = ref_names[i % len(ref_names)]
    mesh = REF_DEFINITIONS[part_name]()
    pcd = mesh.sample_points_uniformly(3000)

    # 랜덤 6DoF 자세 (빈 안에서의 부품 위치)
    euler = np.random.uniform(-np.pi, np.pi, 3)
    R = pcd.get_rotation_matrix_from_xyz(euler)
    offset = np.array([
        np.random.uniform(-0.06, 0.06),  # x: ±60mm
        np.random.uniform(-0.06, 0.06),  # y: ±60mm
        np.random.uniform(0.005, 0.035),  # z: 5~35mm (바닥 위)
    ])

    pcd.rotate(R, center=pcd.get_center())
    pcd.translate(offset)

    # Ground truth 변환 기록
    T_gt = np.eye(4)
    T_gt[:3, :3] = R
    T_gt[:3, 3] = offset
    scene_assignments.append((part_name, T_gt))

    scene_pcd += pcd
    print(f"  부품 {i}: {part_name}, 위치=({offset[0]*1000:+.0f}, "
          f"{offset[1]*1000:+.0f}, {offset[2]*1000:+.0f})mm")

# ToF 카메라 노이즈 추가 (Blaze-112: ~0.3mm 표준편차)
noise = np.random.normal(0, 0.0003, size=np.asarray(scene_pcd.points).shape)
scene_pcd.points = o3d.utility.Vector3dVector(
    np.asarray(scene_pcd.points) + noise
)
print(f"\n  전체 씬: {len(scene_pcd.points):,} points (바닥 + 부품 {N_SCENE_PARTS}개 + 노이즈)")


# ============================================================
# Step 3: L2 전처리 (SOR → 다운샘플링 → 법선)
# ============================================================
print_section("Step 3: L2 전처리")

t_pipeline_start = time.time()

# 3-1. Statistical Outlier Removal
cl, ind = scene_pcd.remove_statistical_outlier(nb_neighbors=20, std_ratio=2.0)
scene_clean = scene_pcd.select_by_index(ind)
removed = len(scene_pcd.points) - len(scene_clean.points)
print(f"  SOR: {removed} outliers 제거 ({len(scene_clean.points):,} 남음)")

# 3-2. Voxel 다운샘플링
scene_down = scene_clean.voxel_down_sample(VOXEL_SIZE)
print(f"  다운샘플링: {len(scene_clean.points):,} → {len(scene_down.points):,}")

# 3-3. 법선 추정 + 카메라 방향 정렬
scene_down.estimate_normals(
    o3d.geometry.KDTreeSearchParamHybrid(radius=NORMAL_RADIUS, max_nn=NORMAL_MAX_NN)
)
scene_down.orient_normals_towards_camera_location(camera_location=CAMERA_LOCATION)
print(f"  법선 추정 완료 (카메라: z={CAMERA_LOCATION[2]}m)")


# ============================================================
# Step 4: 바닥 평면 제거 (RANSAC Plane Segmentation)
# ============================================================
print_section("Step 4: 바닥 평면 제거 (RANSAC)")

plane_model, inliers = scene_down.segment_plane(
    distance_threshold=VOXEL_SIZE,  # 2mm
    ransac_n=3,
    num_iterations=1000,
)
a, b, c, d = plane_model
print(f"  감지된 평면: {a:.3f}x + {b:.3f}y + {c:.3f}z + {d:.4f} = 0")
print(f"  평면 포인트: {len(inliers):,}")

objects_pcd = scene_down.select_by_index(inliers, invert=True)
print(f"  부품 포인트: {len(objects_pcd.points):,}")


# ============================================================
# Step 5: L3 DBSCAN 클러스터 분할
# ============================================================
print_section("Step 5: L3 DBSCAN 클러스터링")

labels = np.array(objects_pcd.cluster_dbscan(
    eps=DBSCAN_EPS,
    min_points=DBSCAN_MIN_POINTS,
    print_progress=False,
))

max_label = labels.max()
n_clusters = max_label + 1
n_noise = (labels == -1).sum()
print(f"  eps={DBSCAN_EPS*1000:.1f}mm, min_points={DBSCAN_MIN_POINTS}")
print(f"  클러스터 수: {n_clusters}, 노이즈: {n_noise}")

# 클러스터 추출 + 필터링
clusters = []
for i in range(n_clusters):
    idx = np.where(labels == i)[0]
    cluster_pcd = objects_pcd.select_by_index(idx)
    bbox = cluster_pcd.get_axis_aligned_bounding_box()
    extent = bbox.get_extent() * 1000  # mm

    # 크기 필터
    if len(idx) < MIN_CLUSTER_POINTS:
        print(f"  클러스터 {i}: 제외 (포인트 {len(idx)} < {MIN_CLUSTER_POINTS})")
        continue
    if max(extent) > MAX_EXTENT_MM or max(extent) < MIN_EXTENT_MM:
        print(f"  클러스터 {i}: 제외 (크기 {max(extent):.0f}mm)")
        continue

    clusters.append({
        "id": i,
        "n_points": len(idx),
        "pcd": cluster_pcd,
        "center": np.asarray(cluster_pcd.get_center()),
        "extent_mm": extent,
    })
    print(f"  클러스터 {i}: {len(idx)} points, "
          f"크기 {extent[0]:.0f}×{extent[1]:.0f}×{extent[2]:.0f}mm [OK]")

print(f"\n  유효 클러스터: {len(clusters)}/{n_clusters}")


# ============================================================
# Step 6~7: L4 매칭 (각 클러스터 × 전체 레퍼런스)
# ============================================================
print_section("Step 6-7: L4 매칭 (클러스터 × 레퍼런스)")

match_results = []  # 최종 매칭 결과

for ci, cluster in enumerate(clusters):
    print(f"\n  --- 클러스터 {cluster['id']} ({cluster['n_points']} points) ---")

    # 클러스터 전처리 (이미 다운샘플링됨, 법선도 있음 → FPFH만 계산)
    cluster_down = cluster["pcd"]

    # 법선이 전파되지 않을 수 있으므로 재계산
    cluster_down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(radius=NORMAL_RADIUS, max_nn=NORMAL_MAX_NN)
    )
    cluster_down.orient_normals_towards_camera_location(camera_location=CAMERA_LOCATION)

    cluster_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        cluster_down,
        o3d.geometry.KDTreeSearchParamHybrid(radius=FPFH_RADIUS, max_nn=FPFH_MAX_NN),
    )

    # 전체 레퍼런스와 매칭 시도
    best_fitness = 0
    best_ref_name = None
    best_result = None
    best_rmse = float("inf")
    t_match_start = time.time()

    for ref_name, ref_data in reference_cache.items():
        ref_down = ref_data["pcd_down"]
        ref_fpfh = ref_data["fpfh"]

        result = run_registration(ref_down, ref_fpfh, cluster_down, cluster_fpfh)

        print(f"    vs {ref_name:>10}: fitness={result.fitness:.4f}, "
              f"RMSE={result.inlier_rmse*1000:.2f}mm, "
              f"corr={len(result.correspondence_set)}")

        # 최고 fitness 선택
        if result.fitness > best_fitness:
            best_fitness = result.fitness
            best_ref_name = ref_name
            best_result = result
            best_rmse = result.inlier_rmse

    t_match_elapsed = time.time() - t_match_start

    # 판정
    n_corr = len(best_result.correspondence_set) if best_result else 0
    if best_fitness < FITNESS_THRESHOLD:
        decision = "REJECT"
        reason = f"Fitness {best_fitness:.3f} < {FITNESS_THRESHOLD}"
    elif best_rmse > RMSE_THRESHOLD:
        decision = "REJECT"
        reason = f"RMSE {best_rmse*1000:.2f}mm > {RMSE_THRESHOLD*1000:.0f}mm"
    elif n_corr < MIN_CORRESPONDENCES:
        decision = "REJECT"
        reason = f"대응점 {n_corr} < {MIN_CORRESPONDENCES}"
    else:
        decision = "ACCEPT"
        reason = f"Best: {best_ref_name}"

    match_results.append({
        "cluster_id": cluster["id"],
        "matched_part": best_ref_name if decision == "ACCEPT" else "---",
        "fitness": best_fitness,
        "rmse_mm": best_rmse * 1000,
        "correspondences": n_corr,
        "transformation": best_result.transformation if best_result else np.eye(4),
        "decision": decision,
        "reason": reason,
        "elapsed": t_match_elapsed,
        "center": cluster["center"],
    })

    marker = "[OK]" if decision == "ACCEPT" else "[X] "
    print(f"    → {marker} {reason} (소요: {t_match_elapsed:.2f}s)")


# ============================================================
# Step 8: L5 6DoF 자세 + 그래스프 포인트 계산
# ============================================================
print_section("Step 8: L5 6DoF 자세 + 그래스프 포인트")

from scipy.spatial.transform import Rotation

print(f"  {'Cluster':>7} {'Part':>10} {'Position (mm)':>25} "
      f"{'Euler ZYX (deg)':>25} {'Grasp Z':>10}")
print(f"  {'-'*85}")

for mr in match_results:
    if mr["decision"] != "ACCEPT":
        print(f"  {mr['cluster_id']:>7} {'REJECTED':>10}")
        continue

    T = mr["transformation"]
    R_mat = T[:3, :3]
    t_vec = T[:3, 3]

    # 오일러 각도 (ZYX — 로봇 관절 표현)
    euler = Rotation.from_matrix(R_mat).as_euler("ZYX", degrees=True)

    # 그래스프 포인트: 클러스터 중심 + 접근 벡터 (-Z 방향, 위에서 내려잡기)
    grasp_point = mr["center"]
    # 접근 벡터: 카메라 방향에서 -Z (수직 하강)
    approach_vector = np.array([0.0, 0.0, -1.0])

    # 실제로는 부품 형상에 맞는 그래스프 계산이 필요하지만,
    # 여기서는 중심점 + 수직 접근으로 단순화
    mr["grasp_point"] = grasp_point
    mr["approach_vector"] = approach_vector
    mr["euler_zyx"] = euler

    pos_str = f"({grasp_point[0]*1000:+6.1f}, {grasp_point[1]*1000:+6.1f}, {grasp_point[2]*1000:+6.1f})"
    euler_str = f"({euler[0]:+6.1f}, {euler[1]:+6.1f}, {euler[2]:+6.1f})"

    print(f"  {mr['cluster_id']:>7} {mr['matched_part']:>10} {pos_str:>25} "
          f"{euler_str:>25} {grasp_point[2]*1000:>8.1f}mm")


# ============================================================
# Step 9: 결과 테이블
# ============================================================
print_section("Step 9: 전체 결과 테이블")

header = (f"  {'ID':>3} {'Part':>10} {'Fitness':>8} {'RMSE(mm)':>9} "
          f"{'Corr':>5} {'Time(s)':>7} {'Decision':>8}")
print(header)
print(f"  {'-'*len(header)}")

for mr in match_results:
    marker = "[OK]" if mr["decision"] == "ACCEPT" else "[X] "
    print(f"  {mr['cluster_id']:>3} {mr['matched_part']:>10} "
          f"{mr['fitness']:>8.4f} {mr['rmse_mm']:>9.2f} "
          f"{mr['correspondences']:>5} {mr['elapsed']:>7.2f} {marker:>8}")


# ============================================================
# Step 10: 성능 요약
# ============================================================
print_section("Step 10: 성능 요약")

t_pipeline_total = time.time() - t_pipeline_start

n_accepted = sum(1 for mr in match_results if mr["decision"] == "ACCEPT")
n_total = len(match_results)
recognition_rate = n_accepted / n_total * 100 if n_total > 0 else 0

# 매칭 단계만의 시간 (전처리 제외, 실제 빈피킹 루프 시간)
matching_times = [mr["elapsed"] for mr in match_results]
avg_match_time = np.mean(matching_times) if matching_times else 0
max_match_time = np.max(matching_times) if matching_times else 0

print(f"  전체 파이프라인 시간: {t_pipeline_total:.2f}초")
print(f"  매칭 단계 합계:      {sum(matching_times):.2f}초")
print(f"  부품당 평균 매칭:    {avg_match_time:.2f}초 (목표: 2.0초 이내)")
print(f"  부품당 최대 매칭:    {max_match_time:.2f}초")
print()
print(f"  감지된 클러스터:     {n_total}")
print(f"  수락(ACCEPT):        {n_accepted}")
print(f"  거부(REJECT):        {n_total - n_accepted}")
print(f"  인식률:              {recognition_rate:.1f}% (목표: 85% 이상)")
print()

# 목표 달성 여부 판단
time_ok = avg_match_time <= 2.0
rate_ok = recognition_rate >= 85.0

if time_ok:
    print(f"  [PASS] 부품당 시간 {avg_match_time:.2f}s <= 2.0s")
else:
    print(f"  [FAIL] 부품당 시간 {avg_match_time:.2f}s > 2.0s — RANSAC 반복 줄이기 또는 voxel 키우기 검토")

if rate_ok:
    print(f"  [PASS] 인식률 {recognition_rate:.1f}% >= 85%")
else:
    print(f"  [FAIL] 인식률 {recognition_rate:.1f}% < 85% — 임계값 조정 또는 플랜B (FGR/PPF) 검토")

print()
print("  실전 적용 시 개선 포인트:")
print("    1. 30종 STL → reference_cache 확장 (현재 3종 데모)")
print("    2. 실제 Basler Blaze-112 데이터로 노이즈 특성 보정")
print("    3. 부품별 그래스프 전략 (형상 맞춤 접근 벡터/각도)")
print("    4. Modbus TCP → HCR-10L 로봇 전송 연동")
print("    5. 다중 레퍼런스 병렬 매칭 (multiprocessing)")


# ============================================================
# 시각화 (옵션)
# ============================================================
if not args.no_vis:
    print_section("시각화: 클러스터 + 매칭 결과")

    # 클러스터 색상
    cmap = [
        [1, 0, 0], [0, 1, 0], [0, 0, 1],
        [1, 1, 0], [1, 0, 1], [0, 1, 1],
        [1, 0.5, 0], [0.5, 0, 1],
    ]

    vis_geometries = []

    # 바닥 (회색)
    ground_vis = scene_down.select_by_index(inliers)
    ground_vis.paint_uniform_color([0.7, 0.7, 0.7])
    vis_geometries.append(ground_vis)

    # 각 클러스터 + 매칭된 레퍼런스
    for ci, cluster in enumerate(clusters):
        color = cmap[ci % len(cmap)]
        cluster_vis = copy.deepcopy(cluster["pcd"])
        cluster_vis.paint_uniform_color(color)
        vis_geometries.append(cluster_vis)

        # 바운딩 박스
        bbox = cluster["pcd"].get_axis_aligned_bounding_box()
        bbox.color = color
        vis_geometries.append(bbox)

    # 좌표축
    coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.02)
    vis_geometries.append(coord)

    print("  클러스터별 색상 + 바운딩 박스. 창을 닫으면 종료.")
    o3d.visualization.draw_geometries(
        vis_geometries,
        window_name="Bin Picking Simulation Result",
        width=1024, height=768,
    )
else:
    print("\n  --no-vis 모드: 시각화 건너뜀")


print(f"\n{'='*60}")
print("  빈피킹 전체 파이프라인 시뮬레이션 완료!")
print(f"{'='*60}")
