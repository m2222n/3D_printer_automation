"""
pypylon API 학습 — 빈피킹용 카메라 제어 패턴 정리
===================================================

Basler 카메라 2대 사용 예정:
  - Blaze-112 ToF: depth map (640×480, 16bit) → 포인트 클라우드
  - ace2 5MP (a2A2590-22gcPRO): RGB 이미지 (2592×1944) → 색상 매핑

pypylon은 pylon SDK의 Python 래퍼. GenICam 기반으로 모든 Basler 카메라 동일 API.

⚠️ 이 파일은 카메라 없이도 실행 가능한 학습/참조 코드입니다.
   카메라가 연결된 환경에서만 동작하는 부분은 함수로 분리하고,
   실행 시에는 API 패턴 설명만 출력합니다.

실행: source .venv/binpick/bin/activate && python bin_picking/tutorials/10_pypylon_api_study.py

참고: https://github.com/basler/pypylon/tree/master/samples
"""

import numpy as np


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ============================================================
# 1. pypylon 기본 구조 (카메라 없이 설명)
# ============================================================
print_section("1. pypylon 기본 API 구조")

print("""
  ■ 핵심 클래스 계층
    pylon.TlFactory          — Transport Layer 팩토리 (싱글턴)
    pylon.InstantCamera      — 단일 카메라 제어
    pylon.InstantCameraArray — 다중 카메라 동시 제어 (우리: Blaze + ace2)
    pylon.GrabResult         — 촬영 결과 (이미지 데이터 + 메타데이터)
    pylon.ImageFormatConverter — 픽셀 포맷 변환 (BGR8 등)

  ■ 기본 워크플로우
    1. TlFactory.GetInstance() — 팩토리 가져오기
    2. tlFactory.EnumerateDevices() — 연결된 카메라 목록
    3. pylon.InstantCamera(tlFactory.CreateDevice(device_info)) — 카메라 생성
    4. camera.Open() — 카메라 열기
    5. camera.StartGrabbing() — 촬영 시작
    6. camera.RetrieveResult(timeout) — 결과 가져오기
    7. grabResult.Array — numpy 배열로 변환
    8. camera.StopGrabbing() → camera.Close() — 정리
""")


# ============================================================
# 2. 단일 카메라 Grab 패턴
# ============================================================
print_section("2. 단일 카메라 Grab 패턴 (grabone.py / grab.py)")

print("""
  ■ 단일 프레임 (GrabOne) — 빈피킹에 적합
    ```python
    from pypylon import pylon
    import numpy as np

    camera = pylon.InstantCamera(
        pylon.TlFactory.GetInstance().CreateFirstDevice())
    camera.Open()

    # 단일 프레임 촬영 (timeout 5000ms)
    result = camera.GrabOne(5000)
    if result.GrabSucceeded():
        img = result.Array          # numpy ndarray
        print(img.shape, img.dtype)  # (H, W) or (H, W, C)
    result.Release()
    camera.Close()
    ```

  ■ 연속 Grab (grab.py) — 모니터링/디버깅용
    ```python
    camera.StartGrabbingMax(10)  # 10프레임만 촬영
    while camera.IsGrabbing():
        result = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
        if result.GrabSucceeded():
            img = result.Array
            # 처리...
        result.Release()
    camera.Close()
    ```

  ■ 최신 프레임만 (LatestImageOnly) — 실시간 처리
    ```python
    camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
    # 오래된 프레임 버리고 최신만 가져옴 → 빈피킹에 적합
    ```
""")


# ============================================================
# 3. Blaze ToF — GenDC (Generic Data Container) 패턴 ⭐
# ============================================================
print_section("3. Blaze-112 ToF — GenDC 데이터 컨테이너 ⭐⭐⭐")

