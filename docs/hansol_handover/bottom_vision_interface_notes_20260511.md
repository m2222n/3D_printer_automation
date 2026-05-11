# 한솔 바텀비전 인터페이스 명세 (2026-05-11 스냅샷)

> **목적**: 한솔코에버가 5/7 공유한 `Flicdern_v3` 소스코드에서 **우리 빈피킹과 통합 시 필요한 인터페이스 정보**만 추출.
>
> **원칙**:
> - 변경 X — 한솔이 담당하는 영역, 우리가 수정하지 않음
> - 알고리즘 학습 X — 필요한 시점에 원본 소스 재확인
> - 인터페이스만 ✅ — Modbus 맵, 좌표 형식, 단위, 핸드셰이크 등 통합 시 충돌 가능 지점
>
> **출처 자료** (영구 보관: `~/hansol_handover/bottom_vision_20260507/`):
> - `Flicdern_v3/flicdern/modbus_robot.py` (Modbus TCP 송신부)
> - `Flicdern_v3/flicdern/hole_detect.py` (메인 + CLI 인자)
> - `Flicdern_v3/flicdern/camera/rayple_camera.py` (iRayple SDK 래퍼)
> - `Flicdern_v3/iraypl_sdk 설치방법.docx` (SDK 설치 가이드, 예승님 직접 작성)
>
> **스냅샷 시점 가정**: 한솔 코드는 향후 변경될 수 있음. 통합 시점에 원본 소스 다시 확인 필수.

---

## 1. Modbus TCP 인터페이스 (가장 중요)

### 1.1 레지스터 맵 (Holding Registers, 0-base)

| 주소 | R/W | 의미 | 크기 | 비고 |
|------|-----|------|------|------|
| **HR0** | W (비전) / R (로봇) | `vision_data_ready` (0/1) | 16bit | 비전이 1로 올리면 데이터 유효 |
| **HR1** | W (비전) / R (로봇) | `hole_count` (0~20) | 16bit | 검출된 홀 개수 |
| **HR2~HR41** | W (비전) / R (로봇) | (x0,y0)~(x19,y19) | 16bit × 40 | uint16 픽셀, 최대 20개 홀 |
| **HR42** | W (로봇) / R (비전) | `robot_ack` (0/1) | 16bit | 로봇이 1로 올리면 수신 확인 |

상수 정의 위치: `Flicdern_v3/flicdern/modbus_robot.py` (`REG_VISION_DATA_READY=0`, `REG_HOLE_COUNT=1`, `REG_COORDS_START=2`, `MAX_HOLES=20`, `REG_ROBOT_ACK_DEFAULT=42`)

### 1.2 좌표 인코딩

| 항목 | 값 | 비고 |
|------|-----|------|
| 데이터 타입 | uint16 (0~65535) | `_to_u16()` 함수에서 음수→0, 65535+→65535 클램프 |
| 단위 | **픽셀** (정수 반올림) | `cv2.moments`로 검출된 무게중심 픽셀 좌표 |
| mm 변환 | CLI `--mm-per-pixel` 옵션 | 한솔이 IPC-510에서 어떻게 캘리브하는지 미확인 |
| 좌표계 | **카메라 이미지 좌표** (x: 오른쪽+, y: 아래+) | OpenCV 표준, 로봇 base 좌표계 X |
| 정렬 | 좌→우 (x 오름차순), tie-break y 오름차순 | 펜던트가 순서대로 처리 가정 |

⚠️ **회전각/방향 정보 없음** — 홀 중심 좌표만 송신. 부품 자체 자세는 별도 (contour_template_matcher.py 영역, Modbus 송신 안 함)

⚠️ **부품 ID 없음** — 모든 홀이 동일 클래스로 취급됨. 다종 부품 처리는 펜던트가 책임지는 것으로 추정

### 1.3 핸드셰이크 시퀀스 (8단계)

비전 PC (Modbus 클라이언트, pymodbus 3.x):

```
1. 좌표 정렬 (x, y)  # 클라이언트 측 sort_holes_left_to_right
2. hole_count + 20개 좌표 슬롯 구성 (부족분 0)
3. HR0 = 0          # vision_data_ready clear
4. HR1~HR41 한 번에 쓰기 (write_registers, 41 워드)
5. HR0 = 1          # data ready
6. HR42 폴링        # 50ms 간격, 30초 timeout
   ↑
   여기서 로봇이 데이터 읽고 HR42 = 1
   ↓
7. (ack 수신 후) HR0 = 0  # cycle complete
8. 연결 close
```

타임아웃: 30초 (`ack_timeout_sec=30.0`). 폴링 간격: 50ms (`ack_poll_interval_sec=0.05`).

---

