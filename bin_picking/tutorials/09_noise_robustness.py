"""
노이즈 강건성 테스트 — ToF 카메라 노이즈 하에서 정합 정확도 평가
================================================================

목적: Basler Blaze-112 ToF 카메라의 노이즈 수준에서 FPFH+RANSAC+ICP
      파이프라인이 얼마나 안정적으로 자세를 추정하는지 정량 평가.

테스트 시나리오:
  1. 가우시안 노이즈 (0.1mm ~ 2.0mm) — 센서 측정 오차
  2. 부분 겹침 (30%, 50% 제거) — 빈 안에서의 가림(occlusion)
  3. 아웃라이어 (5%, 10% 랜덤 포인트) — 배경 클러터

Basler Blaze-112 스펙:
  - 깊이 정밀도: ~0.3mm @ 1m 거리
  - 해상도: 640×480 (VGA)
  - ToF (Time-of-Flight) 원리

파라미터:
  - VOXEL_SIZE = 0.002 (2mm) — 소형 합성 부품 스케일
  - 빈피킹 논문 리뷰 결정 파라미터 그대로 적용

실행: source .venv/binpick/bin/activate && python bin_picking/tutorials/09_noise_robustness.py
"""

import argparse
import copy
import time
import numpy as np
import open3d as o3d
from scipy.spatial.transform import Rotation

parser = argparse.ArgumentParser()
parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기 (터미널 전용)")
args = parser.parse_args()

# ============================================================
# 0. 빈피킹 파라미터 (실제 스케일, 2mm voxel)
# ============================================================
VOXEL_SIZE = 0.002          # 2mm — 소형 SLA 부품
FPFH_RADIUS = VOXEL_SIZE * 5       # 10mm
FPFH_MAX_NN = 100
NORMAL_RADIUS = VOXEL_SIZE * 4     # 8mm
NORMAL_MAX_NN = 30
RANSAC_DISTANCE = VOXEL_SIZE * 1.5  # 3mm
RANSAC_MAX_ITERATION = 100000
RANSAC_CONFIDENCE = 0.999
ICP_DISTANCE = VOXEL_SIZE * 0.5    # 1mm


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 1. 레퍼런스 모델 생성 (~30mm 크기 토러스)
# ============================================================
print_section("Step 1: 레퍼런스 모델 생성 (합성 데이터)")

# 토러스: 빈피킹 부품과 비슷한 크기 (~30mm 직경)
# torus_radius: 중심에서 튜브 중심까지 = 12mm
# tube_radius: 튜브 반지름 = 5mm
# → 전체 직경: 약 34mm, 두께: 약 10mm
mesh = o3d.geometry.TriangleMesh.create_torus(
    torus_radius=0.012,   # 12mm
    tube_radius=0.005,    # 5mm
    radial_resolution=40,
    tubular_resolution=30,
)
mesh.compute_vertex_normals()

# 메시 → 포인트 클라우드 (10,000점 균일 샘플링)
reference_pcd = mesh.sample_points_uniformly(number_of_points=10000)
print(f"레퍼런스 모델: 토러스 (직경 ~34mm)")
print(f"  포인트 수: {len(reference_pcd.points):,}")

# 바운딩 박스로 크기 확인
bbox = reference_pcd.get_axis_aligned_bounding_box()
extent = bbox.get_extent()
print(f"  크기 (XYZ): {extent[0]*1000:.1f} × {extent[1]*1000:.1f} × {extent[2]*1000:.1f} mm")

# 레퍼런스 전처리 (한 번만 수행, 캐시)
ref_down = reference_pcd.voxel_down_sample(VOXEL_SIZE)
ref_down.estimate_normals(
    o3d.geometry.KDTreeSearchParamHybrid(radius=NORMAL_RADIUS, max_nn=NORMAL_MAX_NN)
)
ref_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
    ref_down,
    o3d.geometry.KDTreeSearchParamHybrid(radius=FPFH_RADIUS, max_nn=FPFH_MAX_NN),
)
print(f"  다운샘플: {len(ref_down.points):,} points")
print(f"  FPFH 차원: {ref_fpfh.dimension()}D × {ref_fpfh.num():,}")


