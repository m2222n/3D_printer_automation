"""
노이즈 강건성 심화 분석 — Clear 레진 대응 전략 및 파라미터 최적화
==================================================================

목적: 09_noise_robustness.py 확장판. ToF 카메라(Basler Blaze-112)의 노이즈 환경에서
      FPFH 반경, Robust Kernel, 복원 전략 등을 체계적으로 비교하고,
      특히 Clear V5(투명) 레진에 대한 실전 대응 방안을 도출한다.

섹션 구성:
  1. FPFH 반경 비교 — feature 풍부도에 따른 정합 품질 변화
  2. Robust Kernel 비교 — None / Huber / Tukey 커널 효과
  3. 2mm 노이즈 복원 전략 — voxel 증가, SOR, 시간 평균, 멀티스케일
  4. Clear 레진 시뮬레이션 — 투명 표면 특성 재현 및 대응
  5. 레진별 추천 파라미터 결정 매트릭스

실행: .venv/binpick/bin/python bin_picking/tutorials/11_noise_robustness_advanced.py --no-vis
"""

import argparse
import copy
import time
import numpy as np
import open3d as o3d
from scipy.spatial.transform import Rotation

parser = argparse.ArgumentParser()
parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기")
args = parser.parse_args()

np.random.seed(42)

# ============================================================
# 0. 공통 파라미터 및 유틸리티
# ============================================================
VOXEL_SIZE = 0.002          # 2mm
NORMAL_MAX_NN = 30
FPFH_MAX_NN = 100
RANSAC_MAX_ITERATION = 100000
RANSAC_CONFIDENCE = 0.999


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def make_torus_pcd(n_points=10000):
    """~30mm 토러스 메시에서 포인트 클라우드 생성"""
    mesh = o3d.geometry.TriangleMesh.create_torus(
        torus_radius=0.012, tube_radius=0.005,
        radial_resolution=40, tubular_resolution=30,
    )
    mesh.compute_vertex_normals()
    pcd = mesh.sample_points_uniformly(number_of_points=n_points)
    return pcd


def make_gt_transform():
    """Ground Truth 6DoF 변환"""
    R = Rotation.from_euler('ZYX', [35, -20, 15], degrees=True).as_matrix()
    t = np.array([0.015, -0.010, 0.008])
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def add_gaussian_noise(pcd, sigma_m):
    """가우시안 노이즈 추가 (미터 단위)"""
    pts = np.asarray(pcd.points).copy()
    noise = np.random.normal(0, sigma_m, pts.shape)
    noisy = o3d.geometry.PointCloud()
    noisy.points = o3d.utility.Vector3dVector(pts + noise)
    return noisy


def add_outliers(pcd, outlier_ratio):
    """랜덤 아웃라이어 추가"""
    pts = np.asarray(pcd.points)
    n_outliers = int(len(pts) * outlier_ratio)
    if n_outliers == 0:
        return copy.deepcopy(pcd)
    bbox = pcd.get_axis_aligned_bounding_box()
    lo = bbox.get_min_bound()
    hi = bbox.get_max_bound()
    margin = (hi - lo) * 0.5
    outlier_pts = np.random.uniform(lo - margin, hi + margin, (n_outliers, 3))
    result = o3d.geometry.PointCloud()
    result.points = o3d.utility.Vector3dVector(np.vstack([pts, outlier_pts]))
    return result


def remove_random_points(pcd, remove_ratio):
    """랜덤하게 포인트 제거 (투명 표면 시뮬레이션)"""
    pts = np.asarray(pcd.points)
    n_keep = int(len(pts) * (1 - remove_ratio))
    if n_keep < 10:
        n_keep = 10
    indices = np.random.choice(len(pts), n_keep, replace=False)
    return pcd.select_by_index(indices)


def preprocess(pcd, voxel_size, normal_radius=None, fpfh_radius=None):
    """다운샘플 + 법선 + FPFH"""
    if normal_radius is None:
        normal_radius = voxel_size * 4
    if fpfh_radius is None:
        fpfh_radius = voxel_size * 5
    down = pcd.voxel_down_sample(voxel_size)
    down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(radius=normal_radius, max_nn=NORMAL_MAX_NN)
    )
    # Orient normals consistently
    down.orient_normals_towards_camera_location(np.array([0., 0., 0.5]))
    fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        down,
        o3d.geometry.KDTreeSearchParamHybrid(radius=fpfh_radius, max_nn=FPFH_MAX_NN),
    )
    return down, fpfh


