"""
Colored ICP 튜토리얼 — 기하학 + 색상 정보를 동시 활용하는 정합
================================================================

알고리즘: Colored ICP (Park et al., 2017)
  - 기존 ICP: 기하학(점 좌표, 법선)만 사용
  - Colored ICP: 기하학 + 색상 그래디언트를 결합한 목적 함수
  - Joint optimization: geometry term + color term (λ_c 가중치)

빈피킹 관련성:
  - 카메라: Basler Blaze-112 ToF (depth) + ace2 5MP (color) → RGB-D
  - RGB-D가 있으므로 Colored ICP 적용 가능
  - 단, SLA 부품은 단색(Grey/Clear/White/Flexible) → 색상 정보 제한적
  - 주 활용처: 카메라 캘리브레이션, 씬 정합, 다색 부품 구분

데모 데이터: o3d.data.DemoColoredICPPointClouds()
  - 2개 RGB-D 포인트 클라우드 (색상 정보 포함)
  - 실내 스캔 규모 → voxel_size 0.05m (5cm)

비교: Point-to-Point ICP vs Point-to-Plane ICP vs Colored ICP

실행: source .venv/binpick/bin/activate && python bin_picking/tutorials/08_colored_icp.py
"""

import argparse
import copy
import time
import numpy as np
import open3d as o3d

parser = argparse.ArgumentParser()
parser.add_argument("--no-vis", action="store_true", help="시각화 건너뛰기 (터미널 전용)")
args = parser.parse_args()

# ============================================================
# 0. 파라미터 설정
# ============================================================
# 데모 데이터는 실내 스캔 규모 → voxel 5cm
# 실제 빈피킹에서는 VOXEL_SIZE = 0.002 (2mm)
VOXEL_SIZE = 0.05
ICP_DISTANCE = VOXEL_SIZE * 0.5       # 대응점 최대 거리
NORMAL_RADIUS = VOXEL_SIZE * 4.0      # 법선 추정 반경
NORMAL_MAX_NN = 30                     # 법선 추정 이웃 수


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 1. 데모 데이터 로드 — 색상이 포함된 포인트 클라우드
# ============================================================
print_section("Step 1: 색상 포인트 클라우드 로드")

demo_data = o3d.data.DemoColoredICPPointClouds()
# paths: [source.ply, target.ply]
source_raw = o3d.io.read_point_cloud(demo_data.paths[0])
target_raw = o3d.io.read_point_cloud(demo_data.paths[1])

print(f"Source: {len(source_raw.points):,} points, "
      f"색상 있음: {source_raw.has_colors()}")
print(f"Target: {len(target_raw.points):,} points, "
      f"색상 있음: {target_raw.has_colors()}")

# 색상 분포 확인
if source_raw.has_colors():
    colors = np.asarray(source_raw.colors)
    print(f"\n  Source 색상 범위:")
    print(f"    R: [{colors[:,0].min():.2f}, {colors[:,0].max():.2f}]")
    print(f"    G: [{colors[:,1].min():.2f}, {colors[:,1].max():.2f}]")
    print(f"    B: [{colors[:,2].min():.2f}, {colors[:,2].max():.2f}]")


# ============================================================
# 2. 전처리 — 다운샘플링 + 법선 추정
# ============================================================
print_section("Step 2: 전처리 (다운샘플링 + 법선)")


def preprocess(pcd, voxel_size):
    """다운샘플링 + 법선 추정 (색상 보존)"""
    pcd_down = pcd.voxel_down_sample(voxel_size)
    pcd_down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=NORMAL_RADIUS, max_nn=NORMAL_MAX_NN
        )
    )
    return pcd_down


source_down = preprocess(source_raw, VOXEL_SIZE)
target_down = preprocess(target_raw, VOXEL_SIZE)

print(f"Source (다운샘플): {len(source_down.points):,} points")
print(f"Target (다운샘플): {len(target_down.points):,} points")


# ============================================================
# 3. 초기 변환 — 단위 행렬 (데모 데이터는 이미 대략 정렬됨)
# ============================================================
# 실제 빈피킹에서는 FPFH+RANSAC 초기정합 결과를 init으로 넣음
init_transform = np.identity(4)


# ============================================================
# 4. 비교 실험 — 3가지 ICP 방법
# ============================================================
print_section("Step 3: 3가지 ICP 방법 비교")

results = {}  # {method_name: (result, elapsed)}