# ============================================================
# 2. Ground Truth 변환 정의
# ============================================================
print_section("Step 2: Ground Truth 변환 (알려진 자세)")

# 임의의 6DoF 변환 — 이것을 복원하는 것이 목표
gt_rotation = Rotation.from_euler('ZYX', [35, -20, 15], degrees=True).as_matrix()
gt_translation = np.array([0.015, -0.010, 0.008])  # 15mm, -10mm, 8mm

gt_transform = np.eye(4)
gt_transform[:3, :3] = gt_rotation
gt_transform[:3, 3] = gt_translation

gt_euler = Rotation.from_matrix(gt_rotation).as_euler('ZYX', degrees=True)
print(f"Ground Truth 이동: X={gt_translation[0]*1000:+.1f}, "
      f"Y={gt_translation[1]*1000:+.1f}, Z={gt_translation[2]*1000:+.1f} mm")
print(f"Ground Truth 회전: Rz={gt_euler[0]:+.1f}°, "
      f"Ry={gt_euler[1]:+.1f}°, Rx={gt_euler[2]:+.1f}°")


# ============================================================
# 3. 유틸리티 함수
# ============================================================

def add_gaussian_noise(pcd, sigma_m):
    """가우시안 노이즈 추가 (sigma: 미터 단위)"""
    pts = np.asarray(pcd.points)
    noise = np.random.normal(0, sigma_m, pts.shape)
    noisy = copy.deepcopy(pcd)
    noisy.points = o3d.utility.Vector3dVector(pts + noise)
    return noisy


def remove_partial(pcd, remove_ratio):
    """포인트의 일부를 제거 (가림 시뮬레이션)
    Z축 기준으로 상위 remove_ratio만큼 제거 (한쪽 방향 가림)"""
    pts = np.asarray(pcd.points)
    z_vals = pts[:, 2]
    threshold = np.percentile(z_vals, (1 - remove_ratio) * 100)
    mask = z_vals <= threshold
    partial = pcd.select_by_index(np.where(mask)[0])
    return partial


def add_outliers(pcd, outlier_ratio):
    """랜덤 아웃라이어 추가 (배경 클러터 시뮬레이션)"""
    pts = np.asarray(pcd.points)
    n_outliers = int(len(pts) * outlier_ratio)
    # 바운딩 박스 범위 내 랜덤 포인트
    bbox = pcd.get_axis_aligned_bounding_box()
    lo = bbox.get_min_bound()
    hi = bbox.get_max_bound()
    # 바운딩 박스보다 약간 넓은 범위에서 생성 (50% 확장)
    margin = (hi - lo) * 0.5
    outlier_pts = np.random.uniform(lo - margin, hi + margin, (n_outliers, 3))
    all_pts = np.vstack([pts, outlier_pts])
    result = o3d.geometry.PointCloud()
    result.points = o3d.utility.Vector3dVector(all_pts)
    return result


def compute_pose_error(estimated_T, gt_T):
    """추정 변환 vs GT 변환 사이의 이동/회전 오차 계산"""
    # 이동 오차 (mm)
    t_est = estimated_T[:3, 3]
    t_gt = gt_T[:3, 3]
    trans_error_mm = np.linalg.norm(t_est - t_gt) * 1000

    # 회전 오차 (도)
    R_est = estimated_T[:3, :3]
    R_gt = gt_T[:3, :3]
    R_diff = R_est @ R_gt.T
    # angle = arccos((trace(R_diff) - 1) / 2), 수치 안정성 위해 clip
    cos_angle = (np.trace(R_diff) - 1) / 2
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    rot_error_deg = np.degrees(np.arccos(cos_angle))

    return trans_error_mm, rot_error_deg