def run_ransac(src_down, ref_down, src_fpfh, ref_fpfh, distance_threshold):
    """RANSAC 초기정합"""
    if len(src_down.points) < 20 or len(ref_down.points) < 20:
        result = type('obj', (object,), {'transformation': np.eye(4), 'fitness': 0.0})()
        return result
    result = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
        src_down, ref_down, src_fpfh, ref_fpfh,
        mutual_filter=True,
        max_correspondence_distance=distance_threshold,
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(False),
        ransac_n=3,
        checkers=[
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(distance_threshold),
        ],
        criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(
            max_iteration=RANSAC_MAX_ITERATION, confidence=RANSAC_CONFIDENCE,
        ),
    )
    return result


def run_icp(src_down, ref_down, init_T, max_dist, estimation_method=None):
    """ICP 정밀정합"""
    if estimation_method is None:
        loss = o3d.pipelines.registration.TukeyLoss(k=max_dist)
        estimation_method = o3d.pipelines.registration.TransformationEstimationPointToPlane(loss)
    result = o3d.pipelines.registration.registration_icp(
        src_down, ref_down,
        max_correspondence_distance=max_dist,
        init=init_T,
        estimation_method=estimation_method,
        criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
            relative_fitness=1e-6, relative_rmse=1e-6, max_iteration=50,
        ),
    )
    return result


def full_pipeline(scene_pcd, ref_down, ref_fpfh, voxel_size,
                  fpfh_radius=None, icp_method=None, icp_dist=None):
    """전체 파이프라인: 전처리 → RANSAC → ICP, (T, time, ransac_fit, icp_fit, icp_rmse, n_pts) 반환"""
    t0 = time.time()
    if fpfh_radius is None:
        fpfh_radius = voxel_size * 5

    src_down, src_fpfh = preprocess(scene_pcd, voxel_size, fpfh_radius=fpfh_radius)
    n_pts = len(src_down.points)
    if n_pts < 20:
        return np.eye(4), time.time() - t0, 0.0, 0.0, float('inf'), n_pts

    ransac_dist = voxel_size * 1.5
    res_ransac = run_ransac(src_down, ref_down, src_fpfh, ref_fpfh, ransac_dist)
    ransac_fit = res_ransac.fitness

    if icp_dist is None:
        icp_dist = voxel_size * 0.5
    # Use wider search for ICP max correspondence
    icp_max_dist = icp_dist * 3

    if icp_method is None:
        loss = o3d.pipelines.registration.TukeyLoss(k=icp_dist)
        icp_method = o3d.pipelines.registration.TransformationEstimationPointToPlane(loss)

    res_icp = run_icp(src_down, ref_down, res_ransac.transformation, icp_max_dist, icp_method)

    elapsed = time.time() - t0
    return res_icp.transformation, elapsed, ransac_fit, res_icp.fitness, res_icp.inlier_rmse, n_pts


# ============================================================
# 준비: 레퍼런스 모델 + GT 변환
# ============================================================
print_section("준비: 레퍼런스 모델 및 Ground Truth")

reference_pcd = make_torus_pcd(10000)
gt_transform = make_gt_transform()

bbox = reference_pcd.get_axis_aligned_bounding_box()
extent = bbox.get_extent()
print(f"  토러스 크기: {extent[0]*1000:.1f} x {extent[1]*1000:.1f} x {extent[2]*1000:.1f} mm")
print(f"  포인트 수: {len(reference_pcd.points):,}")

# 레퍼런스 전처리 (기본 파라미터)
ref_down_default, ref_fpfh_default = preprocess(reference_pcd, VOXEL_SIZE)
print(f"  다운샘플: {len(ref_down_default.points):,} pts, FPFH: {ref_fpfh_default.dimension()}D")


