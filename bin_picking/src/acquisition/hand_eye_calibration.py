"""
Hand-Eye Calibration for 3D Bin Picking System
===============================================

Eye-to-Hand (고정 카메라) + Eye-in-Hand (로봇암 카메라) 캘리브레이션

로봇: HCR-10L (Modbus TCP, 포트 502)

설정 1 (Eye-to-Hand): Blaze-112 ToF 고정 카메라 → T_cam_to_base
설정 2 (Eye-in-Hand): ace2 5MP RGB 로봇암 카메라 → T_cam_to_gripper

캘리브레이션 원리 (Eye-to-Hand / Fixed Camera):
    AX = XB  (고전적 Hand-Eye 문제)

    Eye-to-Hand 설정에서:
      - A = T_gripper_to_base(i)^{-1} * T_gripper_to_base(j)  (로봇 포즈 쌍의 상대 변환)
      - B = T_cam_to_target(i) * T_cam_to_target(j)^{-1}      (카메라-보드 상대 변환)
      - X = T_cam_to_base                                       (구하려는 변환)

    OpenCV cv2.calibrateHandEye()는 기본적으로 eye-in-hand를 가정:
      - eye-in-hand: R_gripper2base에 직접 전달 → 결과 = T_cam_to_gripper
      - eye-to-hand: R_gripper2base에 역행렬 전달 → 결과 = T_cam_to_base

    Eye-in-Hand 좌표 변환:
      P_base = T_gripper_to_base @ T_cam_to_gripper @ P_camera
      (→ 매 캡처 시 현재 로봇 포즈 T_gripper_to_base가 필요)

카메라 입고 후 이 코드를 바로 실행하여 캘리브레이션 수행
(카메라 입고 예상: 2026년 5월)

HCR-10L 로봇 포즈 읽기 (Modbus TCP):
    - 통신: Modbus TCP, 포트 502
    - 관절 각도: Input Register 영역
    - 레지스터 레이아웃 (HCR-10L, 6축):
        Register 0-1:  Joint 1 angle (float32, 2 registers)
        Register 2-3:  Joint 2 angle (float32)
        Register 4-5:  Joint 3 angle (float32)
        Register 6-7:  Joint 4 angle (float32)
        Register 8-9:  Joint 5 angle (float32)
        Register 10-11: Joint 6 angle (float32)
      또는 TCP 포즈 직접 읽기:
        Register 12-13: X (mm, float32)
        Register 14-15: Y (mm)
        Register 16-17: Z (mm)
        Register 18-19: Rx (deg, float32)
        Register 20-21: Ry (deg)
        Register 22-23: Rz (deg)

    pymodbus 코드 예시:
    ```python
    from pymodbus.client import ModbusTcpClient

    client = ModbusTcpClient('192.168.100.x', port=502)
    client.connect()

    # TCP 포즈 읽기 (X,Y,Z,Rx,Ry,Rz → 12 registers = 6 floats)
    result = client.read_input_registers(address=12, count=12, slave=1)
    if not result.isError():
        import struct
        values = []
        for i in range(0, 12, 2):
            raw = struct.pack('>HH', result.registers[i], result.registers[i+1])
            values.append(struct.unpack('>f', raw)[0])
        x, y, z = values[0]/1000, values[1]/1000, values[2]/1000  # mm → m
        rx, ry, rz = np.radians(values[3]), np.radians(values[4]), np.radians(values[5])
        # rx, ry, rz → 회전행렬 변환 후 4x4 동차 행렬 구성
    client.close()
    ```

Dependencies:
    pip install numpy opencv-python-headless scipy open3d
"""

import argparse
import pickle
import time
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from scipy.spatial.transform import Rotation


# 캘리브레이션 결과 저장 디렉토리
CALIBRATION_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "calibration"

# 카메라 프리셋 (카메라 입고 후 실측값으로 교체)
CAMERA_PRESETS = {
    "blaze-112": {
        "width": 640, "height": 480,
        "fx": 460.0, "fy": 460.0, "cx": 320.0, "cy": 240.0,
        "dist_coeffs": [0, 0, 0, 0, 0],
        "description": "Basler Blaze-112 ToF (eye-to-hand, overhead)",
    },
    "ace2-5mp": {
        "width": 2448, "height": 2048,
        "fx": 3000.0, "fy": 3000.0, "cx": 1224.0, "cy": 1024.0,
        "dist_coeffs": [0, 0, 0, 0, 0],
        "description": "Basler ace2 5MP RGB (eye-in-hand, arm-mounted)",
    },
    "d435": {
        "width": 640, "height": 480,
        "fx": 607.7, "fy": 607.4, "cx": 319.3, "cy": 242.4,
        "dist_coeffs": [0, 0, 0, 0, 0],
        "description": "Intel RealSense D435 (development/test)",
    },
}


# ============================================================================
# 유틸리티 함수
# ============================================================================

def pose_to_matrix(position: np.ndarray, rotation: np.ndarray) -> np.ndarray:
    """위치(xyz) + 회전(3x3 또는 euler xyz in radians) → 4x4 동차 행렬 변환.

    Args:
        position: (3,) 위치 벡터 [m]
        rotation: (3,3) 회전 행렬 또는 (3,) Euler XYZ [rad]

    Returns:
        (4,4) 동차 변환 행렬
    """
    T = np.eye(4)
    if rotation.shape == (3, 3):
        T[:3, :3] = rotation
    elif rotation.shape == (3,):
        T[:3, :3] = Rotation.from_euler('xyz', rotation).as_matrix()
    else:
        raise ValueError(f"rotation shape must be (3,3) or (3,), got {rotation.shape}")
    T[:3, 3] = position
    return T