def run_registration(source_pcd, ref_down, ref_fpfh, voxel_size):
    """FPFH+RANSAC → ICP 파이프라인 실행, (변환행렬, 소요시간, fitness) 반환"""
    t_start = time.time()

    # 전처리
    src_down = source_pcd.voxel_down_sample(voxel_size)
    src_down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=voxel_size * 4, max_nn=NORMAL_MAX_NN
        )
    )
    src_fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        src_down,
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=voxel_size * 5, max_nn=FPFH_MAX_NN
        ),
    )

    # 포인트가 너무 적으면 실패 처리
    if len(src_down.points) < 20:
        return np.eye(4), time.time() - t_start, 0.0

    # RANSAC 초기정합
    result_ransac = o3d.pipelines.registration.registration_ransac_based_on_feature_matching(
        src_down, ref_down,
        src_fpfh, ref_fpfh,
        mutual_filter=True,
        max_correspondence_distance=RANSAC_DISTANCE,
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(False),
        ransac_n=3,
        checkers=[
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnEdgeLength(0.9),
            o3d.pipelines.registration.CorrespondenceCheckerBasedOnDistance(RANSAC_DISTANCE),
        ],
        criteria=o3d.pipelines.registration.RANSACConvergenceCriteria(
            max_iteration=RANSAC_MAX_ITERATION,
            confidence=RANSAC_CONFIDENCE,
        ),
    )

    # ICP 정밀정합 (Point-to-Plane + Robust)
    loss = o3d.pipelines.registration.TukeyLoss(k=ICP_DISTANCE)
    result_icp = o3d.pipelines.registration.registration_icp(
        src_down, ref_down,
        max_correspondence_distance=ICP_DISTANCE * 3,
        init=result_ransac.transformation,
        estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPlane(loss),
        criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
            relative_fitness=1e-6,
            relative_rmse=1e-6,
            max_iteration=50,
        ),
    )

    elapsed = time.time() - t_start
    return result_icp.transformation, elapsed, result_icp.fitness


# ============================================================
# 4. 테스트 1: 가우시안 노이즈 수준별 정합 정확도
# ============================================================
print_section("Step 3: 가우시안 노이즈 강건성 테스트")
print("  Basler Blaze-112 스펙: ~0.3mm @ 1m")

noise_levels_mm = [0.0, 0.1, 0.3, 0.5, 1.0, 2.0]
noise_results = []

for noise_mm in noise_levels_mm:
    sigma_m = noise_mm / 1000.0  # mm → m

    # 타겟 생성: GT 변환 적용 + 노이즈
    target = copy.deepcopy(reference_pcd)
    target.transform(gt_transform)
    if noise_mm > 0:
        target = add_gaussian_noise(target, sigma_m)

    # 정합 실행 (source=ref, target=noisy scene)
    # 빈피킹에서는 ref(CAD)를 scene에 맞추므로 source=ref, target=scene
    # 결과 변환 T: ref → scene, 즉 T ≈ gt_transform
    est_T, elapsed, fitness = run_registration(target, ref_down, ref_fpfh, VOXEL_SIZE)

    # 오차 계산: 추정된 역변환 vs GT
    # run_registration은 target을 ref에 맞추는 변환을 반환
    # 우리가 원하는 건 ref→target 변환이므로 역변환 취함
    # 단, registration_icp(source=target_noisy, target=ref)이므로
    # 반환된 T는 target_noisy→ref 변환. GT의 역(ref→scene)과 비교하려면
    # est_T_inv = ref→scene 추정값
    if fitness > 0:
        est_T_inv = np.linalg.inv(est_T)
        trans_err, rot_err = compute_pose_error(est_T_inv, gt_transform)
    else:
        trans_err, rot_err = float('inf'), float('inf')

    noise_results.append((noise_mm, trans_err, rot_err, fitness, elapsed))
    label = "← Blaze-112 스펙" if noise_mm == 0.3 else ""
    print(f"  σ={noise_mm:>4.1f}mm: 이동오차={trans_err:>6.2f}mm, "
          f"회전오차={rot_err:>6.2f}°, fitness={fitness:.4f}, "
          f"시간={elapsed:.2f}s {label}")