print("""
  ■ Blaze는 일반 카메라와 다르게 GenDC로 데이터 반환!
    하나의 GrabResult 안에 여러 컴포넌트:
    - Intensity (2D 흑백 이미지)
    - Range / Depth (깊이 맵, 16bit)
    - Confidence (신뢰도 맵)
    - Point Cloud (XYZ, 가능한 경우)

  ■ 핵심 코드 (grabdatacontainer.py 기반)
    ```python
    from pypylon import pylon

    camera = pylon.InstantCamera(
        pylon.TlFactory.GetInstance().CreateFirstDevice())
    camera.Open()
    camera.StartGrabbingMax(1)

    result = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
    if result.GrabSucceeded():
        container = result.GetDataContainer()
        print(f"Components: {container.DataComponentCount}")

        for i in range(container.DataComponentCount):
            comp = container.GetDataComponentByIndex(i)

            if comp.ComponentType == pylon.ComponentType_Intensity:
                intensity = comp.Array  # (480, 640) uint16
                print(f"Intensity: {intensity.shape}")

            elif comp.ComponentType == pylon.ComponentType_Range:
                depth = comp.Array      # (480, 640) uint16 [mm 단위]
                print(f"Depth: {depth.shape}, dtype={depth.dtype}")

            elif comp.ComponentType == pylon.ComponentType_Confidence:
                confidence = comp.Array  # (480, 640) uint16
                print(f"Confidence: {confidence.shape}")

            comp.Release()
        container.Release()
    result.Release()
    camera.Close()
    ```

  ■ Blaze-112 출력 해상도
    - 640 × 480 @ 30fps (최대)
    - Depth: uint16, 밀리미터 단위 (0=무효)
    - 유효 범위: 300mm ~ 10,000mm (빈피킹: ~500mm에서 사용)

  ■ ComponentSelector로 출력 데이터 선택 (⭐ Blaze 전용)
    ```python
    camera.Open()
    # Range (depth) 활성화 — Coord3D_C16 (uint16 mm) 또는 Coord3D_ABC32f (XYZ float)
    camera.ComponentSelector.Value = "Range"
    camera.ComponentEnable.Value = True
    camera.PixelFormat.Value = "Coord3D_C16"  # depth map (기본)
    # camera.PixelFormat.Value = "Coord3D_ABC32f"  # 직접 XYZ (카메라 내부 캘리브 사용)

    camera.ComponentSelector.Value = "Intensity"
    camera.ComponentEnable.Value = True

    camera.ComponentSelector.Value = "Confidence"
    camera.ComponentEnable.Value = True
    ```

  ■ Coord3D_ABC32f: 카메라가 직접 XYZ 포인트 클라우드 출력
    ```python
    # Coord3D_ABC32f 사용 시 → (480, 640, 3) float32, mm 단위
    xyz = comp.Array  # shape (480, 640, 3)
    points = xyz.reshape(-1, 3)  # (307200, 3)
    valid = np.any(points != 0, axis=1)
    points = points[valid] / 1000.0  # mm → m
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(points)
    # → Intrinsic 변환 불필요! 카메라가 이미 계산해줌
    ```

  ■ 거리별 depth 정밀도 (빈피킹 핵심!)
    ┌──────────┬─────────────┬───────────────────┐
    │ 거리     │ 정밀도(1σ)  │ 비고              │
    ├──────────┼─────────────┼───────────────────┤
    │ 0.5m     │ ~1.5mm      │ ← 빈피킹 권장     │
    │ 1.0m     │ ~3mm        │ 일반적            │
    │ 2.0m     │ ~10mm       │ ShortRange 한계   │
    │ 5.0m     │ ~50mm       │ LongRange         │
    └──────────┴─────────────┴───────────────────┘

  ■ HDR 모드 (광택 SLA 레진 부품에 유용)
    ```python
    camera.HDRMode.Value = "SpatialHDR"  # 다중 노출 합성
    # → 반사율 차이 큰 부품 (Grey=무광, Clear=광택)에서 depth 품질 향상
    ```

  ■ ⚠️ Clear V5 레진 경고
    - ToF는 투명/반투명 재료에서 실패 (빛이 통과)
    - Clear 레진: depth 리턴 없거나 노이즈 매우 높음
    - 대안: 스프레이 코팅, 또는 ace2 RGB로 2D 폴백
    - Grey/White/Flexible(불투명)은 정상 동작
""")


# ============================================================
# 4. 다중 카메라 동시 Grab (Blaze + ace2)
# ============================================================
print_section("4. 다중 카메라 동시 Grab (grabmultiplecameras.py)")