def make_noisy_scene(noise_mm, base_pcd=None, transform=None):
    """GT 변환 + 노이즈 적용된 씬 생성"""
    if base_pcd is None:
        base_pcd = reference_pcd
    if transform is None:
        transform = gt_transform
    scene = copy.deepcopy(base_pcd)
    scene.transform(transform)
    if noise_mm > 0:
        scene = add_gaussian_noise(scene, noise_mm / 1000.0)
    return scene


# ============================================================
# 섹션 1: FPFH 반경 비교
# ============================================================
print_section("섹션 1: FPFH 반경 비교 — feature 풍부도 vs 정합 품질")
print("  Open3D FPFH는 고정 11 bins (33D). 반경 변경으로 feature 범위 조절.")
print("  반경 = N x voxel_size (N = 3, 5, 7, 10)")

fpfh_multipliers = [3, 5, 7, 10]
noise_levels_sec1 = [0.3, 2.0]

for noise_mm in noise_levels_sec1:
    print(f"\n  --- 노이즈 {noise_mm}mm ---")
    print(f"  {'FPFH반경':>10} {'N_pts':>7} {'RANSAC_fit':>11} {'ICP_fit':>9} {'ICP_RMSE':>10} {'시간(s)':>8}")
    print(f"  {'-'*10} {'-'*7} {'-'*11} {'-'*9} {'-'*10} {'-'*8}")

    scene = make_noisy_scene(noise_mm)

    for mult in fpfh_multipliers:
        fpfh_r = VOXEL_SIZE * mult
        # Recompute reference with this radius
        ref_d, ref_f = preprocess(reference_pcd, VOXEL_SIZE, fpfh_radius=fpfh_r)

        T, elapsed, r_fit, i_fit, rmse, n_pts = full_pipeline(
            scene, ref_d, ref_f, VOXEL_SIZE, fpfh_radius=fpfh_r
        )

        rmse_str = f"{rmse*1000:.3f}mm" if rmse < float('inf') else "FAIL"
        print(f"  {mult}x({fpfh_r*1000:.0f}mm) {n_pts:>7} {r_fit:>11.4f} "
              f"{i_fit:>9.4f} {rmse_str:>10} {elapsed:>8.2f}")


# ============================================================
# 섹션 2: Robust Kernel 비교
# ============================================================
print_section("섹션 2: Robust Kernel 비교 — None / Huber / Tukey")

icp_base_dist = VOXEL_SIZE * 0.5  # 1mm

kernel_configs = [
    ("P2Plane (no kernel)",
     o3d.pipelines.registration.TransformationEstimationPointToPlane()),
    ("P2Plane + Huber(1mm)",
     o3d.pipelines.registration.TransformationEstimationPointToPlane(
         o3d.pipelines.registration.HuberLoss(k=0.001))),
    ("P2Plane + Tukey(1mm)",
     o3d.pipelines.registration.TransformationEstimationPointToPlane(
         o3d.pipelines.registration.TukeyLoss(k=0.001))),
]

noise_levels_sec2 = [0.3, 1.0, 2.0]

for noise_mm in noise_levels_sec2:
    print(f"\n  --- 노이즈 {noise_mm}mm ---")
    print(f"  {'Kernel':>25} {'ICP_fit':>9} {'ICP_RMSE':>10} {'시간(s)':>8}")
    print(f"  {'-'*25} {'-'*9} {'-'*10} {'-'*8}")

    scene = make_noisy_scene(noise_mm)

    for name, method in kernel_configs:
        T, elapsed, r_fit, i_fit, rmse, n_pts = full_pipeline(
            scene, ref_down_default, ref_fpfh_default, VOXEL_SIZE,
            icp_method=method
        )
        rmse_str = f"{rmse*1000:.3f}mm" if rmse < float('inf') else "FAIL"
        print(f"  {name:>25} {i_fit:>9.4f} {rmse_str:>10} {elapsed:>8.2f}")


# ============================================================
# 섹션 3: 2mm 노이즈 복원 전략
# ============================================================
print_section("섹션 3: 2mm 노이즈 복원 전략")

NOISE_2MM = 2.0

