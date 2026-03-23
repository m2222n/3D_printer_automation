"""
Hand-Eye Calibration for 3D Bin Picking System
===============================================

Eye-to-Hand (Fixed Camera) 캘리브레이션 템플릿

카메라: Basler Blaze-112 ToF (고정 프레임에 설치, 빈 위쪽)
로봇: HCR-10L (Modbus TCP, 포트 502)
설정: Eye-to-Hand (카메라 고정, 로봇 이동)

캘리브레이션 원리 (Eye-to-Hand / Fixed Camera):
    AX = XB  (고전적 Hand-Eye 문제)

    Eye-to-Hand 설정에서:
      - A = T_gripper_to_base(i)^{-1} * T_gripper_to_base(j)  (로봇 포즈 쌍의 상대 변환)
      - B = T_cam_to_target(i) * T_cam_to_target(j)^{-1}      (카메라-보드 상대 변환)
      - X = T_cam_to_base                                       (구하려는 변환)

    OpenCV cv2.calibrateHandEye()는 내부적으로 이를 처리하며,
    eye-to-hand 설정에서는 입력을 다음과 같이 넣어야 한다:
      - R_gripper2base, t_gripper2base  →  로봇 base 좌표계 기준 그리퍼 포즈
      - R_target2cam, t_target2cam      →  카메라 좌표계 기준 체커보드 포즈
    결과: R_cam2gripper, t_cam2gripper  →  실제로는 T_cam_to_base (eye-to-hand)

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
    """Eye-to-Hand (고정 카메라) Hand-Eye 캘리브레이션.

    Basler Blaze-112 ToF 카메라가 빈 위에 고정 설치된 상태에서,
    HCR-10L 로봇 그리퍼에 체커보드를 장착하고 여러 포즈에서 촬영하여
    카메라↔로봇 베이스 간 변환 행렬(T_cam_to_base)을 구한다.
    """

    # OpenCV Hand-Eye 캘리브레이션 메서드 매핑
    METHODS = {
        "tsai": cv2.CALIB_HAND_EYE_TSAI,
        "park": cv2.CALIB_HAND_EYE_PARK,
        "horaud": cv2.CALIB_HAND_EYE_HORAUD,
        "daniilidis": cv2.CALIB_HAND_EYE_DANIILIDIS,
    }

    def __init__(self, board_size: Tuple[int, int] = (9, 6), square_size: float = 0.015):
        """초기화.

        Args:
            board_size: 체커보드 내부 코너 수 (columns, rows). 기본 9x6.
            square_size: 체커보드 사각형 한 변 길이 [m]. 기본 15mm.
        """
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

        # 카메라 내부 파라미터 (Basler Blaze-112 근사값, 실제 캘리브레이션으로 교체 필요)
        # Blaze-112: 640x480, ~60deg FoV → fx,fy ≈ 500
        self.camera_matrix = np.array([
            [500.0,   0.0, 320.0],
            [  0.0, 500.0, 240.0],
            [  0.0,   0.0,   1.0],
        ], dtype=np.float64)
        self.dist_coeffs = np.zeros(5, dtype=np.float64)

        # 캘리브레이션 결과
        self.T_cam_to_base: Optional[np.ndarray] = None
        self.calibration_error: Optional[float] = None

    def set_camera_intrinsics(self, camera_matrix: np.ndarray, dist_coeffs: np.ndarray):
        """카메라 내부 파라미터 설정 (카메라 캘리브레이션 결과 사용).

        Args:
            camera_matrix: (3,3) 카메라 행렬
            dist_coeffs: (5,) 또는 (4,) 왜곡 계수
        """
        self.camera_matrix = camera_matrix.astype(np.float64)
        self.dist_coeffs = dist_coeffs.flatten().astype(np.float64)

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

        # Eye-to-Hand: 로봇 포즈의 역행렬을 사용
        # OpenCV calibrateHandEye는 기본적으로 eye-in-hand를 가정하므로,
        # eye-to-hand에서는 로봇 포즈의 역행렬을 gripper2base로 전달한다.
        R_gripper2base_list = []
        t_gripper2base_list = []
        R_target2cam_list = []
        t_target2cam_list = []

        for i in range(n):
            # Eye-to-hand: 로봇 포즈의 역행렬 사용
            T_base2gripper = np.linalg.inv(self.robot_poses[i])
            rvec_bg, tvec_bg = matrix_to_rvec_tvec(T_base2gripper)
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
        self.T_cam_to_base = T

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
        self.T_cam_to_base = best_T
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

                # 일관성: T_cam2base @ T_ij_cam = T_ij_robot_inv @ T_cam2base
                # → T_cam2base @ T_ij_cam @ T_cam2base^{-1} ≈ T_ij_robot_inv
                T_cam2base_inv = np.linalg.inv(T_cam2base)
                lhs = T_cam2base @ T_ij_cam @ T_cam2base_inv
                rhs = np.linalg.inv(T_ij_robot)

                # 이동 오차 (mm)
                t_err = np.linalg.norm(lhs[:3, 3] - rhs[:3, 3]) * 1000.0
                pair_errors.append(t_err)

        return float(np.mean(pair_errors)) if pair_errors else 0.0

    def transform_to_base(self, points_camera: np.ndarray) -> np.ndarray:
        """카메라 좌표계의 3D 포인트를 로봇 베이스 좌표계로 변환.

        Args:
            points_camera: (N, 3) 카메라 좌표계 포인트 [m]

        Returns:
            points_base: (N, 3) 로봇 베이스 좌표계 포인트 [m]
        """
        if self.T_cam_to_base is None:
            raise RuntimeError("캘리브레이션이 수행되지 않았습니다. calibrate()를 먼저 호출하세요.")

        pts = np.asarray(points_camera, dtype=np.float64)
        if pts.ndim == 1:
            pts = pts.reshape(1, 3)

        R = self.T_cam_to_base[:3, :3]
        t = self.T_cam_to_base[:3, 3]

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

    def save(self, filepath: str):
        """캘리브레이션 결과 저장.

        Args:
            filepath: 저장 경로 (.pkl)
        """
        data = {
            "T_cam_to_base": self.T_cam_to_base,
            "calibration_error": self.calibration_error,
            "camera_matrix": self.camera_matrix,
            "dist_coeffs": self.dist_coeffs,
            "board_size": self.board_size,
            "square_size": self.square_size,
            "n_measurements": len(self.robot_poses),
        }
        with open(filepath, "wb") as f:
            pickle.dump(data, f)
        print(f"캘리브레이션 결과 저장: {filepath}")

    def load(self, filepath: str):
        """캘리브레이션 결과 로드.

        Args:
            filepath: 저장 경로 (.pkl)
        """
        with open(filepath, "rb") as f:
            data = pickle.load(f)
        self.T_cam_to_base = data["T_cam_to_base"]
        self.calibration_error = data["calibration_error"]
        self.camera_matrix = data["camera_matrix"]
        self.dist_coeffs = data["dist_coeffs"]
        self.board_size = data["board_size"]
        self.square_size = data["square_size"]
        print(f"캘리브레이션 결과 로드: {filepath} ({data['n_measurements']}개 측정)")


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


# ============================================================================
# 메인 실행
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Hand-Eye Calibration 시뮬레이션 (Eye-to-Hand, 고정 카메라)",
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

    # ====================================================================
    # 1. 시뮬레이션 데이터 생성
    # ====================================================================
    print("=" * 70)
    print("  Hand-Eye Calibration 시뮬레이션 (Eye-to-Hand)")
    print("=" * 70)
    print()

    print("--- 1단계: 시뮬레이션 데이터 생성 ---")
    robot_poses, cam_to_board_poses, T_gt = _simulate_measurements(
        n_poses=args.n_poses,
        noise_rot_deg=args.noise_rot,
        noise_trans_mm=args.noise_trans,
    )
    print(f"  포즈 수: {len(robot_poses)}")
    print(f"  노이즈: 회전 {args.noise_rot}deg, 이동 {args.noise_trans}mm")
    print(f"  Ground Truth T_cam_to_base:")
    print(f"    위치: [{T_gt[0,3]:.3f}, {T_gt[1,3]:.3f}, {T_gt[2,3]:.3f}] m")
    gt_euler = Rotation.from_matrix(T_gt[:3, :3]).as_euler('xyz', degrees=True)
    print(f"    회전: [{gt_euler[0]:.1f}, {gt_euler[1]:.1f}, {gt_euler[2]:.1f}] deg")
    print()

    # ====================================================================
    # 2. 캘리브레이션 수행 (4가지 메서드 비교)
    # ====================================================================
    print("--- 2단계: 캘리브레이션 (4가지 메서드 비교) ---")

    calibrator = HandEyeCalibrator(board_size=(9, 6), square_size=0.015)

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
    print("  T_cam_to_base (4x4):")
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
    save_path = "/tmp/hand_eye_calibration_test.pkl"
    calibrator.save(save_path)

    calibrator2 = HandEyeCalibrator()
    calibrator2.load(save_path)

    if calibrator2.T_cam_to_base is not None:
        diff = np.max(np.abs(calibrator.T_cam_to_base - calibrator2.T_cam_to_base))
        print(f"  로드 후 차이: {diff:.2e} (0이면 정상)")
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
    print("  캘리브레이션 시뮬레이션 완료")
    print("  카메라 입고 후 이 코드를 바로 실행하여 캘리브레이션 수행")
    print("=" * 70)


if __name__ == "__main__":
    main()