# ============================================================
# 5. 테스트 2: 부분 겹침 (Partial Overlap) — 가림 시뮬레이션
# ============================================================
print_section("Step 4: 부분 겹침 (가림/Occlusion) 테스트")
print("  빈 안에서 부품끼리 겹쳐 일부만 보이는 상황")

overlap_results = []
remove_ratios = [0.0, 0.3, 0.5]

for remove_ratio in remove_ratios:
    # GT 변환 적용 + 카메라 노이즈(0.3mm) + 부분 제거
    target = copy.deepcopy(reference_pcd)
    target.transform(gt_transform)
    target = add_gaussian_noise(target, 0.0003)  # 0.3mm — 센서 기본 노이즈
    if remove_ratio > 0:
        target = remove_partial(target, remove_ratio)

    est_T, elapsed, fitness = run_registration(target, ref_down, ref_fpfh, VOXEL_SIZE)

    if fitness > 0:
        est_T_inv = np.linalg.inv(est_T)
        trans_err, rot_err = compute_pose_error(est_T_inv, gt_transform)
    else:
        trans_err, rot_err = float('inf'), float('inf')

    remaining = int((1 - remove_ratio) * 100)
    overlap_results.append((remove_ratio, trans_err, rot_err, fitness, elapsed))
    print(f"  가림 {remove_ratio*100:.0f}% (보이는 부분 {remaining}%): "
          f"이동오차={trans_err:>6.2f}mm, 회전오차={rot_err:>6.2f}°, "
          f"fitness={fitness:.4f}")


# ============================================================
# 6. 테스트 3: 아웃라이어 (배경 클러터)
# ============================================================
print_section("Step 5: 아웃라이어 (배경 클러터) 테스트")
print("  DBSCAN 분할 후에도 남을 수 있는 배경 포인트")

outlier_results = []
outlier_ratios = [0.0, 0.05, 0.10]

for outlier_ratio in outlier_ratios:
    # GT 변환 적용 + 카메라 노이즈 + 아웃라이어
    target = copy.deepcopy(reference_pcd)
    target.transform(gt_transform)
    target = add_gaussian_noise(target, 0.0003)  # 0.3mm
    if outlier_ratio > 0:
        target = add_outliers(target, outlier_ratio)

    est_T, elapsed, fitness = run_registration(target, ref_down, ref_fpfh, VOXEL_SIZE)

    if fitness > 0:
        est_T_inv = np.linalg.inv(est_T)
        trans_err, rot_err = compute_pose_error(est_T_inv, gt_transform)
    else:
        trans_err, rot_err = float('inf'), float('inf')

    outlier_results.append((outlier_ratio, trans_err, rot_err, fitness, elapsed))
    print(f"  아웃라이어 {outlier_ratio*100:.0f}%: "
          f"이동오차={trans_err:>6.2f}mm, 회전오차={rot_err:>6.2f}°, "
          f"fitness={fitness:.4f}")


# ============================================================
# 7. 종합 결과 테이블
# ============================================================
print_section("Step 6: 종합 결과 테이블")

