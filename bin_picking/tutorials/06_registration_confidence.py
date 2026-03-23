"""
Registration 품질 평가 및 불량 매칭 거부 (L4 신뢰도 판단)
========================================================

빈피킹에서 FPFH+RANSAC+ICP 결과가 실제로 올바른 매칭인지 판단하는 방법.
잘못된 매칭을 걸러내야 로봇이 엉뚱한 부품을 잡는 사고를 방지할 수 있음.

평가 지표:
  1. Fitness: inlier 비율 (0~1, 높을수록 좋음)
  2. RMSE: inlier 거리 평균 (낮을수록 좋음)
  3. Information Matrix: 정합의 기하학적 제약 강도 (6×6, 대각 성분 클수록 안정)
  4. Correspondence Set: 대응점 수

테스트 케이스:
  - 정상 매칭: 같은 형상, 정확한 변환
  - 부분 겹침: 일부만 보이는 경우 (빈피킹에서 흔함)
  - 오매칭: 다른 형상 간 매칭 시도
  - 노이즈: ToF 카메라 센서 노이즈

실행: source .venv/binpick/bin/activate && python bin_picking/tutorials/06_registration_confidence.py
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
# 0. 빈피킹 파라미터 (실제 SLA 부품 스케일)
# ============================================================
VOXEL_SIZE = 0.002       # 2mm — SLA 부품용
FPFH_RADIUS = VOXEL_SIZE * 5       # 10mm
FPFH_MAX_NN = 100
NORMAL_RADIUS = VOXEL_SIZE * 4     # 8mm
NORMAL_MAX_NN = 30
RANSAC_DISTANCE = VOXEL_SIZE * 1.5  # 3mm
RANSAC_MAX_ITERATION = 100000
RANSAC_CONFIDENCE = 0.999
ICP_DISTANCE = VOXEL_SIZE * 0.5     # 1mm

# 빈피킹 판정 임계값 (이 튜토리얼의 핵심)
FITNESS_ACCEPT = 0.3      # 이 이상이면 매칭 수락
FITNESS_GOOD = 0.5        # 이 이상이면 "좋은" 매칭
RMSE_REJECT = 0.003       # 3mm 초과하면 거부 (SLA 공차 고려)
MIN_CORRESPONDENCES = 30  # 대응점 30개 미만이면 거부


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 1. 빈피킹 스케일 데모 메쉬 생성 (20~40mm 부품)
# ============================================================
print_section("Step 1: 빈피킹 스케일 데모 메쉬 생성")

# 토러스: 외경 ~30mm, 내경 ~10mm (점자 교구 링 부품 비슷)
ref_torus = o3d.geometry.TriangleMesh.create_torus(
    torus_radius=0.015,  # 15mm 주반경
    tube_radius=0.005,   # 5mm 관반경
)
ref_torus.compute_vertex_normals()

# 박스: 30×20×10mm (직육면체 부품)
ref_box = o3d.geometry.TriangleMesh.create_box(0.030, 0.020, 0.010)
ref_box.compute_vertex_normals()
# 중심을 원점으로 이동
ref_box.translate(-ref_box.get_center())

# 실린더: 직경 16mm, 높이 25mm
ref_cylinder = o3d.geometry.TriangleMesh.create_cylinder(
    radius=0.008, height=0.025
)
ref_cylinder.compute_vertex_normals()

print(f"  토러스: 외경 ~30mm")
print(f"  박스: 30×20×10mm")
print(f"  실린더: 지름 16mm × 높이 25mm")


# ============================================================
# 2. 전처리 유틸리티 함수
# ============================================================
def preprocess(pcd, voxel_size=VOXEL_SIZE):
    """전처리: 다운샘플링 → 법선 → FPFH"""
    pcd_down = pcd.voxel_down_sample(voxel_size)
    pcd_down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=NORMAL_RADIUS, max_nn=NORMAL_MAX_NN
        )
    )
    pcd_down.orient_normals_towards_camera_location(
        camera_location=np.array([0.0, 0.0, 0.5])
    )
    fpfh = o3d.pipelines.registration.compute_fpfh_feature(
        pcd_down,
        o3d.geometry.KDTreeSearchParamHybrid(
            radius=FPFH_RADIUS, max_nn=FPFH_MAX_NN
        ),
    )
    return pcd_down, fpfh


def run_registration(source_down, source_fpfh, target_down, target_fpfh):
    """FPFH+RANSAC → ICP Point-to-Plane 전체 파이프라인 실행"""
    # RANSAC 초기 정합
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

    # ICP 정밀 정합 (Point-to-Plane + TukeyLoss)
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
# 3. 평가 함수 (핵심!)
# ============================================================
print_section("Step 2: 평가 함수 정의")


def evaluate_registration(source_down, target_down, result, case_name=""):
    """
    정합 결과의 품질을 종합 평가하고 수락/거부를 판정.

    반환: dict {fitness, rmse, correspondences, info_trace, decision, reason}
    """
    fitness = result.fitness
    rmse = result.inlier_rmse
    n_corr = len(result.correspondence_set)

    # Information Matrix (6×6) — 정합의 기하학적 제약 강도
    # 대각 성분이 크면 해당 방향의 제약이 강함 (=안정적)
    # 작으면 해당 방향으로 미끄러질 수 있음 (=불안정)
    info_matrix = o3d.pipelines.registration.get_information_matrix_from_point_clouds(
        source_down, target_down,
        max_correspondence_distance=ICP_DISTANCE * 3,
        transformation=result.transformation,
    )
    # 대각 성분의 합 (trace) — 전체적인 제약 강도 지표
    info_trace = np.trace(info_matrix)
    # 최소 대각 성분 — 가장 약한 방향의 제약
    info_min_diag = np.min(np.diag(info_matrix))

    # 판정 로직 (빈피킹용)
    decision = "ACCEPT"
    reason = "정상 매칭"

    if fitness < FITNESS_ACCEPT:
        decision = "REJECT"
        reason = f"Fitness {fitness:.3f} < {FITNESS_ACCEPT} (겹침 부족)"
    elif rmse > RMSE_REJECT:
        decision = "REJECT"
        reason = f"RMSE {rmse*1000:.2f}mm > {RMSE_REJECT*1000:.1f}mm (정합 정밀도 부족)"
    elif n_corr < MIN_CORRESPONDENCES:
        decision = "REJECT"
        reason = f"대응점 {n_corr} < {MIN_CORRESPONDENCES} (데이터 부족)"
    elif info_min_diag < 1.0:
        decision = "WARN"
        reason = f"Info Matrix 최소 대각 {info_min_diag:.1f} < 1.0 (불안정 방향 있음)"
    elif fitness >= FITNESS_GOOD:
        reason = "높은 신뢰도 매칭"

    return {
        "case": case_name,
        "fitness": fitness,
        "rmse": rmse,
        "rmse_mm": rmse * 1000,
        "correspondences": n_corr,
        "info_trace": info_trace,
        "info_min_diag": info_min_diag,
        "info_matrix": info_matrix,
        "decision": decision,
        "reason": reason,
    }


print("  evaluate_registration() 정의 완료")
print(f"  판정 기준:")
print(f"    FITNESS_ACCEPT: {FITNESS_ACCEPT} (이상이면 수락)")
print(f"    FITNESS_GOOD:   {FITNESS_GOOD} (이상이면 '좋은' 매칭)")
print(f"    RMSE_REJECT:    {RMSE_REJECT*1000:.1f}mm (초과하면 거부)")
print(f"    MIN_CORR:       {MIN_CORRESPONDENCES} (미만이면 거부)")


# ============================================================
# 4. 테스트 케이스 생성 및 실행
# ============================================================
results = []

# --- Case 1: 정상 매칭 (같은 형상, 알려진 변환 적용) ---
print_section("Case 1: 정상 매칭 (같은 토러스, 알려진 변환)")

# Source: 레퍼런스 토러스
source_pcd = ref_torus.sample_points_uniformly(5000)

# Target: 같은 토러스에 알려진 변환 적용
target_mesh = copy.deepcopy(ref_torus)
# 30도 회전 + 10mm 이동 (실제 빈에서의 부품 자세)
R = target_mesh.get_rotation_matrix_from_xyz([0.3, 0.5, 0.2])
target_mesh.rotate(R, center=target_mesh.get_center())
target_mesh.translate([0.010, -0.005, 0.003])
target_pcd = target_mesh.sample_points_uniformly(5000)

print(f"  Source: {len(source_pcd.points)} points (레퍼런스)")
print(f"  Target: {len(target_pcd.points)} points (변환 적용)")

source_down, source_fpfh = preprocess(source_pcd)
target_down, target_fpfh = preprocess(target_pcd)
t0 = time.time()
result = run_registration(source_down, source_fpfh, target_down, target_fpfh)
elapsed = time.time() - t0
eval1 = evaluate_registration(source_down, target_down, result, "정상 매칭")
eval1["elapsed"] = elapsed
results.append(eval1)
print(f"  Fitness: {eval1['fitness']:.4f}, RMSE: {eval1['rmse_mm']:.2f}mm, "
      f"대응점: {eval1['correspondences']}, 소요: {elapsed:.2f}s")
print(f"  → {eval1['decision']}: {eval1['reason']}")


# --- Case 2: 부분 겹침 (위에서만 보이는 경우) ---
print_section("Case 2: 부분 겹침 (반쪽만 보이는 토러스)")

# Target: 토러스의 윗부분만 (z > 0인 점만 남김)
target_partial_mesh = copy.deepcopy(ref_torus)
R2 = target_partial_mesh.get_rotation_matrix_from_xyz([0.4, 0.1, 0.6])
target_partial_mesh.rotate(R2, center=target_partial_mesh.get_center())
target_partial_mesh.translate([0.008, 0.012, 0.002])
target_partial_pcd = target_partial_mesh.sample_points_uniformly(5000)

# z > 중앙값인 점만 남김 (카메라에서 보이는 부분만 시뮬레이션)
pts = np.asarray(target_partial_pcd.points)
center_z = np.median(pts[:, 2])
mask = pts[:, 2] > center_z
target_partial_pcd = target_partial_pcd.select_by_index(np.where(mask)[0])
print(f"  Source: {len(source_pcd.points)} points (전체 레퍼런스)")
print(f"  Target: {len(target_partial_pcd.points)} points (윗부분만)")

source_down2, source_fpfh2 = preprocess(source_pcd)
target_down2, target_fpfh2 = preprocess(target_partial_pcd)
t0 = time.time()
result2 = run_registration(source_down2, source_fpfh2, target_down2, target_fpfh2)
elapsed2 = time.time() - t0
eval2 = evaluate_registration(source_down2, target_down2, result2, "부분 겹침")
eval2["elapsed"] = elapsed2
results.append(eval2)
print(f"  Fitness: {eval2['fitness']:.4f}, RMSE: {eval2['rmse_mm']:.2f}mm, "
      f"대응점: {eval2['correspondences']}, 소요: {elapsed2:.2f}s")
print(f"  → {eval2['decision']}: {eval2['reason']}")


# --- Case 3: 오매칭 (토러스 vs 박스 — 다른 형상) ---
print_section("Case 3: 오매칭 (토러스 ↔ 박스, 다른 형상)")

target_box_pcd = ref_box.sample_points_uniformly(5000)
R3 = ref_box.get_rotation_matrix_from_xyz([0.7, 0.3, 0.9])
target_box_mesh = copy.deepcopy(ref_box)
target_box_mesh.rotate(R3, center=target_box_mesh.get_center())
target_box_pcd = target_box_mesh.sample_points_uniformly(5000)

print(f"  Source: 토러스 {len(source_pcd.points)} points")
print(f"  Target: 박스 {len(target_box_pcd.points)} points")

source_down3, source_fpfh3 = preprocess(source_pcd)
target_down3, target_fpfh3 = preprocess(target_box_pcd)
t0 = time.time()
result3 = run_registration(source_down3, source_fpfh3, target_down3, target_fpfh3)
elapsed3 = time.time() - t0
eval3 = evaluate_registration(source_down3, target_down3, result3, "오매칭 (토러스↔박스)")
eval3["elapsed"] = elapsed3
results.append(eval3)
print(f"  Fitness: {eval3['fitness']:.4f}, RMSE: {eval3['rmse_mm']:.2f}mm, "
      f"대응점: {eval3['correspondences']}, 소요: {elapsed3:.2f}s")
print(f"  → {eval3['decision']}: {eval3['reason']}")


# --- Case 4: 노이즈가 심한 데이터 (ToF 카메라 열화 시뮬레이션) ---
print_section("Case 4: 노이즈 데이터 (ToF 센서 노이즈 3배)")

target_noisy_mesh = copy.deepcopy(ref_torus)
R4 = target_noisy_mesh.get_rotation_matrix_from_xyz([0.2, 0.8, 0.4])
target_noisy_mesh.rotate(R4, center=target_noisy_mesh.get_center())
target_noisy_mesh.translate([0.005, -0.003, 0.007])
target_noisy_pcd = target_noisy_mesh.sample_points_uniformly(5000)

# 강한 노이즈 추가 (표준편차 1mm — Blaze-112 일반 노이즈의 ~3배)
noise = np.random.normal(0, 0.001, size=np.asarray(target_noisy_pcd.points).shape)
target_noisy_pcd.points = o3d.utility.Vector3dVector(
    np.asarray(target_noisy_pcd.points) + noise
)

print(f"  Source: 토러스 (깨끗한 CAD)")
print(f"  Target: 토러스 + 노이즈 1mm σ (센서 열화)")

source_down4, source_fpfh4 = preprocess(source_pcd)
target_down4, target_fpfh4 = preprocess(target_noisy_pcd)
t0 = time.time()
result4 = run_registration(source_down4, source_fpfh4, target_down4, target_fpfh4)
elapsed4 = time.time() - t0
eval4 = evaluate_registration(source_down4, target_down4, result4, "노이즈 데이터")
eval4["elapsed"] = elapsed4
results.append(eval4)
print(f"  Fitness: {eval4['fitness']:.4f}, RMSE: {eval4['rmse_mm']:.2f}mm, "
      f"대응점: {eval4['correspondences']}, 소요: {elapsed4:.2f}s")
print(f"  → {eval4['decision']}: {eval4['reason']}")


# ============================================================
# 5. Information Matrix 상세 분석
# ============================================================
print_section("Step 5: Information Matrix 상세 분석")

print("  Information Matrix는 6×6 행렬로 정합의 기하학적 제약을 나타냄:")
print("  - 대각 성분 [0:3]: 이동(tx, ty, tz) 방향의 제약 강도")
print("  - 대각 성분 [3:6]: 회전(rx, ry, rz) 방향의 제약 강도")
print("  - 값이 클수록 해당 방향의 정합이 안정적")
print("  - 값이 작으면 해당 방향으로 '미끄러질' 수 있음 (불안정)")
print()

# Case 1 (정상)의 info matrix 상세 출력
info = results[0]["info_matrix"]
print(f"  [Case 1: {results[0]['case']}] Information Matrix 대각 성분:")
diag = np.diag(info)
labels = ["tx", "ty", "tz", "rx", "ry", "rz"]
for i, (label, val) in enumerate(zip(labels, diag)):
    bar = "#" * min(int(val / 10), 50)
    print(f"    {label}: {val:>10.1f}  {bar}")
print(f"    Trace (합계): {np.trace(info):.1f}")
print()

# 모든 케이스 info matrix 비교
print(f"  {'케이스':<20} {'Trace':>10} {'Min Diag':>10}")
print(f"  {'-'*40}")
for r in results:
    print(f"  {r['case']:<20} {r['info_trace']:>10.1f} {r['info_min_diag']:>10.1f}")


# ============================================================
# 6. 종합 판정 테이블
# ============================================================
print_section("Step 6: 종합 판정 테이블")

header = f"  {'케이스':<22} {'Fitness':>8} {'RMSE(mm)':>9} {'대응점':>6} {'Info Tr':>8} {'시간(s)':>7} {'판정':>7}"
print(header)
print(f"  {'-'*len(header)}")

for r in results:
    # 판정에 따른 마커
    marker = {"ACCEPT": "[OK]", "REJECT": "[X] ", "WARN": "[!] "}[r["decision"]]
    print(f"  {r['case']:<22} {r['fitness']:>8.4f} {r['rmse_mm']:>9.2f} "
          f"{r['correspondences']:>6} {r['info_trace']:>8.1f} "
          f"{r['elapsed']:>7.2f} {marker:>7}")

print()
print(f"  판정 기준:")
print(f"    [OK]  ACCEPT  — Fitness >= {FITNESS_ACCEPT}, RMSE <= {RMSE_REJECT*1000:.0f}mm, 대응점 >= {MIN_CORRESPONDENCES}")
print(f"    [!]   WARN    — 수락하지만 Info Matrix 불안정 경고")
print(f"    [X]   REJECT  — 하나라도 기준 미달 → 로봇에 전달하지 않음")


# ============================================================
# 7. 빈피킹 실전 적용 가이드
# ============================================================
print_section("Step 7: 빈피킹 실전 적용 가이드")

print("""
  ■ 임계값 튜닝 가이드 (30종 SLA 부품):

    1. Fitness 임계값 (현재 0.3):
       - 단순한 형상 (박스, 실린더): 0.4~0.5로 올려도 됨
       - 복잡한 형상 (구멍/돌출부 많은 부품): 0.2까지 낮춰야 할 수도
       - 부분 겹침이 흔한 빈피킹에서는 0.3이 적절한 시작점

    2. RMSE 임계값 (현재 3mm):
       - SLA 공차 ±0.1mm이지만 ToF 노이즈 고려 → 3mm
       - Blaze-112 정확도: z 방향 ±4mm@1m → 가까이 설치 시 ±1mm
       - 실제 부품으로 테스트 후 조정 필요

    3. Information Matrix 활용:
       - Trace > 100: 안정적
       - Trace < 10: 불안정 (대칭 부품에서 흔함)
       - 대칭 부품(실린더, 구): 회전축 방향 info가 낮음 → 정상임

    4. 다중 레퍼런스 매칭에서:
       - 30종 모두 시도 후 fitness 최고인 것 선택
       - 최고 fitness가 임계값 미만이면 "미식별 부품"으로 처리
       - 상위 2개 fitness 차이가 0.05 미만이면 → 혼동 경고

  ■ 코드 패턴 (실제 빈피킹 루프):

    best_fitness = 0
    best_ref_name = None
    best_result = None

    for ref_name, (ref_down, ref_fpfh) in reference_cache.items():
        result = run_registration(ref_down, ref_fpfh, cluster_down, cluster_fpfh)
        ev = evaluate_registration(ref_down, cluster_down, result)

        if ev["decision"] != "REJECT" and ev["fitness"] > best_fitness:
            best_fitness = ev["fitness"]
            best_ref_name = ref_name
            best_result = result

    if best_ref_name is None:
        print("미식별 부품 — 로봇 스킵")
    else:
        grasp_pose = compute_grasp(best_result.transformation)
        send_to_robot(grasp_pose)  # Modbus TCP → HCR-10L