## 2. 알고리즘 개요 (간략 — 깊은 학습은 통합 시점에)

### 2.1 홀 검출 (`hole_detect.py`)
- 입력: BGR 이미지 (iRayple 또는 BMP 파일)
- 전처리: Otsu 이진화 → morphology close/open
- 핵심 트릭: `cv2.RETR_CCOMP` + hierarchy parent 체크 → 부품 내부 구멍만 추출
- 필터: 원형도 (`4π·A/P²` ≥ 0.65) + 면적 범위 (mm 직경 기반 또는 픽셀 직접)
- 출력: 홀 중심 (cx, cy) 픽셀 좌표 리스트 + 면적/원형도

### 2.2 부품 분류 (`contour_template_matcher.py`)
- 입력: BGR 이미지
- 알고리즘: 외곽 컨투어 → `cv2.matchShapes` (Hu Moments) → 1도 단위 IoU sweep으로 회전각 추정
- 출력: (class_id, x, y, theta_deg, score)
- 현재 templates.json: **1종만 등록** (class_id=7) — 한솔 측 prototype 단계

⚠️ **분류는 Modbus 송신하지 않음** — `hole_detect.py`만 Modbus 호출. `contour_template_matcher.py`는 CLI 출력만.

---

## 3. iRayple 카메라 SDK

| 항목 | 내용 |
|------|------|
| 모델 | iRayple **USB 카메라** (GigE 아님) |
| 인터페이스 | USB 3.0 |
| SDK | IMVApi (ctypes 직접 호출) |
| Python 패키지 | 별도 패키징 없음 — DLL/SO 직접 로드 |
| DLL/SO 경로 | `flicdern/camera/Python/MVSDK_Linux/` (Linux) 또는 `flicdern/camera/Python/IMV/MVSDK/` (Windows) |
| 트리거 모드 | OFF (free-run 연속 grabbing) |
| 픽셀 포맷 | BGR8 (변환 후) |

⚠️ **SDK 본체 누락**: 5/7 받은 자료에 `flicdern/camera/Python/MVSDK_*/` 폴더 없음. IPC-510 셋업 시 한솔에 별도 요청 필요.

### 3.1 설치 절차 (`iraypl_sdk 설치방법.docx` 요약)
1. MvViewer SDK 설치파일 관리자 권한 실행
2. PC 재부팅
3. 카메라를 PC USB 3.0 포트 **직접** 연결 (허브 비추천)
4. MvViewer 실행 → 장치 검색 → Open → Live 확인
5. 위까지 OK여야 Python 연결 가능 상태

---

## 4. 우리 빈피킹과의 충돌 영역 (통합 시 합의 필요)

### 4.1 Modbus 레지스터 충돌

| 레지스터 영역 | 한솔 바텀비전 | 우리 빈피킹 (`modbus_server.py`, 4/15 INT16) |
|--------------|-------------|--------------------------------------|
| 0~41 | HR0~42 (홀 좌표) | (미사용) |
| 130~140 | (미사용) | CMD / 부품ID / X,Y,Z,Rx,Ry,Rz / 그리퍼 |
| 150~151 | (미사용) | ROBOT_STATE / seq echo |

→ **현재 레지스터 영역은 분리됨** (다행). 직접 충돌은 없음.

⚠️ 단, **HCR-10L 펜던트 프로그램이 양쪽 다 처리해야 함** — phase 분기 로직 = 한솔 펜던트 책임. 우리가 단독 검증 불가.

### 4.2 데이터 형식 불일치

| 항목 | 한솔 바텀비전 | 우리 빈피킹 |
|------|-------------|------------|
| 좌표 단위 | uint16 픽셀 (정수) | INT16 1/10mm (정수) |
| 좌표계 | 카메라 이미지 좌표 | 미정 (카메라/로봇 base 중) |
| 출력 개수 | 최대 20개 (홀) | 1개 (가장 좋은 부품 후보) |
| 회전각 | 없음 (Z회전만 contour matcher에서 산출, Modbus 미송신) | 6DoF 또는 4DoF (5/6 회의에서 4DoF로 변경 예정) |
| 부품 ID | 없음 (모든 홀 동일) | 있음 (131 reg, 29종 클래스) |

→ **통일 옵션 4가지** 검토 필요 (시점: 펜던트 통합 단계, 6~7월 예상):
- A. phase 시간 분리 (현재 영역 그대로) — 가장 간단
- B. 레지스터 영역 명확 구분 — 깨끗함
- C. 데이터 형식 통일 (mm 좌표로 통일) — 이상적, 한솔 코드 수정 필요
- D. 별도 Modbus 서버 분리 — HCR 지원 여부 미확인

