"""
레진별 파이프라인 프리셋 (SSOT — Single Source of Truth)
=========================================================

L2 전처리 (CloudFilter) + L4 매칭 (PoseEstimator) 파라미터를 레진 타입 하나로 일관되게
결정하기 위한 중앙 정의.

근거:
  - 논문 3편 리뷰 (FPFH, ICP, Open3D, 2026-03-20)
  - tutorials/09_noise_robustness.py (기본 노이즈 강건성)
  - tutorials/11_noise_robustness_advanced.py (Clear 레진 심화) — 섹션 5 결정 매트릭스

레진 특성 요약
-------------
- Grey V5 / White V5 : 불투명, 확산 반사 → ToF 노이즈 ~0.3mm (정상). 기본 설정 OK
- Clear V5           : 반투명 → ToF 반사 실패 40%+, 산란 노이즈 2mm+. 복원 전략 필요
- Flexible 80A       : 연질, 변형 가능 → CAD 모델과 불일치 가능. ICP 거리 완화 필요

사용법
------
>>> from bin_picking.config.resin_presets import get_preset
>>> preset = get_preset("clear")
>>> cf = preset.make_cloud_filter(roi_min=..., roi_max=...)
>>> est = preset.make_pose_estimator()

또는 파이프라인에서 직접:

>>> from bin_picking.src.main_pipeline import BinPickingPipeline
>>> pipeline = BinPickingPipeline.from_resin("clear")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    import numpy as np


# ============================================================
# 프리셋 데이터클래스
# ============================================================
@dataclass(frozen=True)
class ResinPreset:
    """레진별 전체 파이프라인 파라미터.

    L2 (CloudFilter) 와 L4 (PoseEstimator) 양쪽에서 사용하는 파라미터를
    하나의 객체에 묶어 일관성을 보장한다.

    voxel_size는 L2/L4 전체에 파생되는 핵심 스케일이므로 단일 값을 공유한다.
    """

    # ---- 메타 ----
    name: str
    description: str

    # ---- 공통 스케일 ----
    voxel_size: float                    # 미터. L2/L4 공유

    # ---- L2 전처리 (CloudFilter) ----
    sor_nb_neighbors: int                # SOR 이웃 수
    sor_std_ratio: float                 # SOR 표준편차 비율 (작을수록 엄격)
    normal_radius: float                 # 법선 검색 반경 (보통 voxel_size * 3)
    normal_max_nn: int                   # 법선 최대 이웃
    plane_distance: float                # 바닥면 RANSAC 거리 임계값

    # ---- L4 매칭 (PoseEstimator) ----
    fpfh_radius_multiplier: float        # FPFH 반경 = voxel_size * multiplier (기본 5배)
    icp_distance_multiplier: float       # ICP 거리 = voxel_size * multiplier (기본 1.0배)
    icp_kernel: str                      # "tukey", "huber", "none"
    icp_kernel_param: float              # Tukey/Huber threshold (미터)

    # ---- 판정 임계값 ----
    fitness_threshold: float             # ACCEPT 기준
    rmse_threshold: float                # REJECT 기준 (미터)

    # ---- Clear 전용 복원 전략 ----
    use_multiscale: bool = False         # coarse→fine multiscale 정합 사용 여부
    multiscale_coarse_voxel: float = 0.004   # coarse 단계 voxel

    # ---- 비고 ----
    notes: str = ""

    # ---- 파생 속성 ----
    @property
    def fpfh_radius(self) -> float:
        return self.voxel_size * self.fpfh_radius_multiplier

    @property
    def icp_distance(self) -> float:
        return self.voxel_size * self.icp_distance_multiplier

    # ---- 인스턴스 생성 헬퍼 ----
    def cloud_filter_kwargs(
        self,
        roi_min: "Optional[np.ndarray]" = None,
        roi_max: "Optional[np.ndarray]" = None,
    ) -> dict:
        """CloudFilter 생성자에 전달할 kwargs 딕셔너리."""
        kwargs = {
            "voxel_size": self.voxel_size,
            "sor_nb_neighbors": self.sor_nb_neighbors,
            "sor_std_ratio": self.sor_std_ratio,
            "normal_radius": self.normal_radius,
            "normal_max_nn": self.normal_max_nn,
            "plane_distance": self.plane_distance,
        }
        if roi_min is not None:
            kwargs["roi_min"] = roi_min
        if roi_max is not None:
            kwargs["roi_max"] = roi_max
        return kwargs

    def pose_estimator_kwargs(self) -> dict:
        """PoseEstimator 생성자에 전달할 kwargs 딕셔너리."""
        return {
            "voxel_size": self.voxel_size,
        }

    def summary(self) -> str:
        return (
            f"[{self.name}] {self.description}\n"
            f"  voxel={self.voxel_size*1000:.1f}mm, FPFH반경={self.fpfh_radius*1000:.1f}mm, "
            f"ICP거리={self.icp_distance*1000:.1f}mm\n"
            f"  kernel={self.icp_kernel}({self.icp_kernel_param*1000:.1f}mm), "
            f"SOR=(nb={self.sor_nb_neighbors}, std={self.sor_std_ratio})\n"
            f"  fitness>={self.fitness_threshold}, RMSE<={self.rmse_threshold*1000:.1f}mm"
            f"{', multiscale ON' if self.use_multiscale else ''}"
        )


# ============================================================
# 프리셋 정의 (tutorials/11 섹션 5 결정 매트릭스)
# ============================================================

# 표준 — Grey/White 불투명 레진
PRESET_GREY = ResinPreset(
    name="grey",
    description="Grey V5 — 불투명 확산 반사 (기본/표준)",
    voxel_size=0.002,
    sor_nb_neighbors=20,
    sor_std_ratio=2.0,
    normal_radius=0.006,
    normal_max_nn=30,
    plane_distance=0.005,
    fpfh_radius_multiplier=5.0,          # 10mm
    icp_distance_multiplier=1.0,         # 2mm
    icp_kernel="tukey",
    icp_kernel_param=0.001,              # Tukey 1mm
    fitness_threshold=0.3,
    rmse_threshold=0.003,                # 3mm
    notes="표준 파이프라인. ToF 노이즈 ~0.3mm 가정. fitness > 0.7 기대",
)

PRESET_WHITE = ResinPreset(
    name="white",
    description="White V5 — 불투명 (Grey와 동일 파라미터)",
    voxel_size=0.002,
    sor_nb_neighbors=20,
    sor_std_ratio=2.0,
    normal_radius=0.006,
    normal_max_nn=30,
    plane_distance=0.005,
    fpfh_radius_multiplier=5.0,
    icp_distance_multiplier=1.0,
    icp_kernel="tukey",
    icp_kernel_param=0.001,
    fitness_threshold=0.3,
    rmse_threshold=0.003,
    notes="Grey와 동일. 불투명 레진 공통 설정",
)

# 가장 까다로운 Clear 레진 — tutorials/11 섹션 4~5 근거
PRESET_CLEAR = ResinPreset(
    name="clear",
    description="Clear V5 — 반투명, ToF 반사 실패 40%+, 산란 노이즈 2mm+",
    voxel_size=0.003,                    # 2mm → 3mm (노이즈 ↑)
    sor_nb_neighbors=30,                 # 20 → 30 (더 많이 보고 판단)
    sor_std_ratio=1.0,                   # 2.0 → 1.0 (튜토리얼 11: std=1.0 효과 검증)
    normal_radius=0.009,                 # voxel * 3
    normal_max_nn=30,
    plane_distance=0.005,
    fpfh_radius_multiplier=5.0,          # 15mm (voxel 커진 만큼 자동 증가)
    icp_distance_multiplier=1.5,         # 1.5배 → 4.5mm (노이즈 여유)
    icp_kernel="tukey",
    icp_kernel_param=0.0015,             # Tukey 1.5mm
    fitness_threshold=0.25,              # 0.3 → 0.25 (40% 누락으로 fitness 낮음)
    rmse_threshold=0.004,                # 3mm → 4mm (노이즈 큼)
    use_multiscale=True,                 # coarse(4mm) → fine(3mm)
    multiscale_coarse_voxel=0.004,
    notes=(
        "복원 전략: SOR(nb=30,std=1.0) + voxel 3mm + ICP 거리/RMSE 완화 + multiscale. "
        "대안: 시간 평균(N=5) / 형광 분말 / structured light 병용. "
        "근거: tutorials/11 섹션 4 최소 포인트 밀도 40% 기준."
    ),
)

# Flexible 80A — 변형 가능 연질 레진
PRESET_FLEXIBLE = ResinPreset(
    name="flexible",
    description="Flexible 80A — 연질, 변형 시 CAD 모델과 불일치 가능",
    voxel_size=0.002,
    sor_nb_neighbors=20,
    sor_std_ratio=2.0,
    normal_radius=0.006,
    normal_max_nn=30,
    plane_distance=0.005,
    fpfh_radius_multiplier=5.0,
    icp_distance_multiplier=1.5,         # 1.0 → 1.5 (변형 여유)
    icp_kernel="huber",                  # Tukey → Huber (부드러운 rejection)
    icp_kernel_param=0.0015,             # Huber 1.5mm
    fitness_threshold=0.3,
    rmse_threshold=0.003,
    notes="ToF 노이즈는 Grey와 유사. 변형 허용 위해 Huber kernel + ICP 1.5배 거리",
)


# ============================================================
# 프리셋 레지스트리
# ============================================================
_PRESETS: dict[str, ResinPreset] = {
    "grey": PRESET_GREY,
    "white": PRESET_WHITE,
    "clear": PRESET_CLEAR,
    "flexible": PRESET_FLEXIBLE,
}


def get_preset(name: str) -> ResinPreset:
    """레진 이름으로 프리셋 조회. 대소문자 무관.

    Raises:
        ValueError: 알 수 없는 레진 이름
    """
    key = name.lower().strip()
    if key not in _PRESETS:
        available = ", ".join(sorted(_PRESETS.keys()))
        raise ValueError(
            f"알 수 없는 레진: '{name}'. 사용 가능: {available}"
        )
    return _PRESETS[key]


def list_presets() -> list[str]:
    """등록된 레진 이름 목록."""
    return sorted(_PRESETS.keys())


def default_preset() -> ResinPreset:
    """기본 프리셋 (Grey)."""
    return PRESET_GREY


# ============================================================
# 단독 실행 — 프리셋 요약 출력
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("  레진별 파이프라인 프리셋")
    print("=" * 70)
    for name in list_presets():
        preset = get_preset(name)
        print()
        print(preset.summary())
        print(f"  notes: {preset.notes}")
