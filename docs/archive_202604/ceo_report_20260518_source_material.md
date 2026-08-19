# 대표님 보고용 소스 자료 — 빈피킹 프로젝트 현황 (2026-05-18 기준)

> **용도**: 웹 Claude로 보고서 작성 시 입력 자료. 사실 + 수치 + 아키텍처 + 미완료 항목 정리.
> **작성**: 2026-05-18 (정태민, 6000 Claude 보조)
> **출처**: CLAUDE.md, CLAUDE.local.md, 메모리 30+ 파일, 4/6~5/18 commit 히스토리

---

## 1. 프로젝트 총 목표

### 1.1 최상위 목표
오리누 빈피킹 자동화 시스템 — **빈에 마구잡이로 쌓인 SLA 부품을 카메라로 인식해 6축 협동로봇이 자동으로 집어 다음 공정으로 전달**

### 1.2 핵심 제약 + 결정
- **카메라**: Basler Blaze-112 (ToF depth) + ace2 (RGB) 듀얼 마운트, 로봇 손목 장착 (eye-in-hand) — 5/6 한솔 회의 합의
- **로봇**: 한화 HCR-10L (10kg 가반하중) + Modbus TCP 통신
- **좌표**: X, Y, Z, Theta **4DoF** (5/6 한솔 회의에서 6DoF → 4DoF 단순화)
- **다면 인식**: 좌표 차원 줄이고 자세 분리(A자세 / B자세) + 리그립으로 해결
- **부품 범위**: 출력 부품 29종 중 5종 prototype (5/11 깊게 모드 결정)
- **타임라인**: 6/2 KAIST 3단계 부트캠프 프로젝트 시작 (~6주, 회사 데이터 활용)

### 1.3 5/6 대표님 4대 지시 (이행 추적)
| # | 지시 | 진행 |
|---|------|------|
| 1 | Basler 로컬 테스트 우선 (IPC-510 셋업 기다리지 말 것) | ✅ 5/12 Mac Blaze 풀 작동 검증 |
| 2 | 공장 실물 부품 다각도 촬영 + 학습 (실데이터 강조) | 🔄 5/18 116장 1차 / 5/20~ 본격 보강 |
| 3 | X, Y 각도 (뒤집기) 데이터 고민 + 명세 align | ✅ 1pager v2.5 + stable_poses + pose_validation_protocol 완성 |
| 4 | 예승님 연락 (좌표 명세 + 바텀비전 소스) | ✅ 바텀비전 인수 (5/11) + 빈피킹 뼈대 코드 인계 (5/18) |

---

## 2. 시스템 아키텍처

### 2.1 전체 데이터 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                     빈피킹 시스템 아키텍처                       │
└─────────────────────────────────────────────────────────────────┘

  [부품 빈]
     │
     ├──→ Blaze-112 (ToF Depth, 848×480, 0.3~10m)
     │         │
     │         └──→ depth_map (mm)
     │
     └──→ ace2 (RGB, 2448×2048, IMX392)
               │
               └──→ color_image (BGR)
                        │
                        ↓
            ┌──────────────────────┐
            │   인식 파이프라인     │
            │   (트랙 2가지 병행)   │
            └──────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
   [트랙 1: 6DoF 정밀]            [트랙 2: YOLO 분류]
   (4/6~10 완성)                  (5/18 v1 완성)
        │                               │
        │ L1 영상 취득                  │ YOLO 추론
        │ L2 전처리 (ROI/RANSAC/법선)   │   ↓
        │ L3 DBSCAN 분할                │ bbox + class
        │ L4 FPFH+ICP 6DoF              │   ↓
        │ L5 그래스프 DB (29종)          │ bbox 중심 픽셀
        │   ↓                           │   ↓
        │ 6DoF pose (4DoF로 축소)        │ depth 추출
        │                               │
        └───────────────┬───────────────┘
                        ↓
            ┌──────────────────────┐
            │  Hand-Eye 변환       │
            │  T_gripper2camera    │
            │  (캘리브 6~7월)       │
            └──────────────────────┘
                        ↓
            로봇 베이스 좌표 (X, Y, Z, Theta)
                        ↓
            ┌──────────────────────┐
            │  Modbus TCP INT16    │
            │  register 130~140    │
            └──────────────────────┘
                        ↓
                   [한화 HCR-10L]
                        ↓
                   픽업 → 다음 공정