# 3-0. Baseline (기본 파라미터, 2mm 노이즈)
print("\n  [Baseline] 기본 파라미터, 2mm 노이즈")
scene_baseline = make_noisy_scene(NOISE_2MM)
T_bl, t_bl, _, fit_bl, rmse_bl, n_bl = full_pipeline(
    scene_baseline, ref_down_default, ref_fpfh_default, VOXEL_SIZE
)
print(f"  Fitness={fit_bl:.4f}, RMSE={rmse_bl*1000:.3f}mm, pts={n_bl}")
baseline_fitness = fit_bl

# 3-A. Strategy A: Voxel 크기 증가
print("\n  [Strategy A] Voxel 크기 증가 (노이즈 스무딩)")
voxel_sizes_A = [0.002, 0.003, 0.004]
results_A = []
for vs in voxel_sizes_A:
    scene = make_noisy_scene(NOISE_2MM)
    ref_d, ref_f = preprocess(reference_pcd, vs)
    T, elapsed, r_fit, i_fit, rmse, n_pts = full_pipeline(
        scene, ref_d, ref_f, vs
    )
    improvement = i_fit - baseline_fitness
    results_A.append((vs, i_fit, rmse, n_pts, improvement))
    print(f"  voxel={vs*1000:.0f}mm: fitness={i_fit:.4f}, RMSE={rmse*1000:.3f}mm, "
          f"pts={n_pts}, delta={improvement:+.4f}")

# 3-B. Strategy B: Statistical Outlier Removal
print("\n  [Strategy B] Statistical Outlier Removal 전처리")
sor_configs = [(20, 1.0), (20, 2.0), (50, 1.0), (50, 2.0)]
results_B = []
for nb, std_r in sor_configs:
    scene = make_noisy_scene(NOISE_2MM)
    cl, ind = scene.remove_statistical_outlier(nb_neighbors=nb, std_ratio=std_r)
    T, elapsed, r_fit, i_fit, rmse, n_pts = full_pipeline(
        cl, ref_down_default, ref_fpfh_default, VOXEL_SIZE
    )
    improvement = i_fit - baseline_fitness
    removed = len(scene.points) - len(cl.points)
    results_B.append((nb, std_r, i_fit, rmse, n_pts, removed, improvement))
    print(f"  nb={nb}, std={std_r}: fitness={i_fit:.4f}, RMSE={rmse*1000:.3f}mm, "
          f"removed={removed}, delta={improvement:+.4f}")

# 3-C. Strategy C: Temporal averaging (N depth maps 평균)
print("\n  [Strategy C] 시간 평균 시뮬레이션 (N개 뎁스맵 평균)")
avg_counts = [1, 3, 5, 10]
results_C = []

# Base scene without noise for consistent point positions
base_scene = copy.deepcopy(reference_pcd)
base_scene.transform(gt_transform)
base_pts = np.asarray(base_scene.points).copy()

for n_avg in avg_counts:
    # Average N noisy measurements
    accumulated = np.zeros_like(base_pts)
    for _ in range(n_avg):
        noise = np.random.normal(0, NOISE_2MM / 1000.0, base_pts.shape)
        accumulated += (base_pts + noise)
    averaged_pts = accumulated / n_avg

    avg_pcd = o3d.geometry.PointCloud()
    avg_pcd.points = o3d.utility.Vector3dVector(averaged_pts)

    T, elapsed, r_fit, i_fit, rmse, n_pts = full_pipeline(
        avg_pcd, ref_down_default, ref_fpfh_default, VOXEL_SIZE
    )
    # Effective noise: sigma / sqrt(N)
    eff_noise = NOISE_2MM / np.sqrt(n_avg)
    improvement = i_fit - baseline_fitness
    results_C.append((n_avg, eff_noise, i_fit, rmse, improvement))
    print(f"  N={n_avg:>2} (eff_noise={eff_noise:.2f}mm): fitness={i_fit:.4f}, "
          f"RMSE={rmse*1000:.3f}mm, delta={improvement:+.4f}")

# 3-D. Strategy D: Multi-scale registration (coarse→fine)
print("\n  [Strategy D] 멀티스케일 정합 (coarse -> fine)")
results_D = []

scene_d = make_noisy_scene(NOISE_2MM)
t0 = time.time()