→ **선택은 펜던트 구조 받은 후**. 우리 단독 결정 불가.

### 4.3 Modbus 역할

| 시스템 | 비전 PC 역할 | 로봇 역할 |
|-------|------------|----------|
| 한솔 바텀비전 | **클라이언트** (HR에 쓰기) | **서버** (HR 호스팅, 펜던트 내장) |
| 우리 빈피킹 (4/15 INT16) | **서버** (Reg 130~ 호스팅) | **클라이언트** (Reg 읽어가기) |

⚠️ **역할이 정반대** — HCR-10L 펜던트가 양쪽 다 가능한지 미확인. 한솔이 펜던트 구조 공유해줘야 명확해짐.

---

## 5. 의문/미확인 사항 (통합 시점에 한솔에 질의)

| # | 질문 | 답 받아야 할 이유 |
|---|------|----------------|
| 1 | HCR-10L 펜던트가 빈피킹 phase ↔ 바텀비전 phase를 어떻게 분기하나? | 통합 시퀀스 설계 |
| 2 | 펜던트 프로그램에서 Modbus 클라이언트/서버 동시 운영 가능한가? (한솔=서버, 우리=클라이언트) | 우리 코드 역할 결정 |
| 3 | `mm_per_pixel` 캘리브레이션 값은 한솔이 어떻게 산출하나? IPC-510에 어떻게 저장? | 픽셀↔mm 변환 일관성 |
| 4 | iRayple 카메라 마운트 위치 (작업대 아래? 위?) 및 부품과의 거리 | FOV/캘리브 추정 |
| 5 | 바텀비전 입력 시점 (어느 phase에서 트리거?) | 시퀀스 동기화 |
| 6 | iRayple SDK DLL/SO 본체 폴더 누락 — 별도 공유 필요 | IPC-510 셋업 |
| 7 | 한솔 코드의 `templates.json`은 prototype 1개만 등록. 운영 시 부품별 등록은 누가? | 후가공 대상 부품 정의 |
| 8 | 좌표계 변환 (카메라 → 로봇 base) 책임 소재 — 펜던트? 비전PC? | 우리 빈피킹도 같은 문제 |

→ **이 질문들은 펜던트 구조 공유 요청 시점에 묶어서 한 번에**. 지금은 묻지 않음 (대표님 부재 + 펜던트 통합 시점이 6~7월).

---

## 6. 보안 스캔 결과 (5/11 기준)

| 검사 항목 | 결과 |
|---------|------|
| 회사명 (Flickdone/Orinu/한솔) | 코드 내 없음 (`Flicdern_v3` 디렉토리명은 의도적 변형) |
| 담당자 실명 | 없음 |
| 내부 IP / 도메인 | 없음 (모두 CLI 인자, 하드코딩 X) |
| API 키 / 토큰 / 비번 | 없음 |
| 한솔 사내 경로 | 없음 |

→ 본 노트를 우리 repo `docs/hansol_handover/`에 commit 가능 (소스코드 직접 인용 없음, 인터페이스 명세만).

---

## 7. 우리가 챙겨야 할 액션 (시점별)

### 즉시 (오늘 = 5/11)
- ✅ 본 노트 작성 — 인터페이스 스냅샷 보존
- 자료 영구 보관 (`/tmp/bottom_vision_review/` → `~/hansol_handover/bottom_vision_20260507/`)
  - 제외: `.venv/` (275MB), `__pycache__/`, `Machine+Vision+MVviewer/` (197MB .exe 설치파일)

### IPC-510 셋업 시점 (5월 후반)
- iRayple SDK 본체 한솔에 별도 요청 (`MVSDK_Linux/` 또는 `IMV/MVSDK/`)
- MvViewer 설치 → 카메라 검색 → Live 확인
- `flicdern/` 코드 그대로 실행해서 한솔 시스템 작동 확인

### 펜던트 통합 시점 (6~7월)
- 위 §5 의문 8가지 한솔에 질의
- 통합 시퀀스 설계 (옵션 A/B/C/D 중 선택)
- 빈피킹 + 바텀비전 동시 운영 테스트
- 본 노트 v2 작성 (펜던트 구조 반영)

---

## 참고

- 한솔 회의록: `~/.claude/projects/-home-jtm/memory/project_meeting_0423_hansol.md`, `project_meeting_0506_hansol.md`
- 대표님 빈피킹 지시: `~/.claude/projects/-home-jtm/memory/project_binpicking_ceo_directive_0506.md`
- 4/14 HCR 교육 (Modbus 맵): `~/.claude/projects/-home-jtm/memory/reference_hcr_user_education.md`
- 우리 빈피킹 Modbus 설계 (4/15 INT16): `bin_picking/src/communication/modbus_server.py`