""")


# ============================================================
# 8. 시각화 (옵션)
# ============================================================
if not args.no_vis:
    print_section("Step 8: 시각화")

    # 4개 케이스 중 Case 1 (정상)과 Case 3 (오매칭) 비교
    for i, (eval_r, s_down, t_down, res) in enumerate([
        (eval1, source_down, target_down, result),
        (eval3, source_down3, target_down3, result3),
    ]):
        src_vis = copy.deepcopy(s_down)
        src_vis.paint_uniform_color([1, 0, 0])  # 빨강 = source
        src_vis.transform(res.transformation)

        tgt_vis = copy.deepcopy(t_down)
        tgt_vis.paint_uniform_color([0, 0, 1])  # 파랑 = target

        coord = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.01)
        title = f"{eval_r['case']} — {eval_r['decision']} (Fitness: {eval_r['fitness']:.3f})"
        print(f"  [{title}] 빨강=Source, 파랑=Target. 창을 닫으면 다음.")
        o3d.visualization.draw_geometries(
            [src_vis, tgt_vis, coord],
            window_name=title,
            width=1024, height=768,
        )
else:
    print("\n  --no-vis 모드: 시각화 건너뜀")


print(f"\n{'='*60}")
print("  Registration 신뢰도 평가 튜토리얼 완료!")
print(f"{'='*60}")
