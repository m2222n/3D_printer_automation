"""
STL → 레퍼런스 포인트 클라우드 + FPFH 사전 계산 실습
====================================================

빈피킹 W0-2 과제: "30종 STL 로드 → 레퍼런스 클라우드 생성 + FPFH 캐싱"

이 스크립트는 STL 파일이 없어도 Open3D 기본 메쉬로 실습 가능.
STL 파일이 생기면 경로만 바꾸면 됨.

실행: source .venv/binpick/bin/activate && python bin_picking/tutorials/02_stl_to_reference.py
"""

import os
import pickle
import time
import numpy as np
import open3d as o3d

# ============================================================
# 파라미터 (01_registration_pipeline.py와 동일)
# ============================================================
VOXEL_SIZE = 0.002  # 2mm
FPFH_RADIUS = VOXEL_SIZE * 5  # 10mm
FPFH_MAX_NN = 100
NORMAL_RADIUS = VOXEL_SIZE * 4  # 8mm
NORMAL_MAX_NN = 30
NUM_SAMPLE_POINTS = 10000  # STL에서 샘플링할 포인트 수

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ============================================================
# 1. STL 메쉬 로드 (또는 데모 메쉬 생성)
# ============================================================
print_section("Step 1: 메쉬 로드")

# TODO: 대표님에게 30종 STL 받으면 이 경로를 수정
STL_PATH = None  # 예: "bin_picking/stl/part_01.stl"

if STL_PATH and os.path.exists(STL_PATH):
    mesh = o3d.io.read_triangle_mesh(STL_PATH)
    mesh.compute_vertex_normals()
    part_name = os.path.splitext(os.path.basename(STL_PATH))[0]
    print(f"  STL 로드: {STL_PATH}")
else:
    # STL 없으면 Open3D 기본 메쉬로 실습
    # 점자 프린터 부품 크기 ~30mm 정도를 가정
    mesh = o3d.geometry.TriangleMesh.create_torus(
        torus_radius=0.015, tube_radius=0.005  # 15mm, 5mm
    )
    mesh.compute_vertex_normals()
    part_name = "demo_torus"
    print(f"  STL 파일 없음 → 데모 메쉬 생성 (토러스, 직경 ~30mm)")

print(f"  메쉬: vertices={len(mesh.vertices):,}, "
      f"triangles={len(mesh.triangles):,}")


# ============================================================
# 2. 메쉬 → 포인트 클라우드 샘플링
# ============================================================
print_section("Step 2: 균일 포인트 샘플링")

# Poisson Disk Sampling — 균일 분포 (빈피킹에 적합)
pcd = mesh.sample_points_poisson_disk(
    number_of_points=NUM_SAMPLE_POINTS,
    init_factor=5,
)
print(f"  샘플링: {NUM_SAMPLE_POINTS:,} points (Poisson Disk)")
print(f"  바운딩 박스: {pcd.get_axis_aligned_bounding_box()}")


# ============================================================
# 3. 전처리: 다운샘플링 + 법선 + FPFH
# ============================================================
print_section("Step 3: 전처리 (다운샘플링 + 법선 + FPFH)")

# 3-1. Voxel 다운샘플링
pcd_down = pcd.voxel_down_sample(VOXEL_SIZE)
print(f"  다운샘플링: {len(pcd.points):,} → {len(pcd_down.points):,} points")

# 3-2. 법선 추정
pcd_down.estimate_normals(
    o3d.geometry.KDTreeSearchParamHybrid(
        radius=NORMAL_RADIUS, max_nn=NORMAL_MAX_NN
    )
)

# 3-3. 법선 방향 일관성 (레퍼런스 모델은 원점 기준)
pcd_down.orient_normals_towards_camera_location(
    camera_location=np.array([0.0, 0.0, 0.0])
)
print(f"  법선 추정 + 카메라 방향 정렬 완료")

# 3-4. FPFH 특징 계산
t0 = time.time()
fpfh = o3d.pipelines.registration.compute_fpfh_feature(
    pcd_down,
    o3d.geometry.KDTreeSearchParamHybrid(
        radius=FPFH_RADIUS, max_nn=FPFH_MAX_NN
    ),
)
elapsed = time.time() - t0
print(f"  FPFH 계산: {fpfh.dimension()}D × {fpfh.num()} points ({elapsed:.3f}초)")