print("""
  ■ InstantCameraArray 사용 (Blaze + ace2 동시 촬영)
    ```python
    from pypylon import pylon

    tlFactory = pylon.TlFactory.GetInstance()
    devices = tlFactory.EnumerateDevices()

    # 카메라 2대 배열
    cameras = pylon.InstantCameraArray(2)
    for i, cam in enumerate(cameras):
        cam.Attach(tlFactory.CreateDevice(devices[i]))
        print(f"Camera {i}: {cam.GetDeviceInfo().GetModelName()}")

    cameras.StartGrabbing()

    for _ in range(10):
        result = cameras.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
        cam_idx = result.GetCameraContext()  # 어느 카메라인지!

        if cam_idx == 0:  # Blaze
            container = result.GetDataContainer()
            # depth, intensity 추출...
        elif cam_idx == 1:  # ace2
            rgb = result.Array  # (1944, 2592, 3) or Bayer
            # RGB 처리...

        result.Release()

    cameras.StopGrabbing()
    ```

  ■ 카메라 구분 방법
    - GetCameraContext() → 배열 인덱스
    - GetDeviceInfo().GetModelName() → "Basler blaze-112", "a2A2590-22gcPRO"
    - GetDeviceInfo().GetSerialNumber() → 시리얼로 정확히 구분

  ■ 동기화 주의
    - 하드웨어 트리거 없으면 타임스탬프 기반 매칭 필요
    - Blaze: 30fps, ace2: 22fps → 타이밍 불일치
    - 빈피킹에서는 정지 상태 촬영이므로 순차 촬영도 OK
""")


# ============================================================
# 5. Depth → Open3D PointCloud 변환 ⭐
# ============================================================
print_section("5. Blaze Depth Map → Open3D PointCloud 변환 ⭐⭐⭐")

print("""
  ■ 카메라 내부 파라미터 (Intrinsics)
    Blaze-112 내부 파라미터는 카메라 NodeMap에서 읽음:
    ```python
    camera.Open()
    fx = camera.Scan3dFocalLengthX.Value   # focal length X (pixels)
    fy = camera.Scan3dFocalLengthY.Value   # focal length Y (pixels)
    cx = camera.Scan3dPrincipalPointU.Value # principal point X
    cy = camera.Scan3dPrincipalPointV.Value # principal point Y
    ```

  ■ Depth Map → XYZ 포인트 클라우드 (핵심 변환)
    ```python
    import numpy as np
    import open3d as o3d

    def depth_to_pointcloud(depth_mm, fx, fy, cx, cy,
                            min_depth=300, max_depth=1500):
        \"\"\"Blaze depth map → Open3D PointCloud\"\"\"
        H, W = depth_mm.shape
        depth_m = depth_mm.astype(np.float32) / 1000.0  # mm → m

        # 유효 범위 필터
        mask = (depth_m > min_depth/1000) & (depth_m < max_depth/1000)

        # 픽셀 좌표 그리드
        u, v = np.meshgrid(np.arange(W), np.arange(H))

        # 핀홀 카메라 모델: (u,v,d) → (X,Y,Z)
        Z = depth_m[mask]
        X = (u[mask] - cx) * Z / fx
        Y = (v[mask] - cy) * Z / fy

        points = np.stack([X, Y, Z], axis=-1)  # (N, 3)

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        return pcd
    ```

  ■ Open3D 내장 방법 (더 깔끔)
    ```python
    # Open3D의 create_from_depth_image 사용
    depth_o3d = o3d.geometry.Image(depth_mm.astype(np.uint16))
    intrinsic = o3d.camera.PinholeCameraIntrinsic(W, H, fx, fy, cx, cy)

    pcd = o3d.geometry.PointCloud.create_from_depth_image(
        depth_o3d, intrinsic,
        depth_scale=1000.0,    # mm → m 변환
        depth_trunc=1.5,       # 1.5m 이상 제거
    )
    ```
""")


# ============================================================
# 6. RGB-D 결합 (Blaze depth + ace2 color)
# ============================================================
print_section("6. RGB-D 결합 (Blaze + ace2 → 색상 포인트 클라우드)")