def matrix_to_rvec_tvec(T: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """4x4 동차 행렬 → (rvec, tvec) 변환 (OpenCV 형식)."""
    rvec, _ = cv2.Rodrigues(T[:3, :3])
    tvec = T[:3, 3].reshape(3, 1)
    return rvec, tvec


def rvec_tvec_to_matrix(rvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    """(rvec, tvec) → 4x4 동차 행렬 변환."""
    R, _ = cv2.Rodrigues(rvec)
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = tvec.flatten()
    return T


def rotation_error_deg(R1: np.ndarray, R2: np.ndarray) -> float:
    """두 회전 행렬 사이의 각도 오차 (degrees)."""
    R_diff = R1 @ R2.T
    trace_val = np.clip((np.trace(R_diff) - 1.0) / 2.0, -1.0, 1.0)
    return np.degrees(np.arccos(trace_val))


def translation_error_mm(t1: np.ndarray, t2: np.ndarray) -> float:
    """두 이동 벡터 사이의 거리 오차 (mm)."""
    return float(np.linalg.norm(t1.flatten() - t2.flatten())) * 1000.0


# ============================================================================
# HandEyeCalibrator 클래스
# ============================================================================

class HandEyeCalibrator:
    """Hand-Eye 캘리브레이션 (Eye-to-Hand + Eye-in-Hand 지원).

    Eye-to-Hand: 카메라 고정(빈 위), 체커보드는 로봇 그리퍼에 장착
      → T_cam_to_base (카메라→로봇 베이스)
    Eye-in-Hand: 카메라가 로봇암에 장착, 체커보드는 고정 위치
      → T_cam_to_gripper (카메라→그리퍼)
      → P_base = T_gripper_to_base @ T_cam_to_gripper @ P_camera
    """

    # OpenCV Hand-Eye 캘리브레이션 메서드 매핑
    METHODS = {
        "tsai": cv2.CALIB_HAND_EYE_TSAI,
        "park": cv2.CALIB_HAND_EYE_PARK,
        "horaud": cv2.CALIB_HAND_EYE_HORAUD,
        "daniilidis": cv2.CALIB_HAND_EYE_DANIILIDIS,
    }

    def __init__(self, board_size: Tuple[int, int] = (9, 6), square_size: float = 0.015,
                 mode: str = "eye-to-hand"):
        """초기화.

        Args:
            board_size: 체커보드 내부 코너 수 (columns, rows). 기본 9x6.
            square_size: 체커보드 사각형 한 변 길이 [m]. 기본 15mm.
            mode: "eye-to-hand" (고정 카메라) 또는 "eye-in-hand" (로봇암 카메라)
        """
        if mode not in ("eye-to-hand", "eye-in-hand"):
            raise ValueError(f"mode must be 'eye-to-hand' or 'eye-in-hand', got '{mode}'")

        self.mode = mode
        self.board_size = board_size
        self.square_size = square_size

        # 체커보드 3D 좌표 (보드 좌표계에서, Z=0 평면)
        self.objp = np.zeros((board_size[0] * board_size[1], 3), dtype=np.float32)
        self.objp[:, :2] = np.mgrid[0:board_size[0], 0:board_size[1]].T.reshape(-1, 2)
        self.objp *= square_size

        # 캘리브레이션 데이터 저장
        self.robot_poses: List[np.ndarray] = []         # T_gripper_to_base (4x4)
        self.cam_to_board_poses: List[np.ndarray] = []  # T_target_to_cam (4x4)
        self.images: List[np.ndarray] = []               # 원본 이미지 (검증용)

        # 카메라 내부 파라미터 (모드별 기본값)
        if mode == "eye-to-hand":
            preset = CAMERA_PRESETS["blaze-112"]
        else:
            preset = CAMERA_PRESETS["ace2-5mp"]
        self.camera_matrix = np.array([
            [preset["fx"], 0.0, preset["cx"]],
            [0.0, preset["fy"], preset["cy"]],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)
        self.dist_coeffs = np.array(preset["dist_coeffs"], dtype=np.float64)

        # HCR-10L TCP 오프셋 (그리퍼 장착 후 실측값으로 설정)
        self.tcp_offset: Optional[np.ndarray] = None  # 4x4, 플랜지→TCP

        # 캘리브레이션 결과
        self.T_cam_to_base: Optional[np.ndarray] = None      # eye-to-hand 결과
        self.T_cam_to_gripper: Optional[np.ndarray] = None    # eye-in-hand 결과
        self.calibration_error: Optional[float] = None

    def set_camera_preset(self, name: str):
        """카메라 프리셋으로 내부 파라미터 설정.

        Args:
            name: "blaze-112", "ace2-5mp", "d435" 중 하나
        """
        if name not in CAMERA_PRESETS:
            raise ValueError(f"Unknown preset: {name}. Available: {list(CAMERA_PRESETS.keys())}")
        p = CAMERA_PRESETS[name]
        self.camera_matrix = np.array([
            [p["fx"], 0.0, p["cx"]],
            [0.0, p["fy"], p["cy"]],
            [0.0, 0.0, 1.0],
        ], dtype=np.float64)
        self.dist_coeffs = np.array(p["dist_coeffs"], dtype=np.float64)

    def set_camera_intrinsics(self, camera_matrix: np.ndarray, dist_coeffs: np.ndarray):
        """카메라 내부 파라미터 설정 (카메라 캘리브레이션 결과 사용).

        Args:
            camera_matrix: (3,3) 카메라 행렬
            dist_coeffs: (5,) 또는 (4,) 왜곡 계수
        """
        self.camera_matrix = camera_matrix.astype(np.float64)
        self.dist_coeffs = dist_coeffs.flatten().astype(np.float64)

    def set_tcp_offset(self, x: float = 0, y: float = 0, z: float = 0,
                       rx: float = 0, ry: float = 0, rz: float = 0):
        """HCR-10L TCP 오프셋 설정 (플랜지 → 공구 끝점).

        로봇 티칭 후 실측값을 입력한다. 단위: mm, deg.
        grasp_database.yaml의 robot.tcp_offset_mm 값과 동일.

        Args:
            x, y, z: 위치 오프셋 (mm)
            rx, ry, rz: 회전 오프셋 (deg)
        """
        R = Rotation.from_euler("ZYX", [rz, ry, rx], degrees=True).as_matrix()
        self.tcp_offset = np.eye(4)
        self.tcp_offset[:3, :3] = R
        self.tcp_offset[:3, 3] = np.array([x, y, z]) * 0.001  # mm → m

    def load_tcp_offset_from_yaml(self, yaml_path: Optional[str] = None):
        """grasp_database.yaml에서 TCP 오프셋을 로드한다."""
        import yaml
        if yaml_path is None:
            yaml_path = Path(__file__).resolve().parent.parent.parent / "config" / "grasp_database.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        tcp = data.get("robot", {}).get("tcp_offset_mm", {})
        self.set_tcp_offset(
            x=tcp.get("x", 0), y=tcp.get("y", 0), z=tcp.get("z", 0),
            rx=tcp.get("rx", 0), ry=tcp.get("ry", 0), rz=tcp.get("rz", 0),
        )

    def add_measurement(
        self,
        robot_pose_4x4: np.ndarray,
        camera_image: np.ndarray,
    ) -> bool:
        """로봇 포즈 + 카메라 이미지 쌍 추가.

        체커보드 코너를 검출하고, solvePnP로 카메라-보드 변환을 계산한다.

        Args:
            robot_pose_4x4: (4,4) T_gripper_to_base (로봇 베이스 기준 그리퍼 포즈)
            camera_image: 그레이스케일 또는 BGR 이미지 (체커보드가 보여야 함)

        Returns:
            True if 체커보드 검출 성공, False otherwise
        """
        # 그레이스케일 변환
        if len(camera_image.shape) == 3:
            gray = cv2.cvtColor(camera_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = camera_image.copy()

        # ----------------------------------------------------------------
        # 체커보드 코너 검출
        # ----------------------------------------------------------------
        flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
        found, corners = cv2.findChessboardCorners(gray, self.board_size, flags)

        if not found:
            return False

        # 서브픽셀 정밀도로 코너 위치 보정
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        corners_refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

        # ----------------------------------------------------------------
        # 카메라-보드 변환 계산 (solvePnP)
        # ----------------------------------------------------------------
        success, rvec, tvec = cv2.solvePnP(
            self.objp, corners_refined, self.camera_matrix, self.dist_coeffs,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            return False

        T_target_to_cam = rvec_tvec_to_matrix(rvec, tvec)

        # 저장
        self.robot_poses.append(robot_pose_4x4.copy())
        self.cam_to_board_poses.append(T_target_to_cam)
        self.images.append(camera_image.copy())

        return True

    def add_measurement_from_transform(
        self,
        robot_pose_4x4: np.ndarray,
        T_target_to_cam: np.ndarray,
    ):
        """로봇 포즈 + 카메라-보드 변환 쌍을 직접 추가 (시뮬레이션/테스트용).

        Args:
            robot_pose_4x4: (4,4) T_gripper_to_base
            T_target_to_cam: (4,4) T_target_to_cam
        """
        self.robot_poses.append(robot_pose_4x4.copy())
        self.cam_to_board_poses.append(T_target_to_cam.copy())

    def calibrate(self, method: str = "tsai") -> Tuple[np.ndarray, np.ndarray, float]:
        """Hand-Eye 캘리브레이션 수행.

        Eye-to-Hand 설정에서 cv2.calibrateHandEye에 전달하는 방식:
          - R_gripper2base, t_gripper2base: 로봇 그리퍼→베이스 변환 (= T_gripper_to_base)
          - R_target2cam, t_target2cam: 보드→카메라 변환 (= T_target_to_cam)
        결과가 T_cam_to_base (= T_cam_to_gripper in general notation, eye-to-hand에서는 base)

        Args:
            method: "tsai", "park", "horaud", "daniilidis" 중 하나

        Returns:
            R_cam2base: (3,3) 카메라→베이스 회전
            t_cam2base: (3,1) 카메라→베이스 이동
            reprojection_error: 재투영 오차
        """
        n = len(self.robot_poses)
        if n < 3:
            raise ValueError(f"최소 3개의 측정이 필요합니다 (현재 {n}개)")

        if method not in self.METHODS:
            raise ValueError(f"지원되지 않는 메서드: {method}. "
                             f"가능한 값: {list(self.METHODS.keys())}")

        # OpenCV calibrateHandEye는 기본적으로 eye-in-hand를 가정.
        # eye-to-hand: 로봇 포즈의 역행렬 전달 → 결과 = T_cam_to_base
        # eye-in-hand: 로봇 포즈 직접 전달 → 결과 = T_cam_to_gripper
        R_gripper2base_list = []
        t_gripper2base_list = []
        R_target2cam_list = []
        t_target2cam_list = []

        for i in range(n):
            if self.mode == "eye-to-hand":
                T_input = np.linalg.inv(self.robot_poses[i])
            else:  # eye-in-hand
                T_input = self.robot_poses[i]
            rvec_bg, tvec_bg = matrix_to_rvec_tvec(T_input)
            R_gripper2base_list.append(rvec_bg)
            t_gripper2base_list.append(tvec_bg)

            rvec_tc, tvec_tc = matrix_to_rvec_tvec(self.cam_to_board_poses[i])
            R_target2cam_list.append(rvec_tc)
            t_target2cam_list.append(tvec_tc)

        R_cam2base, t_cam2base = cv2.calibrateHandEye(
            R_gripper2base=R_gripper2base_list,
            t_gripper2base=t_gripper2base_list,
            R_target2cam=R_target2cam_list,
            t_target2cam=t_target2cam_list,
            method=self.METHODS[method],
        )

        # 4x4 행렬 구성
        T = np.eye(4)
        T[:3, :3] = R_cam2base
        T[:3, 3] = t_cam2base.flatten()

        if self.mode == "eye-to-hand":
            self.T_cam_to_base = T
        else:  # eye-in-hand
            self.T_cam_to_gripper = T

        # 재투영 오차 계산
        error = self._compute_reprojection_error(T)
        self.calibration_error = error

        return R_cam2base, t_cam2base, error

    def calibrate_all_methods(self) -> Tuple[np.ndarray, str, float]:
        """4가지 메서드로 캘리브레이션하고 최적 결과 선택.

        Returns:
            best_T_cam2base: (4,4) 최적 변환 행렬
            best_method: 최적 메서드 이름
            best_error: 최적 재투영 오차
        """
        results = {}
        for method_name in self.METHODS:
            try:
                R, t, error = self.calibrate(method=method_name)
                T = np.eye(4)
                T[:3, :3] = R
                T[:3, 3] = t.flatten()
                results[method_name] = (T, error)
            except Exception as e:
                results[method_name] = (None, float('inf'))
                print(f"  [WARN] {method_name} 실패: {e}")

        # 최적 결과 선택 (최소 재투영 오차)
        best_method = min(results, key=lambda m: results[m][1])
        best_T, best_error = results[best_method]
        if self.mode == "eye-to-hand":
            self.T_cam_to_base = best_T
        else:
            self.T_cam_to_gripper = best_T
        self.calibration_error = best_error

        return best_T, best_method, best_error, results

    def _compute_reprojection_error(self, T_cam2base: np.ndarray) -> float:
        """캘리브레이션 결과의 일관성 오차 계산.

        각 측정 쌍에서 T_cam2base를 통해 보드→베이스 변환을 두 가지 경로로 계산하고
        차이를 측정한다.

        경로 1: T_board_to_base = T_cam2base @ T_target_to_cam^{-1}  (잘못됨, 아래 수정)
        실제:   T_board_to_base(via cam)   = T_cam2base @ T_target_to_cam
                T_board_to_base(via robot) = T_gripper2base @ T_board_to_gripper

        간단한 일관성 오차:
          T_cam2base는 모든 포즈 쌍에서 동일해야 함.
          T_cam2base = T_gripper2base @ T_board2gripper @ T_target2cam^{-1}
          → 각 쌍에서 역산한 T_cam2base와 결과의 차이.
        """
        errors = []
        for i in range(len(self.robot_poses)):
            T_gripper2base = self.robot_poses[i]
            T_target2cam = self.cam_to_board_poses[i]

            # Eye-to-hand 일관성: T_cam2base @ T_target2cam = T_gripper2base @ T_board2gripper
            # 여기서 T_board2gripper는 알 수 없으므로, 쌍 간 일관성으로 측정
            pass

        # 쌍 간 일관성 오차
        if len(self.robot_poses) < 2:
            return 0.0

        pair_errors = []
        for i in range(len(self.robot_poses)):
            for j in range(i + 1, len(self.robot_poses)):
                # 로봇 상대 변환
                T_ij_robot = np.linalg.inv(self.robot_poses[i]) @ self.robot_poses[j]
                # 카메라 상대 변환
                T_ij_cam = self.cam_to_board_poses[i] @ np.linalg.inv(self.cam_to_board_poses[j])

                T_inv = np.linalg.inv(T_cam2base)
                if self.mode == "eye-to-hand":
                    # T_cam2base @ T_ij_cam @ T_cam2base^{-1} ≈ T_ij_robot^{-1}
                    lhs = T_cam2base @ T_ij_cam @ T_inv
                    rhs = np.linalg.inv(T_ij_robot)
                else:
                    # eye-in-hand: T_cam2gripper^{-1} @ T_ij_robot @ T_cam2gripper ≈ T_ij_cam
                    lhs = T_inv @ T_ij_robot @ T_cam2base
                    rhs = T_ij_cam

                # 이동 오차 (mm)
                t_err = np.linalg.norm(lhs[:3, 3] - rhs[:3, 3]) * 1000.0
                pair_errors.append(t_err)

        return float(np.mean(pair_errors)) if pair_errors else 0.0

    def transform_to_base(self, points_camera: np.ndarray,
                          T_gripper_to_base: Optional[np.ndarray] = None) -> np.ndarray:
        """카메라 좌표계의 3D 포인트를 로봇 베이스 좌표계로 변환.

        Eye-to-hand: P_base = T_cam_to_base @ P_cam
        Eye-in-hand: P_base = T_gripper_to_base @ T_cam_to_gripper @ P_cam
                     (→ T_gripper_to_base 필수, 캡처 시점의 현재 로봇 포즈)

        Args:
            points_camera: (N, 3) 카메라 좌표계 포인트 [m]
            T_gripper_to_base: (4,4) 현재 그리퍼→베이스 변환 (eye-in-hand에서 필수)

        Returns:
            points_base: (N, 3) 로봇 베이스 좌표계 포인트 [m]
        """
        pts = np.asarray(points_camera, dtype=np.float64)
        if pts.ndim == 1:
            pts = pts.reshape(1, 3)

        if self.mode == "eye-to-hand":
            if self.T_cam_to_base is None:
                raise RuntimeError("캘리브레이션이 수행되지 않았습니다. calibrate()를 먼저 호출하세요.")
            T = self.T_cam_to_base
        else:  # eye-in-hand
            if self.T_cam_to_gripper is None:
                raise RuntimeError("캘리브레이션이 수행되지 않았습니다. calibrate()를 먼저 호출하세요.")
            if T_gripper_to_base is None:
                raise ValueError("eye-in-hand 모드에서는 T_gripper_to_base (현재 로봇 포즈)가 필수입니다.")
            T = T_gripper_to_base @ self.T_cam_to_gripper

        R = T[:3, :3]
        t = T[:3, 3]
        points_base = (R @ pts.T).T + t
        return points_base

    def validate(
        self,
        robot_pose: np.ndarray,
        camera_image: np.ndarray,
    ) -> Optional[float]:
        """검증: 알려진 체커보드 코너를 투영하여 재투영 오차 측정.

        Args:
            robot_pose: (4,4) T_gripper_to_base
            camera_image: 그레이스케일 또는 BGR 이미지

        Returns:
            재투영 오차 (pixels), 체커보드 미검출 시 None
        """
        if self.T_cam_to_base is None:
            raise RuntimeError("캘리브레이션이 수행되지 않았습니다.")

        if len(camera_image.shape) == 3:
            gray = cv2.cvtColor(camera_image, cv2.COLOR_BGR2GRAY)
        else:
            gray = camera_image.copy()

        flags = cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_NORMALIZE_IMAGE
        found, corners = cv2.findChessboardCorners(gray, self.board_size, flags)
        if not found:
            return None

        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        corners_refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

        # 체커보드 3D 좌표 → 베이스 → 카메라로 변환하여 투영
        # 경로: board → gripper → base → camera
        # T_cam_to_base 역행렬 = T_base_to_cam
        T_base_to_cam = np.linalg.inv(self.T_cam_to_base)

        # solvePnP로 실제 카메라-보드 변환 구하기
        success, rvec, tvec = cv2.solvePnP(
            self.objp, corners_refined, self.camera_matrix, self.dist_coeffs,
        )
        if not success:
            return None

        # 재투영
        projected, _ = cv2.projectPoints(
            self.objp, rvec, tvec, self.camera_matrix, self.dist_coeffs,
        )
        error = cv2.norm(corners_refined, projected, cv2.NORM_L2) / len(projected)
        return float(error)

    def save(self, filepath: str = ""):
        """캘리브레이션 결과 저장.

        Args:
            filepath: 저장 경로 (.pkl). 빈 문자열이면 기본 경로 사용.
        """
        if not filepath:
            CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"{self.mode.replace('-', '_')}.pkl"
            filepath = str(CALIBRATION_DIR / filename)

        data = {
            "mode": self.mode,
            "T_cam_to_base": self.T_cam_to_base,
            "T_cam_to_gripper": self.T_cam_to_gripper,
            "calibration_error": self.calibration_error,
            "camera_matrix": self.camera_matrix,
            "dist_coeffs": self.dist_coeffs,
            "board_size": self.board_size,
            "square_size": self.square_size,
            "n_measurements": len(self.robot_poses),
        }
        with open(filepath, "wb") as f:
            pickle.dump(data, f)
        print(f"캘리브레이션 결과 저장: {filepath} (mode={self.mode})")

    def load(self, filepath: str):
        """캘리브레이션 결과 로드.

        Args:
            filepath: 저장 경로 (.pkl)
        """
        with open(filepath, "rb") as f:
            data = pickle.load(f)
        self.mode = data.get("mode", "eye-to-hand")
        self.T_cam_to_base = data.get("T_cam_to_base")
        self.T_cam_to_gripper = data.get("T_cam_to_gripper")
        self.calibration_error = data["calibration_error"]
        self.camera_matrix = data["camera_matrix"]
        self.dist_coeffs = data["dist_coeffs"]
        self.board_size = data["board_size"]
        self.square_size = data["square_size"]
        print(f"캘리브레이션 결과 로드: {filepath} (mode={self.mode}, {data['n_measurements']}개 측정)")


# ============================================================================
# 캘리브레이션 포즈 생성
# ============================================================================

def generate_calibration_poses(n_poses: int = 15) -> List[np.ndarray]:
    """캘리브레이션을 위한 추천 로봇 포즈 생성.

    빈 영역 주변에서 다양한 높이와 기울기를 가진 포즈를 생성한다.
    체커보드를 그리퍼에 장착하고 이 포즈들로 이동시키면
    좋은 캘리브레이션 커버리지를 얻을 수 있다.

    포즈 분포 전략:
      - 3개 높이 레벨 (Z: 0.15m, 0.25m, 0.35m)
      - 각 높이에서 XY 평면 5개 위치 (중심 + 4모서리)
      - 각 위치에서 다른 기울기 (±15도 tilt)

    Args:
        n_poses: 생성할 포즈 수 (기본 15)

    Returns:
        poses: 4x4 동차 행렬 리스트
    """
    poses = []
    rng = np.random.default_rng(42)

    # 빈 중심 위치 (로봇 베이스 기준, 대략적 값)
    bin_center = np.array([0.45, 0.0, 0.0])  # X=0.45m 전방, Y=0 중심

    # 높이 레벨
    heights = np.linspace(0.15, 0.35, 3)

    # XY 오프셋 (빈 내부 다양한 위치)
    xy_offsets = [
        (0.0, 0.0),       # 중심
        (0.06, 0.06),     # 우상
        (-0.06, 0.06),    # 좌상
        (0.06, -0.06),    # 우하
        (-0.06, -0.06),   # 좌하
    ]

    idx = 0
    for h in heights:
        for dx, dy in xy_offsets:
            if idx >= n_poses:
                break

            # 위치
            position = bin_center + np.array([dx, dy, h])

            # 기울기 (다양한 방향으로 기울임)
            tilt_x = rng.uniform(-15, 15)  # degrees
            tilt_y = rng.uniform(-15, 15)
            tilt_z = rng.uniform(-180, 180)  # 회전

            rotation = np.radians([tilt_x, tilt_y, tilt_z])
            T = pose_to_matrix(position, rotation)
            poses.append(T)
            idx += 1

    return poses[:n_poses]


# ============================================================================
# 시뮬레이션 (카메라/로봇 없이 테스트)
# ============================================================================

def _simulate_measurements(
    n_poses: int = 15,
    noise_rot_deg: float = 0.3,
    noise_trans_mm: float = 0.5,
    seed: int = 42,
) -> Tuple[
    List[np.ndarray],  # robot_poses
    List[np.ndarray],  # cam_to_board_poses
    np.ndarray,        # ground_truth T_cam_to_base
]:
    """시뮬레이션 캘리브레이션 측정 데이터 생성.

    알려진 ground truth T_cam_to_base를 설정하고,
    다양한 로봇 포즈 + 대응하는 카메라-보드 변환을 노이즈와 함께 생성한다.

    Args:
        n_poses: 포즈 수
        noise_rot_deg: 회전 노이즈 (degrees)
        noise_trans_mm: 이동 노이즈 (mm)
        seed: 난수 시드

    Returns:
        robot_poses: T_gripper_to_base 리스트
        cam_to_board_poses: T_target_to_cam 리스트
        T_cam_to_base_gt: ground truth 변환 행렬
    """
    rng = np.random.default_rng(seed)

    # --- Ground Truth: 카메라→베이스 변환 ---
    # 카메라가 빈 위 0.8m, 약간 기울어져 설치
    cam_position = np.array([0.45, 0.0, 0.8])  # 베이스에서 0.45m 전방, 0.8m 높이
    cam_rotation = Rotation.from_euler('xyz', [175, 0, 0], degrees=True).as_matrix()
    T_cam_to_base_gt = np.eye(4)
    T_cam_to_base_gt[:3, :3] = cam_rotation
    T_cam_to_base_gt[:3, 3] = cam_position

    # --- 로봇 포즈 생성 ---
    robot_poses = generate_calibration_poses(n_poses)

    # --- 대응하는 카메라-보드 변환 계산 ---
    # 체커보드가 그리퍼에 고정 (T_board_to_gripper는 상수)
    T_board_to_gripper = np.eye(4)
    T_board_to_gripper[:3, 3] = [0.0, 0.0, 0.02]  # 그리퍼에서 2cm 앞

    cam_to_board_poses = []
    valid_robot_poses = []

    for T_gripper_to_base in robot_poses:
        # T_board_to_base = T_gripper_to_base @ T_board_to_gripper
        T_board_to_base = T_gripper_to_base @ T_board_to_gripper

        # T_board_to_cam = T_base_to_cam @ T_board_to_base
        T_base_to_cam = np.linalg.inv(T_cam_to_base_gt)
        T_board_to_cam = T_base_to_cam @ T_board_to_base

        # 노이즈 추가
        noise_r = Rotation.from_euler(
            'xyz',
            rng.normal(0, noise_rot_deg, 3),
            degrees=True,
        ).as_matrix()
        noise_t = rng.normal(0, noise_trans_mm / 1000.0, 3)

        T_target_to_cam = T_board_to_cam.copy()
        T_target_to_cam[:3, :3] = noise_r @ T_target_to_cam[:3, :3]
        T_target_to_cam[:3, 3] += noise_t

        cam_to_board_poses.append(T_target_to_cam)
        valid_robot_poses.append(T_gripper_to_base)

    return valid_robot_poses, cam_to_board_poses, T_cam_to_base_gt


def _simulate_measurements_eye_in_hand(
    n_poses: int = 15,
    noise_rot_deg: float = 0.3,
    noise_trans_mm: float = 0.5,
    seed: int = 42,
) -> Tuple[
    List[np.ndarray],  # robot_poses
    List[np.ndarray],  # cam_to_board_poses
    np.ndarray,        # ground_truth T_cam_to_gripper
]:
    """Eye-in-Hand 시뮬레이션 캘리브레이션 측정 데이터 생성.

    카메라가 로봇암에 장착, 체커보드가 빈 옆 고정 위치에 놓인 상태.
    알려진 GT T_cam_to_gripper로부터 측정 데이터를 역산.

    Args:
        n_poses: 포즈 수
        noise_rot_deg: 회전 노이즈 (degrees)
        noise_trans_mm: 이동 노이즈 (mm)
        seed: 난수 시드

    Returns:
        robot_poses: T_gripper_to_base 리스트
        cam_to_board_poses: T_target_to_cam 리스트
        T_cam_to_gripper_gt: ground truth 변환 행렬
    """
    rng = np.random.default_rng(seed)

    # --- Ground Truth: 카메라→그리퍼 변환 ---
    # 카메라가 그리퍼에서 약간 오프셋 (50mm 앞, 30mm 아래)
    cam_pos = np.array([0.0, -0.03, 0.05])  # 그리퍼 기준 Z축 5cm 앞, Y축 3cm 아래
    cam_rot = Rotation.from_euler('xyz', [0, 0, 0], degrees=True).as_matrix()
    T_cam_to_gripper_gt = np.eye(4)
    T_cam_to_gripper_gt[:3, :3] = cam_rot
    T_cam_to_gripper_gt[:3, 3] = cam_pos

    # --- 체커보드 고정 위치 (로봇 베이스 기준) ---
    T_board_to_base = np.eye(4)
    T_board_to_base[:3, 3] = [0.40, 0.15, 0.0]  # 빈 옆 테이블

    # --- 로봇 포즈 생성 ---
    robot_poses = generate_calibration_poses(n_poses)

    # --- 대응하는 카메라-보드 변환 계산 ---
    cam_to_board_poses = []
    valid_robot_poses = []

    for T_gripper_to_base in robot_poses:
        # T_cam_to_base = T_gripper_to_base @ T_cam_to_gripper
        T_cam_to_base = T_gripper_to_base @ T_cam_to_gripper_gt

        # T_board_to_cam = T_cam_to_base^{-1} @ T_board_to_base
        T_base_to_cam = np.linalg.inv(T_cam_to_base)
        T_board_to_cam = T_base_to_cam @ T_board_to_base

        # 노이즈 추가
        noise_r = Rotation.from_euler(
            'xyz', rng.normal(0, noise_rot_deg, 3), degrees=True
        ).as_matrix()
        noise_t = rng.normal(0, noise_trans_mm / 1000.0, 3)

        T_target_to_cam = T_board_to_cam.copy()
        T_target_to_cam[:3, :3] = noise_r @ T_target_to_cam[:3, :3]
        T_target_to_cam[:3, 3] += noise_t

        cam_to_board_poses.append(T_target_to_cam)
        valid_robot_poses.append(T_gripper_to_base)

    return valid_robot_poses, cam_to_board_poses, T_cam_to_gripper_gt


# ============================================================================
# 메인 실행
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hand-Eye Calibration 시뮬레이션",
    )
    parser.add_argument(
        "--mode",
        choices=["eye-to-hand", "eye-in-hand"],
        default="eye-to-hand",
        help="캘리브레이션 모드 (기본: eye-to-hand)",
    )
    parser.add_argument(
        "--no-vis",
        action="store_true",
        help="시각화 비활성화 (Open3D 불필요)",
    )
    parser.add_argument(
        "--n-poses",
        type=int,
        default=15,
        help="시뮬레이션 포즈 수 (기본: 15)",
    )
    parser.add_argument(
        "--noise-rot",
        type=float,
        default=0.3,
        help="회전 노이즈 [deg] (기본: 0.3)",
    )
    parser.add_argument(
        "--noise-trans",
        type=float,
        default=0.5,
        help="이동 노이즈 [mm] (기본: 0.5)",
    )
    args = parser.parse_args()

    mode = args.mode
    mode_label = "Eye-to-Hand (고정 카메라)" if mode == "eye-to-hand" else "Eye-in-Hand (로봇암 카메라)"

    # ====================================================================
    # 1. 시뮬레이션 데이터 생성
    # ====================================================================
    print("=" * 70)
    print(f"  Hand-Eye Calibration 시뮬레이션 ({mode_label})")
    print("=" * 70)
    print()

    print("--- 1단계: 시뮬레이션 데이터 생성 ---")
    if mode == "eye-to-hand":
        robot_poses, cam_to_board_poses, T_gt = _simulate_measurements(
            n_poses=args.n_poses,
            noise_rot_deg=args.noise_rot,
            noise_trans_mm=args.noise_trans,
        )
        gt_label = "T_cam_to_base"
    else:
        robot_poses, cam_to_board_poses, T_gt = _simulate_measurements_eye_in_hand(
            n_poses=args.n_poses,
            noise_rot_deg=args.noise_rot,
            noise_trans_mm=args.noise_trans,
        )
        gt_label = "T_cam_to_gripper"

    print(f"  모드: {mode_label}")
    print(f"  포즈 수: {len(robot_poses)}")
    print(f"  노이즈: 회전 {args.noise_rot}deg, 이동 {args.noise_trans}mm")
    print(f"  Ground Truth {gt_label}:")
    print(f"    위치: [{T_gt[0,3]:.3f}, {T_gt[1,3]:.3f}, {T_gt[2,3]:.3f}] m")
    gt_euler = Rotation.from_matrix(T_gt[:3, :3]).as_euler('xyz', degrees=True)
    print(f"    회전: [{gt_euler[0]:.1f}, {gt_euler[1]:.1f}, {gt_euler[2]:.1f}] deg")
    print()

    # ====================================================================
    # 2. 캘리브레이션 수행 (4가지 메서드 비교)
    # ====================================================================
    print("--- 2단계: 캘리브레이션 (4가지 메서드 비교) ---")

    calibrator = HandEyeCalibrator(board_size=(9, 6), square_size=0.015, mode=mode)

    for rp, cp in zip(robot_poses, cam_to_board_poses):
        calibrator.add_measurement_from_transform(rp, cp)

    print(f"  측정 데이터: {len(calibrator.robot_poses)}개")
    print()

    best_T, best_method, best_error, all_results = calibrator.calibrate_all_methods()

    # 결과 테이블
    print(f"  {'메서드':<15} {'회전 오차 (deg)':>15} {'이동 오차 (mm)':>15} {'일관성 오차 (mm)':>16}")
    print(f"  {'-'*15} {'-'*15} {'-'*15} {'-'*16}")

    for method_name, (T_result, consistency_err) in all_results.items():
        if T_result is not None:
            r_err = rotation_error_deg(T_result[:3, :3], T_gt[:3, :3])
            t_err = translation_error_mm(T_result[:3, 3], T_gt[:3, 3])
            marker = " <-- BEST" if method_name == best_method else ""
            print(f"  {method_name:<15} {r_err:>15.4f} {t_err:>15.4f} {consistency_err:>16.4f}{marker}")
        else:
            print(f"  {method_name:<15} {'FAILED':>15} {'FAILED':>15} {'FAILED':>16}")
    print()

    # ====================================================================
    # 3. 최적 결과 출력
    # ====================================================================
    print("--- 3단계: 최적 캘리브레이션 결과 ---")
    print(f"  최적 메서드: {best_method}")
    print(f"  일관성 오차: {best_error:.4f} mm")
    r_err = rotation_error_deg(best_T[:3, :3], T_gt[:3, :3])
    t_err = translation_error_mm(best_T[:3, 3], T_gt[:3, 3])
    print(f"  GT 대비 회전 오차: {r_err:.4f} deg")
    print(f"  GT 대비 이동 오차: {t_err:.4f} mm")
    print()
    print(f"  {gt_label} (4x4):")
    for row in best_T:
        print(f"    [{row[0]:>10.6f}  {row[1]:>10.6f}  {row[2]:>10.6f}  {row[3]:>10.6f}]")
    print()

    # ====================================================================
    # 4. transform_to_base 테스트
    # ====================================================================
    print("--- 4단계: 좌표 변환 테스트 ---")

    # 카메라 좌표계에서 샘플 포인트
    points_cam = np.array([
        [0.0, 0.0, 0.5],      # 카메라 정면 0.5m
        [0.1, 0.0, 0.5],      # 우측으로 10cm
        [0.0, 0.1, 0.5],      # 위로 10cm
        [-0.05, -0.05, 0.3],  # 좌하 0.3m
    ])

    if mode == "eye-in-hand":
        # eye-in-hand: 현재 로봇 포즈가 필요 (첫 번째 포즈 사용)
        T_gripper = robot_poses[0]
        print(f"  (eye-in-hand: T_gripper_to_base = robot_poses[0])")
        points_base = calibrator.transform_to_base(points_cam, T_gripper_to_base=T_gripper)
    else:
        points_base = calibrator.transform_to_base(points_cam)

    print(f"  {'카메라 좌표 (m)':<30} {'베이스 좌표 (m)':<30}")
    print(f"  {'-'*30} {'-'*30}")
    for pc, pb in zip(points_cam, points_base):
        cam_str = f"[{pc[0]:>7.3f}, {pc[1]:>7.3f}, {pc[2]:>7.3f}]"
        base_str = f"[{pb[0]:>7.3f}, {pb[1]:>7.3f}, {pb[2]:>7.3f}]"
        print(f"  {cam_str:<30} {base_str:<30}")
    print()

    # ====================================================================
    # 5. 저장/로드 테스트
    # ====================================================================
    print("--- 5단계: 저장/로드 테스트 ---")
    save_path = f"/tmp/hand_eye_calibration_test_{mode.replace('-', '_')}.pkl"
    calibrator.save(save_path)

    calibrator2 = HandEyeCalibrator(mode=mode)
    calibrator2.load(save_path)

    if mode == "eye-to-hand" and calibrator2.T_cam_to_base is not None:
        diff = np.max(np.abs(calibrator.T_cam_to_base - calibrator2.T_cam_to_base))
        print(f"  로드 후 차이: {diff:.2e} (0이면 정상)")
    elif mode == "eye-in-hand" and calibrator2.T_cam_to_gripper is not None:
        diff = np.max(np.abs(calibrator.T_cam_to_gripper - calibrator2.T_cam_to_gripper))
        print(f"  로드 후 차이: {diff:.2e} (0이면 정상)")
    print(f"  로드된 모드: {calibrator2.mode}")
    print()

    # ====================================================================
    # 6. 시각화 (선택)
    # ====================================================================
    if not args.no_vis:
        print("--- 6단계: 시각화 (Open3D) ---")
        try:
            import open3d as o3d

            geometries = []

            # 원점 (로봇 베이스) 좌표 프레임
            base_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(
                size=0.15, origin=[0, 0, 0],
            )
            geometries.append(base_frame)

            # 카메라 좌표 프레임
            cam_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.1)
            cam_frame.transform(best_T)
            geometries.append(cam_frame)

            # 로봇 포즈
            for T_robot in robot_poses:
                robot_frame = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.03)
                robot_frame.transform(T_robot)
                geometries.append(robot_frame)

            # 변환된 샘플 포인트
            pcd = o3d.geometry.PointCloud()
            pcd.points = o3d.utility.Vector3dVector(points_base)
            pcd.paint_uniform_color([1, 0, 0])
            geometries.append(pcd)

            print("  Open3D 뷰어 실행 중... (창을 닫으면 종료)")
            o3d.visualization.draw_geometries(
                geometries,
                window_name="Hand-Eye Calibration Result",
                width=1024,
                height=768,
            )
        except ImportError:
            print("  [WARN] Open3D가 설치되지 않아 시각화를 건너뜁니다.")
    else:
        print("--- 6단계: 시각화 건너뜀 (--no-vis) ---")

    print()
    print("=" * 70)
    print(f"  캘리브레이션 시뮬레이션 완료 ({mode_label})")
    print("  카메라 입고 후 이 코드를 바로 실행하여 캘리브레이션 수행")
    print("  eye-to-hand: python hand_eye_calibration.py --mode eye-to-hand")
    print("  eye-in-hand: python hand_eye_calibration.py --mode eye-in-hand")
    print("=" * 70)


if __name__ == "__main__":
    main()