# --- 4-1. Point-to-Point ICP ---
print("\n  [1/3] Point-to-Point ICP...")
t0 = time.time()
result_p2point = o3d.pipelines.registration.registration_icp(
    source_down, target_down,
    max_correspondence_distance=ICP_DISTANCE * 3,
    init=init_transform,
    estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPoint(),
    criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
        relative_fitness=1e-6,
        relative_rmse=1e-6,
        max_iteration=50,
    ),
)
elapsed_p2point = time.time() - t0
results["Point-to-Point"] = (result_p2point, elapsed_p2point)
print(f"    Fitness: {result_p2point.fitness:.4f}, "
      f"RMSE: {result_p2point.inlier_rmse*1000:.2f}mm, "
      f"시간: {elapsed_p2point:.3f}s")

# --- 4-2. Point-to-Plane ICP ---
print("\n  [2/3] Point-to-Plane ICP...")
t0 = time.time()
result_p2plane = o3d.pipelines.registration.registration_icp(
    source_down, target_down,
    max_correspondence_distance=ICP_DISTANCE * 3,
    init=init_transform,
    estimation_method=o3d.pipelines.registration.TransformationEstimationPointToPlane(),
    criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
        relative_fitness=1e-6,
        relative_rmse=1e-6,
        max_iteration=50,
    ),
)
elapsed_p2plane = time.time() - t0
results["Point-to-Plane"] = (result_p2plane, elapsed_p2plane)
print(f"    Fitness: {result_p2plane.fitness:.4f}, "
      f"RMSE: {result_p2plane.inlier_rmse*1000:.2f}mm, "
      f"시간: {elapsed_p2plane:.3f}s")

# --- 4-3. Colored ICP (Park 2017) ---
# Colored ICP는 색상 그래디언트를 추가 제약 조건으로 사용
# lambda_geometric: 기하학 항 가중치 (기본값 → 자동 설정)
print("\n  [3/3] Colored ICP (Park 2017)...")
t0 = time.time()
result_colored = o3d.pipelines.registration.registration_colored_icp(
    source_down, target_down,
    max_correspondence_distance=ICP_DISTANCE * 3,
    init=init_transform,
    estimation_method=(
        o3d.pipelines.registration.TransformationEstimationForColoredICP()
    ),
    criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
        relative_fitness=1e-6,
        relative_rmse=1e-6,
        max_iteration=50,
    ),
)
elapsed_colored = time.time() - t0
results["Colored ICP"] = (result_colored, elapsed_colored)
print(f"    Fitness: {result_colored.fitness:.4f}, "
      f"RMSE: {result_colored.inlier_rmse*1000:.2f}mm, "
      f"시간: {elapsed_colored:.3f}s")


# ============================================================
# 5. 결과 비교 테이블
# ============================================================
print_section("Step 4: 결과 비교 테이블")

header = f"{'Method':>20} {'Fitness':>10} {'RMSE(mm)':>10} {'대응점':>10} {'시간(s)':>10}"
print(header)
print("-" * len(header))

for name, (res, elapsed) in results.items():
    print(f"{name:>20} "
          f"{res.fitness:>10.4f} "
          f"{res.inlier_rmse*1000:>10.2f} "
          f"{len(res.correspondence_set):>10,} "
          f"{elapsed:>10.3f}")


# ============================================================
# 6. Colored ICP 멀티스케일 (Multi-Scale) — 정밀도 향상
# ============================================================
print_section("Step 5: Colored ICP 멀티스케일 (거칠게 → 정밀하게)")

# 멀티스케일: 큰 voxel → 작은 voxel 순서로 점진 정합
# 넓은 범위에서 대략 맞추고 → 좁은 범위에서 정밀 조정
voxel_radii = [VOXEL_SIZE * 4, VOXEL_SIZE * 2, VOXEL_SIZE]
max_iters = [50, 30, 14]  # 스케일별 반복 횟수

print(f"  스케일 단계: {len(voxel_radii)}")
for i, (radius, iters) in enumerate(zip(voxel_radii, max_iters)):
    print(f"    Level {i}: voxel={radius*1000:.0f}mm, "
          f"max_iter={iters}")

t0 = time.time()
current_transform = init_transform.copy()

for scale_idx, (radius, max_iter) in enumerate(zip(voxel_radii, max_iters)):
    # 스케일별 다운샘플링
    src = source_raw.voxel_down_sample(radius)
    tgt = target_raw.voxel_down_sample(radius)

    # 법선 재추정 (스케일에 맞게)
    src.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(radius=radius * 4, max_nn=30)
    )
    tgt.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(radius=radius * 4, max_nn=30)
    )

    result_ms = o3d.pipelines.registration.registration_colored_icp(
        src, tgt,
        max_correspondence_distance=radius * 1.5,
        init=current_transform,
        estimation_method=(
            o3d.pipelines.registration.TransformationEstimationForColoredICP()
        ),
        criteria=o3d.pipelines.registration.ICPConvergenceCriteria(
            relative_fitness=1e-6,
            relative_rmse=1e-6,
            max_iteration=max_iter,
        ),
    )
    current_transform = result_ms.transformation
    print(f"  Level {scale_idx}: fitness={result_ms.fitness:.4f}, "
          f"RMSE={result_ms.inlier_rmse*1000:.2f}mm")

