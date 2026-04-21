"""
레진 프리셋 SSOT 회귀 테스트
============================

목적: bin_picking/config/resin_presets.py 의 값이 의도치 않게 바뀌지 않도록
      고정된 기대값을 검증한다. (합성 씬 E2E 결과와 직결되므로 중요)

실행:
    python bin_picking/tests/test_resin_presets.py

numpy/open3d 불필요 — SSOT 모듈은 순수 Python.
"""

from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트 추가
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from bin_picking.config.resin_presets import (
    get_preset,
    list_presets,
    default_preset,
)


# ============================================================
# 기대값 (튜토리얼 11 섹션 5 결정 매트릭스 기준)
# 이 값이 변경되면 E2E 합성 씬 결과 영향 → 의식적으로만 수정
# ============================================================
EXPECTED = {
    "grey": {
        "voxel_size": 0.002,
        "sor_nb_neighbors": 20,
        "sor_std_ratio": 2.0,
        "icp_kernel": "tukey",
        "icp_kernel_param": 0.001,
        "fitness_threshold": 0.3,
        "rmse_threshold": 0.003,
        "use_multiscale": False,
    },
    "white": {
        "voxel_size": 0.002,
        "sor_nb_neighbors": 20,
        "sor_std_ratio": 2.0,
        "icp_kernel": "tukey",
        "icp_kernel_param": 0.001,
        "fitness_threshold": 0.3,
        "rmse_threshold": 0.003,
        "use_multiscale": False,
    },
    "clear": {
        "voxel_size": 0.003,
        "sor_nb_neighbors": 30,
        "sor_std_ratio": 1.0,
        "icp_kernel": "tukey",
        "icp_kernel_param": 0.0015,
        "fitness_threshold": 0.25,
        "rmse_threshold": 0.004,
        "use_multiscale": True,
    },
    "flexible": {
        "voxel_size": 0.002,
        "sor_nb_neighbors": 20,
        "sor_std_ratio": 2.0,
        "icp_kernel": "huber",
        "icp_kernel_param": 0.0015,
        "fitness_threshold": 0.3,
        "rmse_threshold": 0.003,
        "use_multiscale": False,
    },
}

# 파생값 (voxel에서 자동 계산)
EXPECTED_DERIVED = {
    "grey":     {"fpfh_radius": 0.010, "icp_distance": 0.002},
    "white":    {"fpfh_radius": 0.010, "icp_distance": 0.002},
    "clear":    {"fpfh_radius": 0.015, "icp_distance": 0.0045},
    "flexible": {"fpfh_radius": 0.010, "icp_distance": 0.003},
}


# ============================================================
# 테스트 러너
# ============================================================
class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed: list[str] = []

    def check(self, name: str, cond: bool, msg: str = ""):
        if cond:
            self.passed += 1
        else:
            self.failed.append(f"{name}: {msg}")

    def summary(self):
        print()
        print("=" * 60)
        print(f"  테스트 결과: PASS {self.passed}, FAIL {len(self.failed)}")
        print("=" * 60)
        if self.failed:
            for msg in self.failed:
                print(f"  [FAIL] {msg}")
            sys.exit(1)
        else:
            print("  전체 통과")


def run_tests():
    r = TestResult()

    # 1. list_presets()가 4종 포함
    presets = list_presets()
    r.check("list_presets 길이", len(presets) == 4, f"{len(presets)} != 4")
    for name in ["grey", "white", "clear", "flexible"]:
        r.check(f"list_presets '{name}' 포함", name in presets, f"없음")

    # 2. default_preset은 grey
    dp = default_preset()
    r.check("default_preset 이름", dp.name == "grey", f"got '{dp.name}'")

    # 3. 각 프리셋 기대값 검증
    for name, expected in EXPECTED.items():
        p = get_preset(name)
        for key, exp_val in expected.items():
            actual = getattr(p, key)
            if isinstance(exp_val, float):
                ok = abs(actual - exp_val) < 1e-9
            else:
                ok = actual == exp_val
            r.check(
                f"{name}.{key}",
                ok,
                f"expected {exp_val!r}, got {actual!r}",
            )

    # 4. 파생값 (voxel에서 자동 계산)
    for name, derived in EXPECTED_DERIVED.items():
        p = get_preset(name)
        for key, exp_val in derived.items():
            actual = getattr(p, key)
            ok = abs(actual - exp_val) < 1e-9
            r.check(
                f"{name}.{key}(derived)",
                ok,
                f"expected {exp_val}, got {actual}",
            )

    # 5. 대소문자 무관
    p1 = get_preset("GREY")
    p2 = get_preset("grey")
    r.check("대소문자 무관", p1.name == p2.name, f"{p1.name} != {p2.name}")

    # 6. 잘못된 이름은 ValueError
    try:
        get_preset("unknown")
        r.check("invalid guard", False, "예외 안 던짐")
    except ValueError:
        r.check("invalid guard", True)

    # 7. cloud_filter_kwargs 형태
    kwargs = get_preset("clear").cloud_filter_kwargs()
    required = {"voxel_size", "sor_nb_neighbors", "sor_std_ratio",
                "normal_radius", "normal_max_nn", "plane_distance"}
    r.check(
        "cloud_filter_kwargs 필수 키",
        required.issubset(kwargs.keys()),
        f"누락: {required - kwargs.keys()}",
    )

    # 8. pose_estimator_kwargs 형태
    kwargs = get_preset("clear").pose_estimator_kwargs()
    r.check(
        "pose_estimator_kwargs voxel_size",
        "voxel_size" in kwargs,
        "voxel_size 누락",
    )

    # 9. Clear 프리셋 멀티스케일 확인
    clear = get_preset("clear")
    r.check(
        "clear.use_multiscale",
        clear.use_multiscale is True,
        f"multiscale={clear.use_multiscale}",
    )
    r.check(
        "clear.multiscale_coarse_voxel",
        abs(clear.multiscale_coarse_voxel - 0.004) < 1e-9,
        f"coarse_voxel={clear.multiscale_coarse_voxel}",
    )

    # 10. summary() 문자열 생성 확인
    s = get_preset("grey").summary()
    r.check("summary() 생성", "grey" in s and "voxel" in s, f"got: {s[:50]}")

    r.summary()


if __name__ == "__main__":
    print("=" * 60)
    print("  레진 프리셋 SSOT 회귀 테스트")
    print("=" * 60)
    run_tests()