```

### 2.2 두 트랙 병행 전략 (5/15 예승님 제안 + 5/18 우리 확정)

| 항목 | 트랙 1 (6DoF 정밀) | 트랙 2 (YOLO 분류) |
|------|------------------|------------------|
| 출력 | 6DoF pose (X,Y,Z + 회전 3축) → 4DoF 축소 | bbox + class_id |
| 알고리즘 | FPFH + ICP (Point Cloud matching) | YOLOv8n (Object Detection) |
| 입력 데이터 | depth + CAD 모델 | RGB 이미지 |
| 강점 | 자세 정밀 (정밀 조립), 자세 분리/리그립 핵심 | 빠른 prototype, 작은 데이터로 학습 가능 |
| 약점 | 무거움, CAD 일치 필요 | 자세 정보 X (bbox 중심만) |
| 현재 상태 | 코드 완성 (4/10), 실 검증 보류 (5/18 환경 제약) | v1 학습 완료 (5/18, mAP50 0.988) |

### 2.3 통합 흐름 (목표)
```
카메라 → 트랙 2 (YOLO 빠른 분류) → bbox + class
       ↓
    bbox 영역에 대해 트랙 1 (6DoF 정밀 매칭)
       ↓
    grasp pose 산출 → 로봇 송신
```

5/22 이후 한솔 빈피킹 뼈대 코드 어댑테이션으로 통합 시연 코드 작성.

### 2.4 하드웨어 구성

| 장치 | 모델 | 상태 |
|------|-----|------|
| Depth 카메라 | Basler Blaze-112 (S/N 40737830) | ✅ 5/12 Mac 풀 작동 |
| RGB 카메라 | Basler ace2 a2A2448-23gcBAS (S/N 41881328) | ⏳ 5/20 셋업 예정 (어댑터 도착) |
| 협동로봇 | 한화 HCR-10L (10kg) | ⏳ IPC-510 입고(4/23), 셋업 미시작 |
| 비전 PC | IPC-510 (i7 + RTX4070) | ⏳ 셋업 미시작 (Mac으로 우선 진행) |
| GPU 학습 | AICA A100 (80GB) | ✅ 5/18 부활 + 환경 구축 + 학습 |
| 어댑터 | ipTIME U1G-C × 2개 | ✅ 1개 5/11 도착 / 2개째 5/15~17 도착 |
| 출력 부품 | SLA 5종 (회사 출력) | ✅ 사무실 보관 중 |
| 그리퍼 | TBD | ❌ 미장착 (6~7월 예정) |
| 카메라 브라켓 | 코에버 설계 → 오리누 출력 → 철제 가공 | 🔄 한솔 STL 5/14 메일 수령 / 출력 대기 |

---

## 3. ✅ 완료된 작업

### 3.1 트랙 1 (Basler 6DoF) — L1~L6 파이프라인 완성 (4/6~10)

**29종 STL 기반 E2E 테스트 결과**:
| 지표 | 결과 | 목표 | 판정 |
|------|-----|------|-----|
| 인식률 (easy 5종) | 100% | 85% | ✅ |
| 인식률 (crowded 10종) | 90% | 80% | ✅ |
| 인식률 (hard 5종) | 60% | 85% | ⚠️ (Colored ICP 도입 예정) |
| RMSE | 1.0~1.5mm | 3mm | ✅ |
| 매칭 시간 (OBB SizeFilter) | 0.4~0.6초 | 2초 | ✅ (3~5배 여유) |

**코드 위치** (`bin_picking/src/`):
- L1 영상취득: `acquisition/basler_capture.py` (5/12 Mac 검증)
- L2 전처리: `preprocessing/cloud_filter.py`
- L3 분할: `segmentation/dbscan_segmenter.py`
- L4 인식+자세: `recognition/cad_library.py` + `pose_estimator.py` + `size_filter.py`
- L5 그래스프: `grasping/grasp_planner.py` + `grasp_database.yaml` (29종)
- L6 통신: `communication/modbus_server.py` (Modbus INT16)
- 통합: `main_pipeline.py`

### 3.2 트랙 2 (Roboflow + YOLO) — v1 학습 완료 (5/18)

#### 데이터 수집
- 5/15 공장 사전 촬영: 폰 사진 95장 (사용자 분류 후 116장으로 정정)
- 5/18 Roboflow Project `parts-5class-v1` 생성 + annotation 완주

**데이터셋 분포**:
| 클래스 | 학습 데이터 |
|--------|----------|
| part_1 | 25장 |
| part_2 | 26장 |
| part_3 (bracket_sen_1, 56mm 확정) | 23장 |
| part_4 | 24장 |
| part_5 (main_body 추정) | 18장 |
| **합계 (raw)** | **116장** |

**Roboflow Version v1 (augmented)**:
- Train 243장 (81 × 3 augmentation) + Valid 23 + Test 12 = **278장**
- Augmentation: Flip Horizontal / Rotation ±30° / Brightness ±25%
- Preprocessing: Auto-Orient + Resize 640×640

#### 학습 결과 (AICA A100, YOLOv8n, 150 epochs, 10분 22초)

| 지표 | 값 |
|------|---|
| **mAP50** | **0.988** (best) / 0.954 (last) |
| **mAP50-95** | **0.836** / 0.805 |
| Precision | 0.935 (best) / 0.872 (last) |
| Recall | 0.891 / 0.937 |
| Inference 속도 | 0.6ms/image (1666 FPS on A100) |
| 모델 크기 | best.pt 6MB |

**클래스별 (best.pt 기준)**:
| 클래스 | Precision | Recall | mAP50 |
|--------|-----------|--------|-------|
| part_1 | 0.800 | 1.000 | 0.995 |
| part_2 | 1.000 | **0.656** ⚠️ | 0.995 |
| part_3 | 0.979 | 1.000 | 0.995 |
| part_4 | 0.983 | 1.000 | 0.995 |
| part_5 | 0.911 | 0.800 | 0.962 |

### 3.3 인프라

| 항목 | 상태 |
|------|-----|
| Basler 어댑터 (ipTIME U1G-C) 검증 | ✅ 5/11 도착, USB 3.0 + Gigabit 검증 |
| Mac 네트워크 분리 (192.168.20/24) | ✅ Wi-Fi 충돌 회피 |
| Blaze macOS 풀 작동 (pypylon 단독) | ✅ 5/12 검증 (Supplementary 없이) |
| AICA A100 GPU 환경 구축 | ✅ 5/18 SSH key 등록 + PyTorch 2.1 + CUDA 12.8 + ultralytics |
| 학습 자동화 스크립트 | ✅ `aica_setup.sh` + `train_v1.sh` (재현 가능) |
| 함정 7가지 메모리화 | ✅ `reference_aica_a100.md` (/dev/shm 64MB 회피 등) |

### 3.4 한솔코에버 협업

| 일자 | 내용 |
|------|------|
| 4/23 | 한솔 3자 회의 — eye-in-hand 듀얼 마운트 합의, Basler/IPC-510 입고 |
| 5/6 | 한솔 3자 회의 — 4DoF 좌표 / 다면 인식 (A/B자세) / Formlabs API 무인 운전 불가 공식화 / 카메라 브라켓 코에버 설계 |
| 5/11 | 한솔 바텀비전 자료 인수 완료 (Flicdern_v3, 33MB) |
| 5/14 | 한솔 카메라 브라켓 STL 메일 도착 (5/15 출력 예정) |
| 5/15 | ACE2 전원 케이블 한솔 보유분 인수 (예승님 직접 만남) |
| 5/18 | **한솔 빈피킹 뼈대 코드 4파일 783줄 인계** (RealSense wrapper + Hand-Eye 캘리브레이션 + T_gripper2camera reference + 통합 시퀀스) |

---

## 4. ❌ 미완료 / 진행 중 작업

### 4.1 트랙 1 (6DoF) — 실 부품 검증 보류

**5/18 발견 문제**:
1. **A4 sanity fundamental 불가**: Blaze FOV 75° + 최소 30cm → 시야 가로 46cm vs A4 21cm = 45% 최대. 시야 70% 채우기 물리적으로 불가능. → 5/14 작성한 `check_intrinsics_planar.py` 산수 오류 발견
2. **P5 main_body 작음**: 5cm 미만 추정 → Blaze 단독 캡처 어려움, ACE2 RGB 동시 필요 시그널
3. **사무실 valid % 4~8%**: 모니터/키보드 등 검정 흡수재 많아 ToF valid 픽셀 낮음

**5/18 결정**:
- 트랙 1 P5 파일럿 보류 → 다음 사무실 셋업 시 재시도 (5/20 또는 5/22)
- 재시도 조건 5개: 깨끗한 책상 + 큰 부품 P3/P4 우선 + ChArUco 정식 캘리브 + ACE2 셋업 완료 + 회전대

### 4.2 핸드-아이 캘리브레이션 — 코드만 있고 실행 X

- 우리 stub: `bin_picking/src/acquisition/hand_eye_calibration.py` (4/15 작성)
- 한솔 코드 인계: `handeye_calibration.py` (5/18, OpenCV `calibrateHandEye(PARK)` 사용)
- **실 실행은 그리퍼 장착 후 (6~7월)**. 우리 환경 `T_gripper2camera.npy` 새로 측정 필요
- 한솔 reference 값: Translation (30.5, 56.7, -212.4)mm (D사 환경, 자릿수 sanity check용)

### 4.3 트랙 2 (YOLO) — 데이터 robustness 부족

**v1 학습 결과 의심**:
- mAP50 0.988 너무 높음 → **데이터 누수 (data leakage) 의심**
- 116장 모두 5/15 단일 환경 (회색 책상 / 1 부품 / 일정 조명)
- Train/Valid/Test가 같은 분포에서 random split → 모델이 학습한 패턴이 실 환경에서 작동할지 미검증

**part_2 약점**:
- Recall 0.656 (4장 validation 중 1~2장 놓침)
- 5/20 추가 촬영 시 우선 보강 (오늘 1.5h에 part_2 자세 다양화 10장)

**필요 작업 (5/20~)**:
- 다양한 환경 (배경/조명/거리/겹침) 추가 100~150장
- v2 학습 + v1 vs v2 비교 (실 환경 robustness 검증)
- 부품 겹침 사진 0장 → 실 빈피킹 환경 도메인 갭

### 4.4 ACE2 RGB 카메라 — 셋업 미완

- 5/8 8단계 검증 절차 작성 완료
- 어댑터 2개째 5/16~17 도착 예정 → 회사 도착 확인 후 5/20 셋업
- 셋업 후 효과: Blaze (depth) + ACE2 (RGB) 동시 캡처 → Colored ICP (트랙 1 hard 부품 60% → 80%+ 기대)

### 4.5 한화 HCR-10L 실 연동 — 미시작

- IPC-510 (4/23 입고) + HCR-10L 셋업 미시작
- 한화 Python SDK / Socket 인터페이스 정보 미확정 (5/6 회의 액션, 한솔 ASAP 확인 중)
- 그리퍼 미장착 (한솔 요청, 6~7월 예정)
- Modbus 통신 코드만 작성 (4/15 INT16 재설계), 실 송신 미검증

### 4.6 카메라 브라켓

- 한솔 STL 5/14 메일 수령 → 5/15 출력 예정이었으나 미진행
- 5/15 한글 파일명 X-Filename HTTP 헤더 ASCII 위반 버그 발견 → fix 완료 (commit `06e68b4`, 3서버 동기화)
- 실 출력 + 카메라 장착 + 철제 가공 단계 남음

### 4.7 통합 시퀀스 (한솔 코드 어댑테이션)

5/19 작성 시작 (Phase 2 임계 2파일):
- `bin_picking/yolo_track/camera/basler_wrapper.py` (작성됨)
- `bin_picking/yolo_track/pipeline/bin_picking_main.py` (작성됨)
- 남은 2파일 (5/27 재택 예정):
  - `bin_picking/yolo_track/robot/hanwha_robot_modbus.py`
  - `bin_picking/yolo_track/calibration/handeye_calibration.py`

5/22 통합 시연 목표: 카메라 라이브 + YOLO 추론 + bbox + dry-run 픽업 명령

---

## 5. YOLO 모델 선택 근거

### 5.1 Basler 공식 입장

**Basler pylon AI 공식 지원**:
- YOLO v8-seg (segmentation 포함) Ultralytics 모델 지원 표기
- 모델 형식: **ONNX 변환 필수** (pylon AI 통합용)
- 라이센스: AGPL 3.0 (Ultralytics 공식)
- Basler ace2 Basic = 컴퓨터 비전 일반 용도 권장 카메라 (cost-performance balance)

**Roboflow Inference + Basler 통합** (Enterprise만 지원, 우리는 비대상):
- 지원 모델: **YOLOv5, YOLOv8, YOLOv9, YOLOv10**
- YOLOv7/v8: segmentation
- YOLOv8: keypoint detection

**Basler 공식 가이드의 한계**:
- 특정 YOLO 버전을 "추천"한다기보다 "지원 가능한 것들"을 나열
- 실제 모델 선택은 사용자 책임 (use case + 하드웨어 + 데이터 따라)

### 5.2 2026년 5월 시점 YOLO 생태계

| 버전 | 출시 | 특징 |
|------|------|------|
| YOLOv5 (Ultralytics) | 2020 | 가장 오래된 안정 버전, 폭넓은 채택 |
| YOLOv7 | 2022 | 정확도 강점 |
| YOLOv8 (Ultralytics) | 2023 | **현 산업 표준**, 다양한 task 지원 (detect/seg/cls/pose) |
| YOLOv9 | 2024 | 효율 개선 |
| YOLOv10 | 2024 | NMS-free, 추론 속도 ↑ |
| YOLOv11 (Ultralytics) | 2024 후반 | 최신 안정, 정확도 + 속도 |
| **YOLO26** | **2026.01** | edge deployment 최적화, CPU 추론 ↑, 컴팩트 |

### 5.3 우리가 YOLOv8을 선택한 이유

**1. Roboflow 호환성 우선**:
- 5/15 예승님 제안 = Roboflow 사용
- Roboflow YOLO export 포맷이 v8 기반 가장 안정
- Roboflow + YOLOv8 조합이 가장 많은 튜토리얼/커뮤니티 지원

**2. Ultralytics 생태계 성숙**:
- `pip install ultralytics` 한 줄 설치
- `yolo detect train` CLI 1줄 학습
- AICA A100 환경에서 5/18 즉시 동작 (PyTorch 2.1 + CUDA 12.8 호환)

**3. nano 모델 (yolov8n) 가벼움**:
- 6MB best.pt — 우리 5클래스 116장 데이터에 적합 (작은 데이터에 큰 모델은 overfit)
- 추론 0.6ms/image (실시간 충분)
- 비전 PC GPU (RTX 4070) 또는 향후 edge 배포 가능

**4. Basler pylon AI 호환**:
- YOLOv8 → ONNX export 가능 (`yolo export format=onnx`)
- 추후 pylon AI vTool 통합 시 즉시 사용 가능

**5. AGPL 3.0 라이센스 영향**:
- Ultralytics YOLO = AGPL 3.0 (copyleft)
- 우리 코드 공개 시 AGPL 의무 (사내 사용은 무관)
- 상용 라이센스 가능 (Ultralytics에 별도 문의)
- 추후 영향 시 v10 (Apache 2.0) 등 대안 검토 가능

### 5.4 다른 버전 검토하지 않은 이유

- **YOLOv11**: 2024년 후반 출시, 6/2 부트캠프 시작 압박으로 검증된 v8 우선
- **YOLO26**: 2026.01 출시 신제품, 라이브러리 안정성 미확인. 사무실 4일 안에 시행착오 리스크
- **YOLOv10**: NMS-free 매력적이나 Roboflow 통합 우선
- **v5/v7**: 구버전, 신규 도입 의미 ↓

### 5.5 향후 고려

- 5/29 또는 6/2 이후 시간 여유 시 **v8 vs v11 비교 실험** 가능
- ONNX export 검증 (Basler pylon AI 통합 대비)
- edge 배포 (MaixCAM 또는 Jetson) 검토 시 **YOLO26** 카드

---

## 6. 6/2 KAIST 부트캠프 일정

### 6.1 마감
- **6/1 (월)** 부트캠프 입력 자료 제출
- **6/2 (화)** 부트캠프 3단계 6주 프로젝트 시작 — 주제 "빈피킹 + 비전 AI"

### 6.2 사무실 가용 4일 (5/18 결정)
| 일자 | 핵심 작업 |
|------|---------|
| 5/20 (수) | ACE2 셋업 + 데이터 보강 100~150장 + 트랙 1 P3/P4 빠른 검증 |
| 5/22 (금) | Roboflow v2 + AICA v2 학습 + 한솔 코드 어댑테이션 라이브 검증 |
| 5/29 (금) | 빈/박스 환경 통합 시연 + 영상 녹화 |
| 6/1 (월?) | 최종 자료 마감 |

### 6.3 화/목 (KAIST 교육) + 수 5/27 (재택)
- 코드 작성 (Phase 2 robot_modbus + handeye_calibration)
- 발표 자료 (5/26)
- 사이드 (.form 패치 리뷰 / 시간 차이 디버깅)

---

## 7. 리스크 + 대응 (1pager v2.5 § 8 핵심 발췌)

| # | 리스크 | 가능성 | 대응 |
|---|--------|-------|------|
| 19 | A4 sanity Blaze FOV 75° fundamental 불가 | **확인됨 (5/18)** | ChArUco 정식 캘리브 (5/20 ACE2 셋업 시) 또는 A2 평면 |
| 20 | 사무실 valid % 4~8% (검정 흡수재 많음) | **확인됨 (5/18)** | 5/20 깨끗한 책상 + 단순 배경 + 균일 조명 필수 |
| 21 | 데이터 누수 의심 (v1 mAP 0.988 너무 높음) | **중** | 5/20 다양한 환경 추가 → v2 mAP 변화 검증 |
| 22 | Roboflow Public plan = 데이터셋 외부 노출 | **수용 (5/18)** | 클래스명 `part_1~5` 익명화. Private 전환은 Core $79/월 (대표님 승인 시) |
| 23 | best.pt vs last.pt 메트릭 차이 (part_2 R: 0.656 vs 0.937) | **저** | last.pt를 시연용으로 사용 검토 또는 v2에서 epoch 단축 |

### 5/6 회의 미해결 액션
1. **한화 HCR-10L Python SDK / Socket 인터페이스** — 한솔 이예승 ASAP 확인 (5/18 회신 메일에 재요청)
2. **빈피킹 카메라 브라켓 출력** — 한솔 STL 도착 (5/14) → 출력 미진행

### 대표님 질의 필요 (1pager § 9)
1. 학습 데이터 규모 — 5종 × ~500장 = 2,400장 적정한가?
2. regrasp 시퀀스 책임 소재 — 우리 코드 / 한솔 펜던트 / 사람?
3. 학습 모델 선택 시점 — 데이터 모인 후 / 부트캠프 묶기?
4. 29종 풀 데이터셋 시점
5. 펜던트 통합 일정
6. 빈피킹 vs Phase 4 MaixCAM 우선순위

---

## 8. 주요 메모리/문서 위치 (보고서 작성 시 참고)

### 메모리 (회사 내부, `~/.claude/projects/-home-jtm/memory/`)
- `project_binpicking.md` — Phase 5 빈피킹 전체 (L1~L6, STL 29종)
- `project_binpicking_e2e_history.md` — v1~v14 E2E 테스트 이력
- `project_binpicking_ceo_directive_0506.md` — 대표님 5/6 지시 4가지
- `project_meeting_0506_hansol.md` — 한솔 3자 회의록
- `project_meeting_0423_hansol.md` — 4/23 회의록
- `project_roboflow_v1_setup_0518.md` — Roboflow + AICA 학습 결과
- `project_hansol_bin_picking_handover_0518.md` — 한솔 코드 4파일 분석
- `project_p5_pilot_blocked_0518.md` — 트랙 1 보류 결정 + 재시도 조건
- `reference_aica_a100.md` — AICA 환경 + 함정 7가지
- `reference_basler_blaze_112.md` — Basler 하드웨어 사양

### 문서 (git 추적)
- `docs/archive_track1_202605/binpicking_learning_data_strategy_1pager_20260511.md` — **1pager v2.5 (대표님 align용)**
- `docs/archive_track1_202605/binpicking_capture_sop_20260511.md` — 본 캡처 SOP
- `docs/archive_track1_202605/binpicking_pose_validation_protocol.md` — 자세 검증 매뉴얼
- `docs/archive_track1_202605/binpicking_friday_runbook_20260515.md` — 사무실 runbook
- `docs/archive_track1_202605/office_checklist_20260520.md` — 5/20 작업 체크리스트
- `bin_picking/yolo_track/runs/v1-yolov8n-0719/` — 학습 결과 (results.png / confusion_matrix.png / weights/best.pt)

### Git
- 회사 리포 (origin): https://github.com/orinu-ai/3D_printer_automation (Private)
- 개인 미러 (한솔 공유): https://github.com/m2222n/3D_printer_automation (Private)
- 마지막 commit: `199c7d1 feat(yolo_track): 5/18 빈피킹 YOLO 트랙 2 v1 + AICA 학습 결과`

### Roboflow
- Workspace: `orinubinpicking`
- Project: `parts-5class-v1` (Public, CC BY 4.0)
- Version v1: 278장 augmented
- Universe URL: `https://universe.roboflow.com/orinubinpicking/parts-5class-v1/dataset/1`