elapsed_ms = time.time() - t0
print(f"\n  멀티스케일 총 시간: {elapsed_ms:.3f}s")
print(f"  최종 fitness: {result_ms.fitness:.4f}")
print(f"  최종 RMSE: {result_ms.inlier_rmse*1000:.2f}mm")

# 싱글스케일 vs 멀티스케일 비교
print(f"\n  비교: 싱글스케일 vs 멀티스케일")
print(f"    {'':>15} {'싱글':>12} {'멀티':>12}")
print(f"    {'Fitness':>15} {result_colored.fitness:>12.4f} {result_ms.fitness:>12.4f}")
print(f"    {'RMSE(mm)':>15} {result_colored.inlier_rmse*1000:>12.2f} {result_ms.inlier_rmse*1000:>12.2f}")
print(f"    {'시간(s)':>15} {elapsed_colored:>12.3f} {elapsed_ms:>12.3f}")


# ============================================================
# 7. 시각화
# ============================================================
print_section("Step 6: 시각화")


def draw_colored_registration(source, target, transformation, title):
    """색상 유지한 채로 정합 결과 시각화"""
    source_vis = copy.deepcopy(source)
    source_vis.transform(transformation)

    # 좌표축 (데모 스케일에 맞춤)
    coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.1)

    print(f"  [{title}] 원본 색상 유지 — 겹치는 영역이 잘 맞을수록 정합 성공")
    print("  창을 닫으면 다음 단계로 진행합니다.")
    o3d.visualization.draw_geometries(
        [source_vis, target, coord],
        window_name=title,
        width=1024, height=768,
    )


if not args.no_vis:
    # 초기 상태
    draw_colored_registration(source_down, target_down,
                              init_transform, "Before (초기 상태)")
    # Point-to-Point 결과
    draw_colored_registration(source_down, target_down,
                              result_p2point.transformation,
                              "Point-to-Point ICP")
    # Point-to-Plane 결과
    draw_colored_registration(source_down, target_down,
                              result_p2plane.transformation,
                              "Point-to-Plane ICP")
    # Colored ICP 결과
    draw_colored_registration(source_down, target_down,
                              result_colored.transformation,
                              "Colored ICP (싱글스케일)")
    # 멀티스케일 결과
    draw_colored_registration(source_down, target_down,
                              current_transform,
                              "Colored ICP (멀티스케일)")
else:
    print("  --no-vis 모드: 시각화 건너뜀")


# ============================================================
# 8. 빈피킹 적용 시 고려사항
# ============================================================
print_section("Step 7: 빈피킹에서 Colored ICP 활용 분석")

print("""
  ■ Colored ICP의 장점
    - 기하학이 비슷한(대칭/단순) 부품에서 색상으로 모호성 해결
    - RGB-D 카메라(Basler ace2 + Blaze-112)의 색상 정보 활용 가능
    - 멀티스케일 적용 시 수렴 안정성 향상

  ■ SLA 부품에서의 한계 (이 프로젝트)
    - SLA 레진은 대부분 단색: Grey V5, Clear V5, White V5, Flexible 80A
    - 단색 부품 → 색상 그래디언트 거의 없음 → Colored ICP 이점 제한적
    - 투명(Clear) 레진은 ToF 카메라에서 깊이 노이즈 심함

  ■ Colored ICP가 유용한 경우
    1. 카메라 캘리브레이션: RGB ↔ Depth 정합 (색상 풍부한 캘리브 타겟 사용)
    2. 씬 정합 (Scene Registration): 여러 뷰 합성 시 배경 색상 활용
    3. 다색 부품: 도색/마킹된 부품, 서로 다른 레진 혼재 시
    4. 텍스처 있는 환경: 빈(bin) 자체에 패턴/마킹이 있을 때

  ■ 이 프로젝트 권장
    - 기본: Point-to-Plane ICP + Robust Kernel (단색 부품에 충분)
    - 선택: Colored ICP를 카메라 캘리브레이션 단계에서 활용
    - 멀티스케일: 정합 불안정 시 적용 (정밀도↑, 시간 약간↑)

  ■ 파라미터 참고 (실제 빈피킹 2mm voxel)
    - VOXEL_SIZE = 0.002 (2mm)
    - 멀티스케일: [8mm, 4mm, 2mm]
    - lambda_geometric: 기본값 사용 (자동 조절)
""")

print("\n✅ Colored ICP 튜토리얼 완료!")