# 7-1. 노이즈 수준별
print("\n  [1] 가우시안 노이즈 수준별")
print(f"  {'노이즈(mm)':>10} {'이동오차(mm)':>12} {'회전오차(°)':>11} {'Fitness':>10} {'시간(s)':>8}")
print(f"  {'-'*10} {'-'*12} {'-'*11} {'-'*10} {'-'*8}")
for noise_mm, t_err, r_err, fit, elap in noise_results:
    marker = " ◀ spec" if noise_mm == 0.3 else ""
    t_str = f"{t_err:>12.2f}" if t_err != float('inf') else f"{'FAIL':>12}"
    r_str = f"{r_err:>11.2f}" if r_err != float('inf') else f"{'FAIL':>11}"
    print(f"  {noise_mm:>10.1f} {t_str} {r_str} {fit:>10.4f} {elap:>8.2f}{marker}")

# 7-2. 부분 겹침별
print(f"\n  [2] 부분 겹침 (가림) — 기본 노이즈 0.3mm 포함")
print(f"  {'가림(%)':>10} {'이동오차(mm)':>12} {'회전오차(°)':>11} {'Fitness':>10} {'시간(s)':>8}")
print(f"  {'-'*10} {'-'*12} {'-'*11} {'-'*10} {'-'*8}")
for rm_ratio, t_err, r_err, fit, elap in overlap_results:
    t_str = f"{t_err:>12.2f}" if t_err != float('inf') else f"{'FAIL':>12}"
    r_str = f"{r_err:>11.2f}" if r_err != float('inf') else f"{'FAIL':>11}"
    print(f"  {rm_ratio*100:>10.0f} {t_str} {r_str} {fit:>10.4f} {elap:>8.2f}")

# 7-3. 아웃라이어별
print(f"\n  [3] 아웃라이어 — 기본 노이즈 0.3mm 포함")
print(f"  {'아웃라이어(%)':>12} {'이동오차(mm)':>12} {'회전오차(°)':>11} {'Fitness':>10} {'시간(s)':>8}")
print(f"  {'-'*12} {'-'*12} {'-'*11} {'-'*10} {'-'*8}")
for ol_ratio, t_err, r_err, fit, elap in outlier_results:
    t_str = f"{t_err:>12.2f}" if t_err != float('inf') else f"{'FAIL':>12}"
    r_str = f"{r_err:>11.2f}" if r_err != float('inf') else f"{'FAIL':>11}"
    print(f"  {ol_ratio*100:>12.0f} {t_str} {r_str} {fit:>10.4f} {elap:>8.2f}")


# ============================================================
# 8. 안전 운용 파라미터 결정
# ============================================================
print_section("Step 7: 안전 운용 파라미터 결정")

# 노이즈 테스트에서 이동오차 < 1mm, 회전오차 < 2° 인 범위 찾기
TRANS_THRESHOLD = 1.0  # mm
ROT_THRESHOLD = 2.0    # degrees

print(f"\n  허용 기준: 이동오차 < {TRANS_THRESHOLD}mm, 회전오차 < {ROT_THRESHOLD}°")
print()

# 노이즈
safe_noise = 0.0
for noise_mm, t_err, r_err, fit, _ in noise_results:
    if t_err < TRANS_THRESHOLD and r_err < ROT_THRESHOLD:
        safe_noise = noise_mm
print(f"  안전 노이즈 수준: ≤ {safe_noise:.1f}mm")
print(f"    Basler Blaze-112 (~0.3mm): {'✅ 안전 범위 내' if safe_noise >= 0.3 else '⚠️ 주의 필요'}")

# 부분 겹침
safe_occlusion = 0.0
for rm_ratio, t_err, r_err, fit, _ in overlap_results:
    if t_err < TRANS_THRESHOLD and r_err < ROT_THRESHOLD:
        safe_occlusion = rm_ratio
print(f"\n  안전 가림 수준: ≤ {safe_occlusion*100:.0f}%")
print(f"    빈피킹 실전: 상단 부품은 30% 미만 가림 → "
      f"{'✅ 안전 범위' if safe_occlusion >= 0.3 else '⚠️ 상위 부품 우선 피킹 권장'}")