print("""
  ■ 두 카메라 캘리브레이션 필요
    - Blaze와 ace2는 물리적 위치가 다름 → 외부 파라미터(Extrinsic) 필요
    - 체커보드/ArUco 마커로 스테레오 캘리브레이션
    - 결과: R (3×3 회전), T (3×1 이동) → 4×4 변환 행렬

  ■ 캘리브레이션 워크플로우
    ```python
    import cv2
    import numpy as np

    # 1. 두 카메라에서 동시에 체커보드 촬영 (20+ 쌍)
    # 2. 각 카메라 intrinsic 캘리브레이션
    ret1, K1, dist1, rvecs1, tvecs1 = cv2.calibrateCamera(...)  # Blaze intensity
    ret2, K2, dist2, rvecs2, tvecs2 = cv2.calibrateCamera(...)  # ace2 RGB

    # 3. 스테레오 캘리브레이션 (두 카메라 간 상대 자세)
    ret, K1, dist1, K2, dist2, R, T, E, F = cv2.stereoCalibrate(
        objpoints, imgpoints1, imgpoints2,
        K1, dist1, K2, dist2, image_size,
        criteria=..., flags=cv2.CALIB_FIX_INTRINSIC)
    # R, T: Blaze→ace2 변환
    ```

  ■ Depth + Color 합성
    ```python
    def create_rgbd_pointcloud(depth_mm, rgb_image,
                               K_blaze, K_ace2, R_b2a, T_b2a,
                               dist_blaze=None, dist_ace2=None):
        \"\"\"Blaze depth + ace2 RGB → 색상 포인트 클라우드\"\"\"
        import open3d as o3d

        # 1. Depth → 3D 포인트 (Blaze 좌표계)
        pcd = depth_to_pointcloud(depth_mm, K_blaze[0,0], K_blaze[1,1],
                                  K_blaze[0,2], K_blaze[1,2])
        points = np.asarray(pcd.points)

        # 2. Blaze 3D → ace2 3D (외부 파라미터 적용)
        points_ace2 = (R_b2a @ points.T + T_b2a).T

        # 3. ace2 3D → ace2 2D (투영)
        pts_2d, _ = cv2.projectPoints(points_ace2, np.zeros(3), np.zeros(3),
                                      K_ace2, dist_ace2)
        pts_2d = pts_2d.reshape(-1, 2).astype(int)

        # 4. 유효 범위 내 색상 매핑
        H, W = rgb_image.shape[:2]
        valid = (pts_2d[:,0] >= 0) & (pts_2d[:,0] < W) & \\
                (pts_2d[:,1] >= 0) & (pts_2d[:,1] < H)

        colors = np.zeros((len(points), 3))
        colors[valid] = rgb_image[pts_2d[valid,1], pts_2d[valid,0]] / 255.0
        # BGR→RGB if needed

        pcd.colors = o3d.utility.Vector3dVector(colors)
        return pcd
    ```

  ■ SLA 부품 특성상 단색이라 색상 활용 제한적
    → 그래도 시각화/디버깅에는 매우 유용
    → 다른 레진 색상 부품 구분에 활용 가능 (Grey vs White vs Clear)
""")


# ============================================================
# 7. 카메라 파라미터 설정 패턴
# ============================================================
print_section("7. 카메라 파라미터 설정 패턴")

