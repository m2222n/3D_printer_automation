"""
L5 그래스프 계획 — 부품별 피킹 자세 계산
==========================================

L4에서 인식된 부품의 월드 자세(T_part_world)에
사전 정의된 로컬 그래스프 자세(T_grasp_local)를 적용하여
로봇이 실행할 최종 피킹 자세(T_grasp_world)를 계산한다.

공식:
  T_grasp_world = T_part_world @ T_grasp_local

grasp_database.yaml에 부품별 그래스프 파라미터 정의:
  - approach_axis: 접근 방향 (부품 로컬)
  - grasp_center_mm: 잡는 위치 (부품 중심 기준 오프셋)
  - grasp_depth_mm: 접근 축 방향 진입 깊이
  - gripper_width_mm: 그리퍼 벌림
  - gripper_force_N: 파지력

실행 환경: source .venv/binpick/bin/activate
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import yaml


# ============================================================
# 경로
# ============================================================
_BINPICK_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_GRASP_DB_PATH = _BINPICK_ROOT / "config" / "grasp_database.yaml"


# ============================================================
# GraspPlanner
# ============================================================
class GraspPlanner:
    """부품별 그래스프 자세 계산기.

    grasp_database.yaml을 로드하고, L4 인식 결과(부품명 + 변환행렬)에서
    로봇 실행용 피킹 자세를 계산한다.
    """

    def __init__(self, db_path: Path = DEFAULT_GRASP_DB_PATH):
        """
        Args:
            db_path: grasp_database.yaml 경로
        """
        self.db_path = Path(db_path)
        self._db: Dict[str, Any] = {}
        self._defaults: Dict[str, Any] = {}
        self._robot: Dict[str, Any] = {}

        self.load_database()

    def load_database(self):
        """YAML 데이터베이스를 로드한다."""
        if not self.db_path.exists():
            raise FileNotFoundError(f"그래스프 DB 없음: {self.db_path}")

        with open(self.db_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._robot = data.get("robot", {})
        self._defaults = data.get("defaults", {})
        self._db = data.get("parts", {})

    @property
    def part_names(self) -> List[str]:
        """정의된 부품 이름 목록."""
        return list(self._db.keys())

    @property
    def part_count(self) -> int:
        """정의된 부품 수."""
        return len(self._db)

    def has_grasp(self, part_name: str) -> bool:
        """해당 부품의 그래스프가 정의되어 있는지."""
        return part_name in self._db

    def get_grasp_params(self, part_name: str) -> Dict[str, Any]:
        """부품의 그래스프 파라미터를 반환한다 (기본값 병합).

        Args:
            part_name: 부품 이름

        Returns:
            그래스프 파라미터 딕셔너리
        """
        if part_name in self._db:
            params = {**self._defaults, **self._db[part_name]}
        else:
            # 미정의 부품 → 기본값만
            params = {
                **self._defaults,
                "description": f"미정의 부품 ({part_name}) — 기본값 사용",
                "approach_axis": [0, 0, -1],
                "grasp_center_mm": [0, 0, 0],
                "grasp_depth_mm": 15,
                "grasp_type": "parallel",
            }
        return params

    def compute_grasp_local(self, params: Dict[str, Any]) -> np.ndarray:
        """로컬 그래스프 변환행렬(4x4)을 계산한다.

        부품 좌표계에서 그리퍼가 접근하는 자세를 정의.
        - Z축: approach 방향 (그리퍼 접근 축)
        - 위치: grasp_center + approach 방향으로 grasp_depth만큼 오프셋

        Args:
            params: get_grasp_params() 반환 딕셔너리

        Returns:
            4x4 동차 변환행렬 (부품 로컬 → 그래스프 포즈)
        """
        approach = np.array(params.get("approach_axis", [0, 0, -1]), dtype=float)
        approach = approach / (np.linalg.norm(approach) + 1e-8)

        center = np.array(params.get("grasp_center_mm", [0, 0, 0]), dtype=float) * 0.001  # mm→m
        depth = params.get("grasp_depth_mm", 15) * 0.001  # mm→m

        # 그래스프 위치: 부품 중심에서 접근 방향 반대로 depth만큼
        grasp_position = center - approach * depth

        # 회전: approach를 Z축으로 하는 프레임 구성
        R = self._rotation_from_approach(approach)

        T = np.eye(4)
        T[:3, :3] = R
        T[:3, 3] = grasp_position

        return T

    def compute_grasp_world(
        self,
        part_name: str,
        T_part_world: np.ndarray,
    ) -> Dict[str, Any]:
        """월드 좌표계에서의 그래스프 자세를 계산한다.

        T_grasp_world = T_part_world @ T_grasp_local

        Args:
            part_name: L4에서 인식된 부품 이름
            T_part_world: L4에서 추정된 4x4 변환행렬 (레퍼런스 → 씬)

        Returns:
            dict: {
                "part_name": str,
                "T_grasp_world": ndarray(4,4),
                "position_mm": {"x", "y", "z"},
                "approach_vector": [3],
                "gripper_width_mm": float,
                "gripper_force_N": float,
                "grasp_type": str,
                "defined": bool,  # DB에 정의된 부품인지
            }
        """
        params = self.get_grasp_params(part_name)
        T_grasp_local = self.compute_grasp_local(params)

        # 월드 그래스프 자세
        T_grasp_world = T_part_world @ T_grasp_local

        # 위치 추출
        position = T_grasp_world[:3, 3]

        # 접근 벡터 (월드 좌표계에서의 그리퍼 Z축)
        approach_world = T_grasp_world[:3, 2]

        return {
            "part_name": part_name,
            "T_grasp_world": T_grasp_world,
            "position_mm": {
                "x": float(position[0] * 1000),
                "y": float(position[1] * 1000),
                "z": float(position[2] * 1000),
            },
            "approach_vector": approach_world.tolist(),
            "gripper_width_mm": params.get("gripper_width_mm", self._defaults.get("gripper_width_mm", 40)),
            "gripper_force_N": params.get("gripper_force_N", self._defaults.get("gripper_force_N", 15)),
            "grasp_type": params.get("grasp_type", "parallel"),
            "retreat_height_mm": params.get("retreat_height_mm", self._defaults.get("retreat_height_mm", 100)),
            "defined": part_name in self._db,
        }

    def validate_pick(self, grasp: Dict[str, Any]) -> Dict[str, Any]:
        """피킹 자세가 로봇 안전 범위 내인지 검증한다.

        Args:
            grasp: compute_grasp_world() 반환값

        Returns:
            {"safe": bool, "warnings": [str]} — 위반 항목 목록
        """
        warnings = []
        pos = grasp["position_mm"]
        safety = self._robot.get("safety", {})
        workspace = self._robot.get("workspace_mm", {})

        # 작업 영역 체크
        for axis in ["x", "y", "z"]:
            bounds = workspace.get(axis)
            if bounds and not (bounds[0] <= pos[axis] <= bounds[1]):
                warnings.append(
                    f"{axis.upper()}={pos[axis]:.1f}mm 작업 영역 벗어남 "
                    f"[{bounds[0]}, {bounds[1]}]"
                )

        # 최소 Z 높이 (빈 바닥 충돌 방지)
        min_z = safety.get("min_z_mm")
        if min_z is not None and pos["z"] < min_z:
            warnings.append(
                f"Z={pos['z']:.1f}mm < min_z={min_z}mm (충돌 위험)"
            )

        # 그리퍼 힘 제한
        max_force = safety.get("max_gripper_force_N")
        if max_force and grasp["gripper_force_N"] > max_force:
            warnings.append(
                f"force={grasp['gripper_force_N']}N > max={max_force}N"
            )

        return {"safe": len(warnings) == 0, "warnings": warnings}

    def plan_picks(
        self,
        recognized_parts: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """L4 인식 결과 리스트에서 피킹 계획을 생성한다.

        Args:
            recognized_parts: L4 결과 리스트. 각 항목:
                {"name": str, "transformation": ndarray(4,4), "decision": str, ...}

        Returns:
            피킹 계획 리스트 (ACCEPT된 부품만, z축 높은 순):
            [{"part_name", "T_grasp_world", "position_mm", ...}, ...]
        """
        picks = []

        for part in recognized_parts:
            if part.get("decision") != "ACCEPT":
                continue
            if part.get("transformation") is None:
                continue

            grasp = self.compute_grasp_world(
                part["name"],
                part["transformation"],
            )
            grasp["cluster_id"] = part.get("cluster_id")
            grasp["fitness"] = part.get("fitness")
            grasp["rmse"] = part.get("rmse")

            # 로봇 안전 검증
            validation = self.validate_pick(grasp)
            grasp["safe"] = validation["safe"]
            grasp["warnings"] = validation["warnings"]

            picks.append(grasp)

        # z축 높은 순 (위에 있는 부품부터 피킹 — 충돌 방지)
        picks.sort(key=lambda p: -p["position_mm"]["z"])

        return picks

    @staticmethod
    def _rotation_from_approach(approach: np.ndarray) -> np.ndarray:
        """접근 벡터를 Z축으로 하는 3x3 회전행렬을 생성한다."""
        z = approach / (np.linalg.norm(approach) + 1e-8)

        # X축: z와 수직인 벡터 생성
        if abs(z[2]) < 0.9:
            up = np.array([0, 0, 1])
        else:
            up = np.array([1, 0, 0])

        x = np.cross(up, z)
        x = x / (np.linalg.norm(x) + 1e-8)
        y = np.cross(z, x)

        R = np.column_stack([x, y, z])
        return R

    def print_database(self):
        """데이터베이스 내용을 출력한다."""
        print(f"  그래스프 DB: {self.db_path}")
        print(f"  정의 부품: {self.part_count}종")
        print(f"  기본값: width={self._defaults.get('gripper_width_mm')}mm, "
              f"force={self._defaults.get('gripper_force_N')}N, "
              f"retreat={self._defaults.get('retreat_height_mm')}mm")
        print()

        for name in sorted(self._db.keys()):
            p = self._db[name]
            print(f"    {name:>35}  width={p.get('gripper_width_mm', '?')}mm  "
                  f"force={p.get('gripper_force_N', '?')}N  "
                  f"depth={p.get('grasp_depth_mm', '?')}mm")


# ============================================================
# CLI
# ============================================================
if __name__ == "__main__":
    planner = GraspPlanner()

    print("=" * 60)
    print("  L5 그래스프 데이터베이스")
    print("=" * 60)
    planner.print_database()

    # 테스트: 단위 변환 + 자세 계산
    print()
    print("=" * 60)
    print("  그래스프 자세 계산 테스트")
    print("=" * 60)
    print()

    # 가상 L4 결과
    test_parts = [
        {"name": "01_sol_block_a", "transformation": np.eye(4), "decision": "ACCEPT"},
        {"name": "07_guide_paper_l", "transformation": np.eye(4), "decision": "ACCEPT"},
        {"name": "unknown_part", "transformation": np.eye(4), "decision": "ACCEPT"},
        {"name": "bracket_sensor1", "transformation": np.eye(4), "decision": "REJECT"},
    ]

    picks = planner.plan_picks(test_parts)

    print(f"  입력: {len(test_parts)}개 (ACCEPT {sum(1 for p in test_parts if p['decision']=='ACCEPT')}개)")
    print(f"  피킹 계획: {len(picks)}개")
    print()

    for i, pick in enumerate(picks):
        pos = pick["position_mm"]
        print(f"  [{i+1}] {pick['part_name']:>25}  "
              f"pos=({pos['x']:+7.1f}, {pos['y']:+7.1f}, {pos['z']:+7.1f})mm  "
              f"width={pick['gripper_width_mm']}mm  force={pick['gripper_force_N']}N  "
              f"defined={'✅' if pick['defined'] else '⚠️ 기본값'}")