# ============================================================
# 4. pickle 캐싱 (런타임에 FPFH 재계산 방지)
# ============================================================
print_section("Step 4: 레퍼런스 데이터 pickle 캐싱")

cache_data = {
    "part_name": part_name,
    "points": np.asarray(pcd_down.points),
    "normals": np.asarray(pcd_down.normals),
    "fpfh": np.asarray(fpfh.data),  # (33, N)
    "voxel_size": VOXEL_SIZE,
    "fpfh_radius": FPFH_RADIUS,
    "normal_radius": NORMAL_RADIUS,
}

cache_path = os.path.join(CACHE_DIR, f"{part_name}.pkl")
with open(cache_path, "wb") as f:
    pickle.dump(cache_data, f)

file_size = os.path.getsize(cache_path) / 1024
print(f"  저장: {cache_path}")
print(f"  크기: {file_size:.1f} KB")
print(f"  포인트: {len(cache_data['points']):,}")


# ============================================================
# 5. 캐시 로드 테스트
# ============================================================
print_section("Step 5: 캐시 로드 + 복원 테스트")

t0 = time.time()
with open(cache_path, "rb") as f:
    loaded = pickle.load(f)

# numpy → Open3D 객체 복원
pcd_restored = o3d.geometry.PointCloud()
pcd_restored.points = o3d.utility.Vector3dVector(loaded["points"])
pcd_restored.normals = o3d.utility.Vector3dVector(loaded["normals"])

fpfh_restored = o3d.pipelines.registration.Feature()
fpfh_restored.data = loaded["fpfh"]

elapsed_load = time.time() - t0
print(f"  로드 시간: {elapsed_load*1000:.1f}ms (FPFH 재계산 불필요!)")
print(f"  복원 확인: {len(pcd_restored.points):,} points, "
      f"FPFH {fpfh_restored.dimension()}D × {fpfh_restored.num()}")


# ============================================================
# 6. 시각화 (메쉬 + 포인트 클라우드 + 법선)
# ============================================================
print_section("Step 6: 시각화")

# 법선 시각화 — 법선 방향이 일관적인지 확인 (⚠️ 빈피킹 핵심 검증!)
print("  [1/2] 포인트 클라우드 + 법선 (닫으면 다음)")
print("  → 법선(빨간 선)이 외부를 향하는지 확인!")
o3d.visualization.draw_geometries(
    [pcd_down],
    window_name=f"{part_name} — 법선 검증",
    point_show_normal=True,
    width=1024,
    height=768,
)

# 메쉬 + 포인트 비교
mesh_vis = copy.deepcopy(mesh) if 'copy' in dir() else mesh
pcd_vis = copy.deepcopy(pcd_down)
pcd_vis.paint_uniform_color([1, 0, 0])

import copy
mesh_wire = o3d.geometry.LineSet.create_from_triangle_mesh(mesh)
mesh_wire.paint_uniform_color([0.7, 0.7, 0.7])

print("  [2/2] 메쉬(회색 와이어) + 포인트(빨강)")
o3d.visualization.draw_geometries(
    [mesh_wire, pcd_vis],
    window_name=f"{part_name} — 메쉬 vs 포인트",
    width=1024,
    height=768,
)


# ============================================================
# 7. 30종 일괄 처리 템플릿
# ============================================================
print_section("Step 7: 30종 일괄 처리 (템플릿)")

print("""
  STL 파일 30종을 받으면 아래처럼 일괄 처리:

  import glob

  stl_files = glob.glob("bin_picking/stl/*.stl")
  for stl_path in stl_files:
      mesh = o3d.io.read_triangle_mesh(stl_path)
      mesh.compute_vertex_normals()
      pcd = mesh.sample_points_poisson_disk(10000, init_factor=5)
      pcd_down = pcd.voxel_down_sample(0.002)
      pcd_down.estimate_normals(...)
      pcd_down.orient_normals_towards_camera_location(...)
      fpfh = compute_fpfh_feature(pcd_down, ...)

      # pickle 저장
      cache = {"points": ..., "normals": ..., "fpfh": ...}
      pickle.dump(cache, open(f"cache/{part_name}.pkl", "wb"))

  → 30종 × ~10KB = ~300KB 캐시, 로드 시간 <10ms
""")

print("\n✅ STL → 레퍼런스 + FPFH 캐싱 튜토리얼 완료!")