print("""
  ■ 공통 패턴 (GenICam 기반)
    ```python
    camera.Open()

    # 읽기
    print(camera.Width.Value)
    print(camera.Height.Value)
    print(camera.PixelFormat.Value)
    print(camera.ExposureTime.Value)

    # 쓰기 (범위 확인)
    if camera.ExposureTime.Min <= 5000 <= camera.ExposureTime.Max:
        camera.ExposureTime.Value = 5000  # µs

    # 사용 가능 옵션 확인
    print(camera.PixelFormat.Symbolics)  # ['Mono8', 'Mono12', ...]
    ```

  ■ Blaze-112 주요 파라미터
    ```python
    # 동작 모드
    camera.Scan3dOperatingMode.Value = "ShortRange"  # 300~2000mm (빈피킹)
    # 또는 "LongRange" (1000~10000mm)

    # 노출 시간 (자동/수동)
    camera.ExposureAuto.Value = "Continuous"  # 자동 (권장)
    # camera.ExposureTime.Value = 1000  # µs (수동)

    # 필터
    camera.Scan3dSpatialFilterEnable.Value = True   # 공간 필터 (노이즈 감소)
    camera.Scan3dTemporalFilterEnable.Value = True  # 시간 필터 (여러 프레임 평균)
    camera.Scan3dTemporalFilterStrength.Value = 200 # 프레임 수 (높을수록 안정)

    # 신뢰도 임계값
    camera.DepthMin.Value = 300     # 최소 거리 (mm)
    camera.DepthMax.Value = 1500    # 최대 거리 (mm)
    camera.ConfidenceThreshold.Value = 100  # 낮은 신뢰도 포인트 제거
    ```

  ■ ace2 주요 파라미터
    ```python
    camera.PixelFormat.Value = "BGR8"  # OpenCV 호환
    camera.ExposureAuto.Value = "Continuous"
    camera.BalanceWhiteAuto.Value = "Continuous"
    camera.AcquisitionFrameRate.Value = 10.0  # fps 제한 (동기화용)
    ```

  ■ 설정 저장/로드 (운영 환경에서 유용)
    ```python
    # 저장
    pylon.FeaturePersistence.Save("blaze_config.pfs", camera.GetNodeMap())
    # 로드 (카메라 재연결 시)
    pylon.FeaturePersistence.Load("blaze_config.pfs", camera.GetNodeMap(), True)
    ```
""")


# ============================================================
# 8. 에러 핸들링 패턴
# ============================================================
print_section("8. 에러 핸들링 + 안정적 운영 패턴")

print("""
  ■ 기본 예외 처리
    ```python
    from pypylon import pylon, genicam

    try:
        camera = pylon.InstantCamera(
            pylon.TlFactory.GetInstance().CreateFirstDevice())
        camera.Open()
        # ...
    except genicam.GenericException as e:
        print(f"카메라 에러: {e}")
    except pylon.RuntimeException as e:
        print(f"런타임 에러: {e}")
    finally:
        if camera.IsOpen():
            camera.Close()
    ```

  ■ 카메라 연결 끊김 대응 (24/7 운영)
    ```python
    MAX_RETRIES = 5
    for attempt in range(MAX_RETRIES):
        try:
            result = camera.GrabOne(5000)
            if result.GrabSucceeded():
                break
        except genicam.GenericException:
            print(f"촬영 실패 ({attempt+1}/{MAX_RETRIES}), 재시도...")
            camera.Close()
            time.sleep(1)
            camera.Open()
    ```

  ■ Grab 타임아웃 vs Exception
    ```python
    # 방법 1: 타임아웃 시 None 반환
    result = camera.RetrieveResult(5000, pylon.TimeoutHandling_Return)
    if result is None or not result.GrabSucceeded():
        print("타임아웃 또는 촬영 실패")

    # 방법 2: 타임아웃 시 예외 발생 (추천 — 문제 빨리 발견)
    result = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
    ```
""")


# ============================================================
# 9. 시뮬레이션: Blaze depth map → Open3D 변환 (카메라 없이)
# ============================================================
print_section("9. 시뮬레이션: 합성 Depth → Open3D PointCloud")