# Coarse: large voxel
vs_coarse = 0.004
ref_d_c, ref_f_c = preprocess(reference_pcd, vs_coarse)
src_d_c, src_f_c = preprocess(scene_d, vs_coarse)
ransac_c = run_ransac(src_d_c, ref_d_c, src_f_c, ref_f_c, vs_coarse * 1.5)
icp_c = run_icp(src_d_c, ref_d_c, ransac_c.transformation, vs_coarse * 1.5)

# Fine: default voxel
src_d_f, src_f_f = preprocess(scene_d, VOXEL_SIZE)
icp_f = run_icp(src_d_f, ref_down_default, icp_c.transformation, VOXEL_SIZE * 1.5)

elapsed_d = time.time() - t0
fit_d = icp_f.fitness
rmse_d = icp_f.inlier_rmse
improvement_d = fit_d - baseline_fitness
results_D.append(("4mm->2mm", fit_d, rmse_d, elapsed_d, improvement_d))
print(f"  Coarse(4mm)->Fine(2mm): fitness={fit_d:.4f}, RMSE={rmse_d*1000:.3f}mm, "
      f"time={elapsed_d:.2f}s, delta={improvement_d:+.4f}")

# Strategy comparison table
print("\n  --- 전략 비교 요약 (2mm 노이즈) ---")
print(f"  {'전략':>20} {'Fitness':>9} {'개선폭':>9} {'비고':>20}")
print(f"  {'-'*20} {'-'*9} {'-'*9} {'-'*20}")
print(f"  {'Baseline':>20} {baseline_fitness:>9.4f} {'---':>9} {'기본 파라미터':>20}")

# Best from each strategy
if results_A:
    best_A = max(results_A, key=lambda x: x[1])
    print(f"  {'A: Voxel증가':>20} {best_A[1]:>9.4f} {best_A[4]:>+9.4f} "
          f"{'voxel='+str(int(best_A[0]*1000))+'mm':>20}")
if results_B:
    best_B = max(results_B, key=lambda x: x[2])
    print(f"  {'B: SOR':>20} {best_B[2]:>9.4f} {best_B[6]:>+9.4f} "
          f"{'nb='+str(best_B[0])+',std='+str(best_B[1]):>20}")
if results_C:
    best_C = max(results_C, key=lambda x: x[2])
    print(f"  {'C: 시간평균':>20} {best_C[2]:>9.4f} {best_C[4]:>+9.4f} "
          f"{'N='+str(best_C[0]):>20}")
if results_D:
    best_D = results_D[0]
    print(f"  {'D: 멀티스케일':>20} {best_D[1]:>9.4f} {best_D[4]:>+9.4f} "
          f"{best_D[0]:>20}")


# ============================================================
# 섹션 4: Clear 레진 시뮬레이션
# ============================================================
print_section("섹션 4: Clear V5 레진 시뮬레이션")
print("  Clear V5 특성:")
print("    - 40% 포인트 누락 (ToF 투명 표면 반사 실패)")
print("    - 나머지 포인트에 2mm 노이즈 (산란 반사)")
print("    - 10% 아웃라이어 (멀티패스 간섭)")


def make_clear_scene():
    """Clear V5 레진 특성 시뮬레이션"""
    scene = copy.deepcopy(reference_pcd)
    scene.transform(gt_transform)
    # 1. 40% 포인트 누락
    scene = remove_random_points(scene, 0.40)
    # 2. 2mm 가우시안 노이즈
    scene = add_gaussian_noise(scene, 0.002)
    # 3. 10% 아웃라이어
    scene = add_outliers(scene, 0.10)
    return scene


# 4-1. Basic pipeline on Clear
print("\n  [4-1] 기본 파이프라인 (Clear 레진)")
clear_scene = make_clear_scene()
print(f"  씬 포인트 수: {len(clear_scene.points):,}")

T_clear, t_clear, r_fit_c, i_fit_c, rmse_c, n_c = full_pipeline(
    clear_scene, ref_down_default, ref_fpfh_default, VOXEL_SIZE
)
print(f"  Fitness={i_fit_c:.4f}, RMSE={rmse_c*1000:.3f}mm, pts={n_c}")
clear_baseline = i_fit_c

# 4-2. Apply recovery strategies to Clear
print("\n  [4-2] 복원 전략 적용 (Clear 레진)")