# 아웃라이어
safe_outlier = 0.0
for ol_ratio, t_err, r_err, fit, _ in outlier_results:
    if t_err < TRANS_THRESHOLD and r_err < ROT_THRESHOLD:
        safe_outlier = ol_ratio
print(f"\n  안전 아웃라이어 수준: ≤ {safe_outlier*100:.0f}%")
print(f"    DBSCAN 전처리로 대부분 제거 가능 → {'✅ 관리 가능' if safe_outlier >= 0.05 else '⚠️ DBSCAN 파라미터 조정 필요'}")


# ============================================================
# 9. 시각화 (선택)
# ============================================================
print_section("Step 8: 시각화")

if not args.no_vis:
    # 노이즈 0.3mm (Blaze-112 스펙) 예시 시각화
    target_vis = copy.deepcopy(reference_pcd)
    target_vis.transform(gt_transform)
    target_vis = add_gaussian_noise(target_vis, 0.0003)

    # 레퍼런스 (빨강), 타겟 (파랑), 정합 결과 (초록)
    ref_vis = copy.deepcopy(ref_down)
    ref_vis.paint_uniform_color([1, 0, 0])  # 빨강 = 레퍼런스 (CAD)

    target_vis_color = target_vis.voxel_down_sample(VOXEL_SIZE)
    target_vis_color.paint_uniform_color([0, 0, 1])  # 파랑 = 타겟 (씬)

    # 정합 결과 적용
    est_T, _, _ = run_registration(target_vis, ref_down, ref_fpfh, VOXEL_SIZE)
    aligned_vis = copy.deepcopy(target_vis_color)
    aligned_vis.transform(est_T)
    aligned_vis.paint_uniform_color([0, 1, 0])  # 초록 = 정합 결과

    coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.01)

    print("  빨강=레퍼런스(CAD), 파랑=타겟(노이즈 0.3mm), 초록=정합결과")
    o3d.visualization.draw_geometries(
        [ref_vis, target_vis_color, aligned_vis, coord],
        window_name="Noise Robustness (σ=0.3mm)",
        width=1024, height=768,
    )
else:
    print("  --no-vis 모드: 시각화 건너뜀")


# ============================================================
# 10. 실전 적용 권장사항
# ============================================================
print_section("Step 9: 실전 적용 권장사항")

print("""
  ■ Basler Blaze-112 환경에서의 권장 설정
    - voxel_size: 2mm (현재 테스트와 동일)
    - FPFH radius: 10mm (5×voxel)
    - RANSAC threshold: 3mm (1.5×voxel)
    - ICP: Point-to-Plane + TukeyLoss (아웃라이어 강건)
    - ICP threshold: 1mm (0.5×voxel)

  ■ 노이즈 대응
    - Blaze-112의 0.3mm 노이즈는 현 파이프라인으로 충분히 처리 가능
    - 1mm 이상 노이즈 시: Statistical Outlier Removal 전처리 추가
    - Clear(투명) 레진: ToF 반사 불안정 → 노이즈 1mm+ 예상 → 별도 대응 필요

  ■ 가림(Occlusion) 대응
    - 빈 상단 부품부터 피킹 (가림 최소화)
    - 50% 가림 시에도 동작하도록 RANSAC iteration 높게 유지
    - 피킹 후 씬 재촬영 → 다음 부품 인식

  ■ 배경 클러터 대응
    - DBSCAN 분할로 개별 부품 분리 (배경 대부분 제거)
    - ROI(Region of Interest) 필터: 빈 영역만 크롭
    - 평면 제거: RANSAC 평면 피팅으로 바닥/벽 제거

  ■ 인식 실패 판정 기준
    - fitness < 0.3 → 인식 실패로 판정, 다른 부품 시도
    - 이동오차 > 2mm 또는 회전오차 > 5° → 재시도 또는 스킵
    - 연속 3회 실패 → 알람 + 수동 개입 요청
""")

print("\n✅ 노이즈 강건성 테스트 완료!")