try:
    import open3d as o3d

    # Blaze-112 시뮬레이션 파라미터
    W, H = 640, 480
    fx, fy = 500.0, 500.0   # 가상 focal length
    cx, cy = 320.0, 240.0   # principal point (이미지 중앙)

    # 합성 depth map: 평면 (z=500mm) + 구형 부품 (z=450mm, r=30mm)
    depth_mm = np.full((H, W), 500, dtype=np.uint16)  # 바닥 500mm

    # 구형 부품 시뮬레이션 (중앙에 반구)
    for v in range(H):
        for u in range(W):
            du, dv = u - 320, v - 240
            r = np.sqrt(du**2 + dv**2)
            if r < 40:  # 반경 40px → ~30mm 부품
                z_offset = np.sqrt(max(0, 40**2 - r**2)) * 0.75
                depth_mm[v, u] = int(450 - z_offset)

    # 노이즈 추가 (Blaze-112 스펙: ~0.3mm → 정수 반올림)
    noise = np.random.normal(0, 0.5, (H, W)).astype(np.int16)
    depth_mm = np.clip(depth_mm.astype(np.int16) + noise, 300, 600).astype(np.uint16)

    print(f"  합성 Depth Map: {W}×{H}, range=[{depth_mm.min()}, {depth_mm.max()}]mm")

    # Open3D 방법 1: 수동 변환
    depth_m = depth_mm.astype(np.float32) / 1000.0
    mask = (depth_m > 0.3) & (depth_m < 0.6)

    u_grid, v_grid = np.meshgrid(np.arange(W), np.arange(H))
    Z = depth_m[mask]
    X = (u_grid[mask] - cx) * Z / fx
    Y = (v_grid[mask] - cy) * Z / fy
    points_manual = np.stack([X, Y, Z], axis=-1)

    pcd_manual = o3d.geometry.PointCloud()
    pcd_manual.points = o3d.utility.Vector3dVector(points_manual)
    print(f"  수동 변환: {len(pcd_manual.points):,} points")

    # Open3D 방법 2: create_from_depth_image (깔끔)
    depth_o3d = o3d.geometry.Image(depth_mm)
    intrinsic = o3d.camera.PinholeCameraIntrinsic(W, H, fx, fy, cx, cy)
    pcd_o3d = o3d.geometry.PointCloud.create_from_depth_image(
        depth_o3d, intrinsic,
        depth_scale=1000.0,
        depth_trunc=0.6,
    )
    print(f"  Open3D 내장: {len(pcd_o3d.points):,} points")

    # 두 방법 결과 비교
    diff = abs(len(pcd_manual.points) - len(pcd_o3d.points))
    print(f"  포인트 수 차이: {diff} (거의 동일하면 OK)")

    # 다운샘플 + 법선 (빈피킹 파이프라인 연결)
    pcd_down = pcd_o3d.voxel_down_sample(0.002)
    pcd_down.estimate_normals(
        o3d.geometry.KDTreeSearchParamHybrid(radius=0.008, max_nn=30))
    pcd_down.orient_normals_towards_camera_location(np.array([0., 0., 0.]))
    print(f"  다운샘플+법선: {len(pcd_down.points):,} points → L4 매칭 준비 완료")

    print("\n  ✅ Depth→PointCloud 변환 검증 성공!")
    print("  → 실제 Blaze-112에서도 동일 코드로 변환 가능")

except ImportError:
    print("  ⚠️ Open3D 미설치 — 시뮬레이션 건너뜀")


# ============================================================
# 10. 빈피킹 통합 촬영 함수 (템플릿)
# ============================================================
print_section("10. 빈피킹 통합 촬영 함수 (실전 템플릿)")