---

## 9. 보고서 작성 가이드 (웹 Claude용)

이 자료를 입력으로 사용 시:

### 보고서 권장 구성
1. **개요** — 빈피킹 시스템 1줄 요약 + 6/2 부트캠프 목표
2. **아키텍처** — 섹션 2.1 다이어그램 + 2.2 두 트랙 표 + 2.4 하드웨어
3. **진행 상황** — 섹션 3 (완료) + 4 (미완료) 균형 있게
4. **YOLO 모델 선택** — 섹션 5 (Basler 공식 + 우리 결정 근거)
5. **6/2 마감 + 일정** — 섹션 6
6. **리스크 + 대표님 질의** — 섹션 7
7. **다음 단계** — 5/20 작업 미리보기

### 톤
- 객관적 사실 + 수치 위주
- 미완료는 "왜 안 됐는지 + 다음 액션" 명시
- 대표님 5/6 4대 지시 이행 상황 표 강조
- 5/6 4DoF / 카메라 브라켓 / 다면 인식 같은 한솔 회의 합의 사항 반영

### 분량
- 1~2 페이지 (간결) 또는 4~5 페이지 (상세) 모두 가능
- 아키텍처 다이어그램 + 메트릭 표 + 리스크 표 핵심 강조

---

## 출처

- [Roboflow: Deploy Object Detection Models on Basler Cameras](https://roboflow.com/cameras/deploy-object-detection-models-on-basler-cameras)
- [Basler pylon AI Documentation](https://docs.baslerweb.com/introduction-to-pylon-ai)
- [YOLO26 Release Blog (Roboflow, 2026.01)](https://blog.roboflow.com/yolo26/)
- [Ultralytics YOLOv8 공식](https://github.com/ultralytics/ultralytics)
- 5/18 commit `199c7d1` (yolo_track v1 결과)
- 5/18 commit `3f3220b` (CLAUDE.md 5/18 마일스톤)