strategies_clear = []

# Strategy A: Voxel 증가
for vs in [0.003, 0.004]:
    np.random.seed(42)
    cs = make_clear_scene()
    ref_d, ref_f = preprocess(reference_pcd, vs)
    T, el, rf, ifi, rmse, np_ = full_pipeline(cs, ref_d, ref_f, vs)
    strategies_clear.append((f"A:voxel={int(vs*1000)}mm", ifi, rmse))

# Strategy B: SOR
for nb, std_r in [(20, 1.0), (50, 2.0)]:
    np.random.seed(42)
    cs = make_clear_scene()
    cl, ind = cs.remove_statistical_outlier(nb_neighbors=nb, std_ratio=std_r)
    T, el, rf, ifi, rmse, np_ = full_pipeline(cl, ref_down_default, ref_fpfh_default, VOXEL_SIZE)
    strategies_clear.append((f"B:SOR(nb={nb},std={std_r})", ifi, rmse))

# Strategy C: Temporal averaging (N=5)
np.random.seed(42)
base_scene_c = copy.deepcopy(reference_pcd)
base_scene_c.transform(gt_transform)
base_scene_c = remove_random_points(base_scene_c, 0.40)
base_pts_c = np.asarray(base_scene_c.points).copy()

for n_avg in [5, 10]:
    accumulated_c = np.zeros_like(base_pts_c)
    for _ in range(n_avg):
        noise_c = np.random.normal(0, 0.002, base_pts_c.shape)
        accumulated_c += (base_pts_c + noise_c)
    avg_pts_c = accumulated_c / n_avg
    avg_pcd_c = o3d.geometry.PointCloud()
    avg_pcd_c.points = o3d.utility.Vector3dVector(avg_pts_c)
    # Add outliers to averaged result
    avg_pcd_c = add_outliers(avg_pcd_c, 0.10)
    T, el, rf, ifi, rmse, np_ = full_pipeline(avg_pcd_c, ref_down_default, ref_fpfh_default, VOXEL_SIZE)
    strategies_clear.append((f"C:avg(N={n_avg})", ifi, rmse))

# Strategy D: Multi-scale
np.random.seed(42)
cs_d = make_clear_scene()
t0 = time.time()
vs_coarse = 0.004
ref_d_c2, ref_f_c2 = preprocess(reference_pcd, vs_coarse)
src_d_c2, src_f_c2 = preprocess(cs_d, vs_coarse)
ransac_c2 = run_ransac(src_d_c2, ref_d_c2, src_f_c2, ref_f_c2, vs_coarse * 1.5)
icp_c2 = run_icp(src_d_c2, ref_d_c2, ransac_c2.transformation, vs_coarse * 1.5)
src_d_f2, _ = preprocess(cs_d, VOXEL_SIZE)
icp_f2 = run_icp(src_d_f2, ref_down_default, icp_c2.transformation, VOXEL_SIZE * 1.5)
strategies_clear.append(("D:multiscale(4->2mm)", icp_f2.fitness, icp_f2.inlier_rmse))

# Combined: SOR + Multi-scale
np.random.seed(42)
cs_combo = make_clear_scene()
cl_combo, _ = cs_combo.remove_statistical_outlier(nb_neighbors=20, std_ratio=1.0)
ref_d_c3, ref_f_c3 = preprocess(reference_pcd, vs_coarse)
src_d_c3, src_f_c3 = preprocess(cl_combo, vs_coarse)
ransac_c3 = run_ransac(src_d_c3, ref_d_c3, src_f_c3, ref_f_c3, vs_coarse * 1.5)
icp_c3 = run_icp(src_d_c3, ref_d_c3, ransac_c3.transformation, vs_coarse * 1.5)
src_d_f3, _ = preprocess(cl_combo, VOXEL_SIZE)
icp_f3 = run_icp(src_d_f3, ref_down_default, icp_c3.transformation, VOXEL_SIZE * 1.5)
strategies_clear.append(("B+D:SOR+multiscale", icp_f3.fitness, icp_f3.inlier_rmse))