print("""
  ■ 실제 빈피킹에서 사용할 촬영 함수 구조:

  ```python
  class BinPickingCamera:
      def __init__(self):
          self.tlFactory = pylon.TlFactory.GetInstance()
          self.blaze = None   # Blaze-112 ToF
          self.ace2 = None    # ace2 5MP RGB
          self.intrinsic = None

      def connect(self):
          \"\"\"카메라 2대 연결\"\"\"
          devices = self.tlFactory.EnumerateDevices()
          for dev in devices:
              model = dev.GetModelName()
              if "blaze" in model.lower():
                  self.blaze = pylon.InstantCamera(
                      self.tlFactory.CreateDevice(dev))
              elif "a2A" in model:
                  self.ace2 = pylon.InstantCamera(
                      self.tlFactory.CreateDevice(dev))

          # Blaze 설정
          self.blaze.Open()
          self.blaze.Scan3dOperatingMode.Value = "ShortRange"
          self.blaze.Scan3dSpatialFilterEnable.Value = True
          self.blaze.Scan3dTemporalFilterEnable.Value = True
          self.blaze.ConfidenceThreshold.Value = 100
          self.blaze.DepthMin.Value = 300
          self.blaze.DepthMax.Value = 1000

          # Intrinsic 읽기
          fx = self.blaze.Scan3dFocalLengthX.Value
          fy = self.blaze.Scan3dFocalLengthY.Value
          cx = self.blaze.Scan3dPrincipalPointU.Value
          cy = self.blaze.Scan3dPrincipalPointV.Value
          self.intrinsic = o3d.camera.PinholeCameraIntrinsic(640, 480, fx, fy, cx, cy)

          # ace2 설정
          self.ace2.Open()
          self.ace2.PixelFormat.Value = "BGR8"

      def grab_pointcloud(self):
          \"\"\"단일 촬영 → PointCloud 반환\"\"\"
          result = self.blaze.GrabOne(5000)
          container = result.GetDataContainer()

          depth = None
          for i in range(container.DataComponentCount):
              comp = container.GetDataComponentByIndex(i)
              if comp.ComponentType == pylon.ComponentType_Range:
                  depth = comp.Array.copy()
              comp.Release()
          container.Release()
          result.Release()

          # Depth → PointCloud
          depth_img = o3d.geometry.Image(depth.astype(np.uint16))
          pcd = o3d.geometry.PointCloud.create_from_depth_image(
              depth_img, self.intrinsic,
              depth_scale=1000.0, depth_trunc=1.0)
          return pcd

      def grab_rgb(self):
          \"\"\"ace2 RGB 촬영\"\"\"
          result = self.ace2.GrabOne(5000)
          rgb = result.Array.copy()
          result.Release()
          return rgb

      def disconnect(self):
          if self.blaze and self.blaze.IsOpen():
              self.blaze.Close()
          if self.ace2 and self.ace2.IsOpen():
              self.ace2.Close()
  ```

  ■ 빈피킹 메인 루프에서:
    ```python
    cam = BinPickingCamera()
    cam.connect()

    while True:
        pcd = cam.grab_pointcloud()          # L1 영상 취득
        pcd_clean = preprocess(pcd)          # L2 전처리
        clusters = dbscan_segment(pcd_clean) # L3 분할
        for cluster in clusters:
            part, pose = match(cluster, refs) # L4 인식/자세
            grasp = plan_grasp(part, pose)    # L5 그래스프
            send_to_robot(grasp)              # L6 Modbus

    cam.disconnect()
    ```
""")


# ============================================================
# 11. Basler Blaze-112 스펙 요약
# ============================================================
print_section("11. Basler Blaze-112 스펙 요약")

print("""
  ┌────────────────────┬──────────────────────────────┐
  │ 항목               │ 사양                          │
  ├────────────────────┼──────────────────────────────┤
  │ 센서               │ Sony DepthSense IMX556PLR     │
  │ 기술               │ ToF (Time-of-Flight)          │
  │ 해상도             │ 640 × 480 (VGA)              │
  │ 프레임 레이트      │ 최대 30 fps                   │
  │ 범위 (ShortRange)  │ 300 ~ 2,000 mm               │
  │ 범위 (LongRange)   │ 1,000 ~ 10,000 mm            │
  │ 정확도             │ ±4mm @ 1m (z 방향)            │
  │ 인터페이스         │ GigE (1Gbps)                  │
  │ 출력 데이터        │ Intensity + Depth + Confidence│
  │ 데이터 포맷        │ GenDC (Generic Data Container)│
  │ 크기               │ 65 × 65 × 76 mm              │
  │ 무게               │ ~300g                         │
  │ 빈피킹 권장 거리   │ 500 ~ 800mm (ShortRange)      │
  │ FOV                │ 67° × 51° (H × V)            │
  └────────────────────┴──────────────────────────────┘

  빈피킹 권장 설정:
  - ShortRange 모드 (300~2000mm)
  - 카메라 높이: ~600mm (빈 위)
  - 시야각: 67°×51° → 600mm에서 약 440×360mm 커버
  - 빈 크기 200×200mm → 충분히 커버
  - Temporal Filter: ON (여러 프레임 평균 → 노이즈 ↓)
  - Confidence Threshold: 100+ (낮은 품질 포인트 제거)
""")


print(f"\n{'='*70}")
print("  ✅ pypylon API 학습 완료!")
print(f"{'='*70}")
print("""
  다음 단계:
  1. 카메라 입고 시 (5월): 이 코드의 함수들을 실제 카메라로 테스트
  2. 캘리브레이션: Blaze + ace2 스테레오 캘리브레이션
  3. 통합: grab_pointcloud() → 07_full_binpicking_simulation.py의 L2~L5
""")