print(f"\n  {'전략':>25} {'Fitness':>9} {'RMSE':>10}")
print(f"  {'-'*25} {'-'*9} {'-'*10}")
print(f"  {'Baseline (Clear)':>25} {clear_baseline:>9.4f} {rmse_c*1000:>9.3f}mm")
for name, fit, rmse_val in strategies_clear:
    rmse_s = f"{rmse_val*1000:.3f}mm" if rmse_val < float('inf') else "FAIL"
    print(f"  {name:>25} {fit:>9.4f} {rmse_s:>10}")

# Minimum viable point density
print("\n  [4-3] 최소 포인트 밀도 테스트 (Clear 레진)")
print("  질문: fitness > 0.3 달성을 위한 최소 잔존 포인트 비율은?")
removal_rates = [0.20, 0.40, 0.50, 0.60, 0.70, 0.80]
print(f"  {'제거율':>8} {'잔존':>6} {'Fitness':>9} {'판정':>6}")
print(f"  {'-'*8} {'-'*6} {'-'*9} {'-'*6}")
for rr in removal_rates:
    np.random.seed(42)
    s = copy.deepcopy(reference_pcd)
    s.transform(gt_transform)
    s = remove_random_points(s, rr)
    s = add_gaussian_noise(s, 0.002)
    T, el, rf, ifi, rmse_v, np_ = full_pipeline(
        s, ref_down_default, ref_fpfh_default, VOXEL_SIZE
    )
    verdict = "OK" if ifi > 0.3 else "FAIL"
    print(f"  {rr*100:>7.0f}% {(1-rr)*100:>5.0f}% {ifi:>9.4f} {verdict:>6}")


# ============================================================
# 섹션 5: 레진별 추천 파라미터 결정 매트릭스
# ============================================================
print_section("섹션 5: 레진별 추천 파라미터 결정 매트릭스")

print("""
  +-----------------+----------+----------+----------------+-----------+------------------+
  | 레진            | Voxel(mm)| FPFH반경 | ICP Kernel     | ICP거리   | 추가 전처리      |
  +-----------------+----------+----------+----------------+-----------+------------------+
  | Grey V5         |  2mm     | 5x(10mm) | Tukey(1mm)     | 1mm       | 없음 (표준)      |
  | White V5        |  2mm     | 5x(10mm) | Tukey(1mm)     | 1mm       | 없음 (표준)      |
  | Clear V5        |  3~4mm   | 5x       | Tukey(1.5mm)   | 1.5mm     | SOR + 멀티스케일 |
  | Flexible 80A    |  2mm     | 5x(10mm) | Huber(1.5mm)   | 1.5mm     | 없음 (ICP 여유)  |
  +-----------------+----------+----------+----------------+-----------+------------------+

  상세 설명:

  [Grey V5 / White V5] — 표준 설정 (불투명, 확산 반사)
    - ToF 카메라 노이즈: ~0.3mm (정상)
    - 기본 파이프라인으로 fitness > 0.7 기대
    - 추가 조치 불필요

  [Clear V5] — 투명 레진 (높은 노이즈, 포인트 누락)
    - ToF 반사 실패로 40%+ 포인트 누락 예상
    - 산란 반사로 2mm+ 노이즈
    - 권장: voxel 3~4mm + SOR(nb=20, std=1.0) + 멀티스케일 정합
    - 또는: 시간 평균 (N=5+) + 기본 파이프라인
    - fitness > 0.3 목표 (fitness < 0.3 시 인식 실패 판정)
    - 대안: 레진에 형광 분말 혼합, 외부 패턴 조명(structured light) 병용

  [Flexible 80A] — 연질 레진 (변형 가능)
    - ToF 노이즈는 Grey와 유사 (~0.3mm)
    - 변형 시 CAD 모델과 불일치 → ICP threshold 여유 필요
    - Huber kernel (Tukey보다 부드러운 rejection)
    - ICP 거리 1.5mm (기본 1mm 대비 50% 확대)

  인식 실패 판정 기준:
    - fitness < 0.3 → 실패, 다른 부품 시도
    - RMSE > 2mm → 재시도 (최대 3회)
    - 연속 3회 실패 → 수동 개입 요청
""")

print("=" * 70)
print("  노이즈 강건성 심화 분석 완료!")
print("=" * 70)
