# 3D Printer Automation System

> 3D프린터-로봇 연동 자동화 시스템 | Formlabs Form 4 + HCR 협동로봇 + 3D 빈피킹 비전 (Depth + CAD) + 라인 MES

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)](https://vitejs.dev)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-psycopg_3-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![MariaDB](https://img.shields.io/badge/MariaDB-11-003545?logo=mariadb&logoColor=white)](https://mariadb.org)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.1-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org)
[![Ultralytics](https://img.shields.io/badge/Ultralytics-YOLOv8%2Fv11-0078D4?logoColor=white)](https://docs.ultralytics.com)
[![ONNX](https://img.shields.io/badge/ONNX-Runtime-005CED?logo=onnx&logoColor=white)](https://onnx.ai)
[![Open3D](https://img.shields.io/badge/Open3D-0.19-4B8BBE?logo=python&logoColor=white)](http://www.open3d.org)
[![Modbus](https://img.shields.io/badge/Modbus_TCP-pymodbus_3-FF6F00?logo=python&logoColor=white)](https://pymodbus.readthedocs.io)
[![Basler](https://img.shields.io/badge/Basler-pypylon-0078D4?logoColor=white)](https://www.baslerweb.com)
[![RealSense](https://img.shields.io/badge/Intel_RealSense-D435-0071C5?logo=intel&logoColor=white)](https://www.intelrealsense.com)
[![MQTT](https://img.shields.io/badge/MQTT-Mosquitto-660066?logo=mqtt&logoColor=white)](https://mosquitto.org)
[![Cloudflare](https://img.shields.io/badge/Cloudflare-Tunnel-F38020?logo=cloudflare&logoColor=white)](https://www.cloudflare.com)

---

## 프로젝트 개요

점자프린터 플라스틱 부품(약 20종) 생산 공정을 자동화하는 시스템입니다.

- **셀A (프린팅 라인)**: 프린터 4대 → 세척 → 건조 → 경화를 로봇과 통합 제어 서버가 관리
- **셀B (후가공 라인)**: 빈피킹 비전으로 부품을 찾아 집고 드릴·트림 스테이션으로 이송
- **라인 MES**: 배치(빌드플레이트)와 부품이 "지금 어디 있나"를 관측하는 도메인 + 모니터링·제어 대시보드

### 하드웨어 구성

| 장비 | 모델 | 수량 | 용도 |
|------|------|------|------|
| 3D 프린터 | Formlabs Form 4 | 4대 | SLA 레진 프린팅 |
| 협동로봇 | HCR-12A | 1대 | 빌드플레이트 교체, 세척기 투입 (셀A) |
| 협동로봇 | HCR-10L | 1대 | 빈피킹, 후가공 이송 (셀B) |
| 세척기 | Form Wash | 2대 | 레진 세척 |
| 경화기 | Form Cure | 1대 | UV 경화 |
| 3D 카메라 | Basler Blaze-112 (ToF) | 1대 | 빈피킹 Depth 취득 (eye-in-hand) |
| 2D 카메라 | Basler ace2 5MP | 1대 | 빈피킹 RGB 취득 (Blaze와 동시 마운트) |
| 깊이 카메라 | Intel RealSense D435 | 1대 | 빈피킹 임시 검증 |
| 산업용 PC | IPC-510 (RTX GPU) | 1대 | 셀B 비전·로봇 통신 허브 |
| 리모트 I/O | PoE 이더넷 리모트 I/O (DI/DO · RTD) | 3대 | 세척기·경화기·건조기·타워램프 신호 통합 (상태 감시) |
| 엣지 AI 카메라 | Sipeed MaixCAM | 1+대 | 세척기/경화기 완료 감지 (PoC) |

---

## 개발 단계

| Phase | 항목 | 상태 |
|-------|------|------|
| **Phase 1** | Web API 모니터링 (Formlabs Cloud) | ✅ 완료 |
| **Phase 2** | Local API 원격 프린트 제어 + 프론트엔드 UI | ✅ 완료 |
| **Phase 3** | HCR 로봇 연동 + 시퀀스 서비스 (Modbus 8단계 핸드셰이크) | ✅ 운영 |
| **Phase 4** | 장비 상태 감시 (리모트 I/O 신호 → 상태 전이 → WebSocket) | 🔄 리모트 I/O 입고, 결선·연동 진행 중 |
| **Phase 5** | 3D 빈피킹 비전 시스템 | 🔄 트랙 2 (YOLO) v2 5모델 비교 학습 완료, ONNX 변환 + 도메인 갭 검증 단계 |
| **Phase 6** | 라인 MES v2 (관측 도메인 + `/api/v2` + 라인 모니터링·공정 제어 탭) | 🔄 백엔드 18 라우트 완료, 운영 DB 적용 대기 |

---

## 시스템 아키텍처

세 서비스가 **방향**으로 갈린다 — 쓰는 쪽(제어) · 읽는 쪽(관측) · 보여주는 쪽(API).

```
                 브라우저 (frontend/ · 9탭)
                        │ HTTP · JWT
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ web-api/                  API 층 · FastAPI                        │
│  app/api, local, vision, binpick   v1 (기존 화면)                │
│  app/line/                         v2 /api/v2 18 라우트 (라인 MES) │
│  소유 DB: SQLite                                                  │
└──────┬──────────────────────┬───────────────────────┬────────────┘
       │ 읽기·CMD 생성        │ StateEngine 호출       │ 발행 (Spawn · State)
       ▼                      ▼                       ▼
┌──────────────┐   ┌───────────────────────────────────────────────┐
│ MariaDB      │   │ line_mes/          관측 도메인 · 순수 파이썬 패키지 │
│ automation   │   │  contract.py       이벤트 4종 = 유일한 경계        │
│ (제어 진실)   │   │  state_engine.py   이벤트 → product_state · 채번   │
└──────▲───────┘   │  publish.py        논블로킹 발행기                  │
       │ 소유       │  topology.yaml · topo_sync.py · schema.sql         │
       │           │  소유 DB: PostgreSQL (LINE_DSN)                      │
┌──────┴──────────┐└───────────────────────────────────────────────┘
│ sequence_service/│  제어 층 · 단일 컨트롤러 스레드                 ▲
│  app/cell/       │  Modbus 마스터(로봇) · PreForm · 시퀀스         │ 발행 (State DONE · Moved)
│  app/cell/line_events.py ──────────────────────────────────────────┘
└─────────────────┘
```

| 서비스 | 역할 | 소유 DB | 프로세스 |
|---|---|---|---|
| `web-api/` | 브라우저가 보는 전부 — 인증 · v1 화면 API · v2 라인 MES API · 정적 파일 | SQLite | uvicorn 1개 |
| `line_mes/` | 관측 도메인 — 제품 위치 규칙·스키마. HTTP 없음, 상주 프로세스 없음 | PostgreSQL (`schema.sql` 18테이블·24뷰) | 없음 (두 서비스가 `import`) |
| `sequence_service/` | 제어 — 프린터 출력 지시 · 로봇 반송 · 셀 상태. **로봇에 쓰는 유일한 자리** | MariaDB `automation` | 스레드 1개 |

**원칙**
- 의존은 한 방향: `web-api → line_mes ← sequence_service`. `line_mes/`는 표준 라이브러리 + psycopg + yaml 외 아무것도 import하지 않는다.
- 발행은 논블로킹이고 실패해도 제어를 막지 않는다. `LINE_DSN`이 비면 v2 전체가 no-op(라우트 503, 발행 skip, 프론트는 목업).
- 위치를 바꾸는 이벤트는 `Moved` 뿐. 카메라·프린터 API는 `State`만 낸다.
- 세 DB 병존 · 기존 DDL 0 변경. 다리는 `unit.cmd_id = print_command.cmd_id` 한 컬럼.

**허브 개념**: 로봇·프린터·카메라 같은 실시간 제어는 공장 PC 로컬에서 직접 처리(네트워크 장애 시에도 안전). 원격 모니터링·UI·이력 조회만 Cloudflare Tunnel을 통해 제공.

### 라인 MES 이벤트 발행 지점

| 이벤트 | 발행 지점 | 소스 |
|---|---|---|
| `Spawn` 배치 투입 | web-api `/local/print` 전송 성공 직후 | ADAPTER |
| `State` 프린터 RUN/HOLD | web-api 폴링 서비스 (15초) | ADAPTER |
| `State` 프린터 DONE | sequence_service 프린터 시퀀스 (`cmd_status=40`) | ADAPTER |
| `State` 세척기·경화기 | web-api 상태 감시 (리모트 I/O 입력) | DEVICE |
| `Moved` 로봇 이송 완료 | sequence_service 로봇 시퀀스 (레지스터 206) | ROBOT |
| `Split` · `Moved` · `State` 작업자 | web-api `/api/v2` 쓰기 W1~W6 | MANUAL |

---

## 빈피킹 (Phase 5)

### 빈피킹 — 듀얼 트랙 전략

협력사 제안으로 두 트랙을 병행 개발 중. 산업 현장 도입 관점에서 트랙 2가 우선.

| | 트랙 1: 6DoF Pose Estimation | 트랙 2: YOLO 2D 인식 + Depth |
|---|---|---|
| 방식 | CAD 라이브러리 + FPFH + Colored ICP | YOLOv8/v11 detection + depth fusion |
| 구현 | L1~L6 Python (Open3D 기반) | Ultralytics + Roboflow + ONNXRuntime |
| 좌표 | 6DoF (rotation matrix) | 6요소 (x, y, z, edge, angle, label) |
| 데이터 | CAD 29종 + 합성 검증 | 실 부품 촬영 + augmentation + **CAD 렌더 합성 데이터셋** |
| 상태 | 인프라 완성, 환경 제약으로 단계적 검증 보류 | **v2 학습 완료, 도메인 갭 검증 단계** |

### 빈피킹 v2 학습 결과 (2026-05-22 학습 / 2026-05-26 분석)

5종 부품 (Part1~5) 인식 — Roboflow 데이터셋 946 augmented images (train 828 / val 80 / test 39):

| Rank | Model | Params | mAP50 | mAP50-95 | Recall | best.pt |
|------|-------|--------|-------|----------|--------|---------|
| 🥇 1 | **YOLOv8n** | 3.2M | **0.9939** | 0.7458 | 0.978 | 6.3MB |
| 🥈 2 | YOLOv11s | 9.5M | 0.9910 | 0.7446 | 0.979 | 19.2MB |
| 🥉 3 | YOLOv8m | 25.9M | 0.9899 | 0.7255 | 0.947 | 52.1MB |
| 4 | YOLOv11m | 20.1M | 0.9868 | 0.7225 | 0.929 | 40.5MB |
| 5 | YOLOv11l | 25.3M | 0.9842 | 0.7363 | 0.916 | 51.2MB |

**핵심 관찰**:
- 가장 작은 YOLOv8n이 1등 — 데이터셋 작은 규모에서 큰 모델은 과적합 경향
- 클래스별 약점 부품 Recall **0.656 → 0.958 (+30%p)** 회복 — 멀티 객체 촬영 효과 입증
- IPC-510 ONNXRuntime 배포 관점에서 YOLOv8n(6MB) / YOLOv11s(19MB) 동률 후보
- 다음 단계: ONNX 변환 → 도메인 갭 검증 (별도 환경 평가셋) → 최종 모델 선정

### 빈피킹 학습/배포 파이프라인

```mermaid
flowchart LR
    Capture["📸 실 부품 촬영<br/>다각도<br/>(스마트폰 + Basler)"]
    Synth["🧩 CAD 렌더 합성<br/>STEP/STL 다각도 렌더<br/>(trimesh + pyrender)"]
    Roboflow["🏷️ Roboflow<br/>(annotation + 증강)"]
    Train["🎓 A100 GPU<br/>(PyTorch + Ultralytics)"]
    ONNX["⚙️ ONNX Export<br/>(yolo export format=onnx)"]
    Deploy["🏭 IPC-510<br/>(ONNXRuntime-GPU)"]
    Coord["📐 6요소 좌표<br/>(x, y, z, edge, angle, label)"]
    Modbus["🤖 Modbus → HCR-10L"]

    Capture --> Roboflow
    Synth --> Roboflow
    Roboflow --> Train --> ONNX --> Deploy --> Coord --> Modbus

    classDef capture fill:#e3f2fd,stroke:#1976d2,color:#000
    classDef label fill:#fff8e1,stroke:#f57c00,color:#000
    classDef train fill:#f3e5f5,stroke:#7b1fa2,color:#000
    classDef export fill:#e0f7fa,stroke:#00838f,color:#000
    classDef deploy fill:#fff3e0,stroke:#e65100,color:#000
    classDef output fill:#e8f5e9,stroke:#388e3c,color:#000

    class Capture,Synth capture
    class Roboflow label
    class Train train
    class ONNX export
    class Deploy deploy
    class Coord,Modbus output
```

### 트랙 1 (6DoF Pose) 현황 — 보존 상태

CAD 기반 파이프라인은 인프라가 완성되어 있으며, 환경 제약(작업 영역, 카메라 캘리브레이션 fundamental 검증)으로 단계적 검증을 보류 중. 추후 산업 현장 셋업이 갖춰지면 트랙 2와 병행 비교 예정.

- L1~L6 Python 단독 구현 (CAD 기반 29종 인식)
- 인식률: easy 100%, crowded 90%, hard 60% (Colored ICP로 hard 개선)
- 매칭 시간 0.4~0.6s/부품, RMSE 1.0~1.5mm
- 레진별 프리셋 4종 (grey/white/clear/flexible)
- 데모 시각화: 2×2 그리드 + 3상태 색상 코딩 (ACCEPT/WARN/REJECT) + 실패 케이스 자동 PNG
- 카메라: Basler Blaze-112 (ToF depth) + Basler ace2 (RGB 5MP) eye-in-hand 동시 마운트

### 빈피킹 트랙 1 — 6DoF Pose 파이프라인

```mermaid
flowchart LR
    L1["L1: 영상 취득<br/>pypylon<br/>(Blaze-112 + ace2)"]
    L2["L2: 전처리<br/>Open3D<br/>(ROI, RANSAC)"]
    L3["L3: 분할<br/>DBSCAN"]
    L4["L4: 인식+자세<br/>FPFH + (Colored)ICP<br/>+ OBB SizeFilter"]
    L5["L5: 그래스프<br/>grasp_planner<br/>(29종 DB)"]
    L6["L6: 로봇 전송<br/>Modbus TCP<br/>(INT16)"]

    L1 --> L2 --> L3 --> L4 --> L5 --> L6

    classDef stage fill:#e8eaf6,stroke:#3f51b5,color:#000
    class L1,L2,L3,L4,L5,L6 stage
```

---

## 주요 기능

### Phase 1: 실시간 모니터링
- Formlabs Cloud API 폴링 → WebSocket 실시간 push
- 프린터 4대 그리드 대시보드 + 타임라인 간트 차트 + 상세 모달
- 프린트 이력 + 통계

### Phase 2: 원격 프린트 제어
- 파일 업로드 → 프리셋 저장 → 프린터로 전송 (PreFormServer)
- 프리셋 CRUD · readiness 체크 · 유효성/간섭 검사 · 대기 큐 · 알림벨
- 프린터 벤더 어댑터(`PRINTER_VENDOR`, 현재 formlabs)

### Phase 3: 자동화 셀 제어
- sequence_service: 단일 컨트롤러 스레드, 설비별 시퀀스(프린터·세척·경화·로봇), MariaDB 상태 전이
- Modbus TCP 8단계 핸드셰이크 (레지스터 130 명령 · 131~135 파라미터 · 150/151 · 200/206) — 명령표는 `sequence_service/README.md`
- 자동화 탭(CMD 생성·셀 START/STOP) + 수동제어 탭(DIO·Modbus·TCP 송신, 조작 기록 남김)

### Phase 4: 장비 상태 감시
- 세척기·경화기·건조기 신호를 **리모트 I/O**(PoE 이더넷 DI/DO, Modbus TCP)로 통합 수집 → 상태 전이 저장 → WebSocket 푸시
- Form Wash/Cure 는 제어 API 가 없으므로 장비 신호선·버튼을 리모트 I/O 에 결선해 완료/대기를 읽는다
- 엣지 AI 카메라(MaixCAM)는 보조 PoC — 화면 숫자 판독(OCR)·플레이트 유무 확인용

### Phase 5: 3D 빈피킹 비전 시스템

**트랙 2: YOLO 2D 인식 + Depth (현재 메인 트랙)**
- Roboflow annotation + augmentation 파이프라인
- **CAD 렌더 합성 데이터셋** — STEP/STL 부품을 다각도(기울임 × 회전) 자동 렌더링해 부품별 합성 이미지 생성 (trimesh + pyrender, 헤드리스). 실 촬영 데이터 보완 + 부품 클래스 확장용
- A100 GPU에서 다중 모델 비교 학습 (YOLOv8n/8m, YOLOv11s/m/l)
- 6요소 좌표 출력: x, y, z (depth), edge, angle, label
- ONNX 변환 + ONNXRuntime-GPU 배포 (산업용 PC)

**트랙 1: 6DoF Pose Estimation (인프라 보존 상태)**
- STL 29종 라이브러리 (FPFH 캐싱)
- Multi-resolution ICP (coarse-to-fine)
- Colored ICP 파이프라인
- OBB SizeFilter (회전 불변) + 포인트 비율 필터
- 핸드-아이 캘리브레이션 (eye-to-hand + eye-in-hand 2세트)
- E2E 실패 케이스 자동 시각화

### Phase 6: 라인 MES v2
- 관측 도메인 패키지 `line_mes/` (이벤트 4종 contract · state_engine · 토폴로지 적재 · 시뮬레이터)
- `/api/v2` 18 라우트: 읽기 R1~R12(노드 현황·반송자원·재공·투입 대기·랙 칸·FIFO 대기열·묶음·판정·명령 카탈로그·부품 마스터) + 쓰기 W1~W6(배치 분리·이동·상태·판정·조작 기록·로봇 명령). 읽기는 ETag/304.
- 프론트 전환 스위치는 서버 한 값: `/system/config.line_mes` (= `LINE_DSN` 유무). 꺼져 있으면 목업으로 동작.
- 기존 자동화 CMD 목록에 `line_tracked` 대조 — Spawn 누락 CMD를 바로 드러낸다.

### 웹앱 인프라
- systemd user service로 자동 시작 + 크래시 재시작 (공장 PC 는 NSSM 서비스 + `deploy.bat`)
- JWT 토큰 기반 인증 + React 로그인 페이지 + sliding refresh (HTTP + WebSocket + OpenAPI 문서 모두 보호)
- Cloudflare Tunnel을 통한 외부 접속 (내부 네트워크 비노출)
- 프린터 시리얼 단일 출처 `PRINTER_SERIAL_MAP` — web-api · sequence_service · topo_sync가 전부 여기서 읽는다

---

## 프론트엔드 UI (9탭)

| 탭 | 기능 |
|----|------|
| 모니터링 | 프린터 4대 그리드, 상태 필터, 타임라인 |
| 프린트 제어 | 프린터별 독립 컨테이너 (업로드·프리셋·프린트) |
| 대기 중인 작업 | 드래그앤드롭 순서 변경, 예약 시간 |
| 이전 작업 내용 | 로컬+클라우드 이력, 필터, CSV, 메모 |
| 통계 | 재료 도넛, 일별 바, 프린터별 가동률 |
| 자동화 | CMD 생성·프린터 할당·셀 제어·진행 상황 |
| 자동화 수동제어 | DIO·Modbus·TCP 수동 송신 (관리자용) |
| 라인 모니터링 | 노드 점유·반송자원 큐·재공 파이프라인 (v2 폴링) |
| 공정 제어 | 설비별 투입 대기·랙 칸·배치 분리·부품 판정·로봇 명령 (v2) |

> 자동화 두 탭은 공장 PC에서 시퀀스 서비스가 실행 중일 때, 라인 두 탭은 `LINE_DSN`이 설정됐을 때 실제 데이터로 동작한다. 그 외엔 각각 비활성/목업.

---

## 공정 흐름

| # | 공정 | 담당 |
|---|------|------|
| ① | STL 파일 업로드 | 사용자 (웹/앱) |
| ② | 프린터로 작업 전송 (+ 라인 MES `Spawn`) | 백엔드 (Local API) |
| ③ | 빌드플레이트 랙 → 프린터 투입 | HCR-12A |
| ④ | 3D 프린팅 | Form 4 |
| ⑤ | 프린팅 완료 감지 | 백엔드 (Web API 폴링 + 시퀀스 `cmd_status`) |
| ⑥~⑦ | 빌드플레이트 픽업 → 세척기 투입 (`Moved`) | HCR-12A |
| ⑧ | 세척 완료 감지 (`State`) | 리모트 I/O |
| ⑨ | 빌드플레이트 세척기 → 랙 투입 (`Moved`) | HCR-12A |
| ⑩ | 부품 분리 (`Split`) | 작업자 (공정 제어 탭) |
| ⑪ | 서포트 제거 | 작업자 |
| ⑫ | 경화기 투입 | 작업자 |
| ⑬ | 경화 완료 감지 (`State`) | 리모트 I/O |
| ⑭ | 치수 검사 | 광학계 (구축 중) |
| ⑮ | 빈피킹 → 드릴·트림 스테이션 이송 | HCR-10L + Blaze/ace2 |
| ⑯ | 양품/불량 판정 → 적재 | 작업자 / HCR-10L |
| ⑰ | 완료 보고 | 백엔드 (알림) |

---

## API 엔드포인트

전체 표는 `web-api/README.md`. `GET /api/v1/system/config` 가 프론트 설정의 단일 출처다 (`printer_serial_map` · `line_id` · `line_mes`).

### 인증
```
POST /api/v1/auth/login           # 로그인 → JWT (7일 sliding, 30일 절대 최대)
GET  /api/v1/auth/me              # 현재 세션
POST /api/v1/auth/logout
```

### Phase 1: Web API 모니터링
```
GET  /api/v1/dashboard                    # 4대 프린터 상태 요약
GET  /api/v1/printers                     # 프린터 목록
GET  /api/v1/printers/{serial}            # 특정 프린터 상태
GET  /api/v1/printers/{serial}/refresh    # 상태 즉시 새로고침
GET  /api/v1/printers/{serial}/prints     # 프린터별 이력
GET  /api/v1/prints                       # 프린트 이력 (필터)
GET  /api/v1/statistics                   # 통계
GET  /api/v1/system/token-status          # Formlabs 토큰 상태
GET  /api/v1/system/config                # 시스템 설정 (프린터 맵 · 라인 ID · 라인 MES on/off)
WS   /api/v1/ws                           # 실시간 업데이트
```

### Phase 2: Local API 원격 제어
```
GET    /api/v1/local/health
POST   /api/v1/local/printers/discover
CRUD   /api/v1/local/presets
POST   /api/v1/local/presets/{id}/print
POST   /api/v1/local/upload
GET    /api/v1/local/files
DELETE /api/v1/local/files/{filename}
CRUD   /api/v1/local/print                # 전송 성공 시 라인 MES Spawn 1건
CRUD   /api/v1/local/scene/*              # Scene + 모델 복제 + 유효성 + 간섭
GET    /api/v1/local/materials
POST   /api/v1/local/scene/{id}/screenshot
POST   /api/v1/local/scene/{id}/estimate-time
CRUD   /api/v1/local/notes
GET    /api/v1/local/notifications
POST   /api/v1/local/notifications/mark-read
```

### Phase 3: 자동화 셀 제어 (sequence_service 연동)
```
POST /api/v1/local/automation/commands            # Sequence CMD 생성
GET  /api/v1/local/automation/commands            # CMD 목록 (+ line_tracked 라인 MES 대조)
POST /api/v1/local/automation/commands/use
POST /api/v1/local/automation/control/{action}    # START / STOP / PAUSE / RESUME
POST /api/v1/local/automation/simul               # 시뮬 모드 토글
GET  /api/v1/local/automation/state | queues | logs
GET  /api/v1/local/automation/manual/io/state     # DIO 읽기
POST /api/v1/local/automation/manual/io/output    # DIO 쓰기 (관리자용 · 기록)
POST /api/v1/local/automation/manual/robot-send | vision-send
GET  /api/v1/local/automation/manual/robot-status | vision-status
GET/POST /api/v1/local/automation/manual/comm-config
GET  /api/v1/local/automation/manual/modbus/registers | write
```

### Phase 4: 장비 상태 감시
```
GET  /api/v1/vision/health
GET  /api/v1/vision/cameras[/{camera_id}]
GET  /api/v1/vision/devices[/{device_type}/{device_id}]   # 세척기/경화기 상태
GET  /api/v1/vision/events[/latest]                       # 상태 전이 이력
POST /api/v1/vision/simulate[/scenario]                   # 개발용
WS   /api/v1/vision/ws
```

### Phase 5: 빈피킹 결과 수신
```
POST /api/v1/binpick/reports                  # 인식 모듈 → 서버
GET  /api/v1/binpick/health
GET  /api/v1/binpick/scenes[/latest|/{pk}]    # 장면 목록·상세 (게이트 판정 필터)
WS   /api/v1/binpick/ws
```

### 라인 MES v2 (전부 JWT · 폴링 · 읽기는 ETag/304)
```
GET  /api/v2/lines/{line_id}/nodes | transporters | wip | control-menu   # R1~R4
GET  /api/v2/nodes/{node_id}/inbound | source-racks | groups | parts     # R5 R6 R9 R10
GET  /api/v2/racks/{node_id}/slots[/{slot_no}/queue]                     # R7 R8
GET  /api/v2/transporters/{id}/commands                                  # R11 명령 카탈로그
GET  /api/v2/parts                                                       # R12 부품 마스터
POST /api/v2/units/{unit_id}/split                                       # W1 배치 완료 → 부품 분리
POST /api/v2/moves                                                       # W2 이동
POST /api/v2/nodes/{node_id}/state                                       # W3 설비 상태
POST /api/v2/judgements                                                  # W4 부품 판정
POST /api/v2/commands                                                    # W5 조작 기록
POST /api/v2/transporters/{id}/commands/{command_id}                     # W6 로봇 명령 실행
```

### Formlabs API 사용 현황
- Web API: 6개 사용 (전체 19개) — 읽기 전용 모니터링
- Local API: 17개 사용 (전체 35개) — 프린트 전송·Scene 관리
- Webhook 미지원 → 폴링 방식
- Form Wash/Cure 제어 API 없음 → 리모트 I/O 신호로 완료 감지

---

## 프로젝트 구조

```
3D_printer_automation/
├── main.py                        # 통합 런처 (web-api + sequence_service)
├── requirements.txt               # 루트 의존성 (-e . 로 line_mes 포함) — deploy.bat 는 이것만 설치
├── pyproject.toml                 # line_mes 패키지 정의
├── deploy.bat                     # 공장 PC 1줄 배포
│
├── web-api/                       # API 층 (FastAPI)
│   ├── app/
│   │   ├── core/                  # 설정, Formlabs OAuth2, JWT 미들웨어
│   │   ├── api/                   # Phase 1 REST + WebSocket + 로그인
│   │   ├── local/                 # Phase 2 로컬 API + Phase 3 자동화 DB·DIO + 라인 발행
│   │   ├── adapters/              # 프린터 벤더 어댑터 (formlabs | demo)
│   │   ├── vision/                # Phase 4 상태 감시 (리모트 I/O · 카메라 PoC)
│   │   ├── binpick/               # Phase 5 인식 결과 수신
│   │   └── line/                  # 라인 MES v2 /api/v2 (routes_read · routes_write · publisher)
│   ├── .env.example
│   ├── Dockerfile / docker-compose.yml
│   └── README.md                  # 전체 라우트 표
│
├── line_mes/                      # 라인 MES 관측 도메인 (순수 파이썬 패키지)
│   ├── contract.py                # 이벤트 4종 (Spawn · State · Moved · Split)
│   ├── state_engine.py            # 이벤트 → product_state · 채번
│   ├── publish.py                 # 논블로킹 발행기
│   ├── schema.sql / schema.md     # PostgreSQL 테이블·뷰·트리거
│   ├── topology.yaml / topo_sync.py   # 라인·노드·경로 정의 → DB 적재
│   ├── simulator.py               # 이벤트 흘려 뷰 검증
│   └── tools/                     # dev_up.sh · dev_reset.sh
│
├── sequence_service/              # 제어 층 (공장 PC)
│   ├── app/cell/                  # runtime · sequences/ · modbus_protocol · line_events
│   ├── app/io/                    # Ajin IO (WinDLL)
│   └── README.md                  # 로봇암 이송 명령표
│
├── frontend/                      # React + Vite + TS + Tailwind CSS 4 (9탭)
│   └── src/{components, services/{api,localApi,lineApi,auth}.ts, mocks, types}
│
├── bin_picking/                   # Phase 5 3D 빈피킹
│   ├── src/                       # 트랙 1: 6DoF Pose Estimation
│   │   ├── acquisition/           # L1: realsense, basler, depth_to_pointcloud
│   │   ├── preprocessing/         # L2: cloud_filter (레진별 프리셋)
│   │   ├── segmentation/          # L3: dbscan_segmenter
│   │   ├── recognition/           # L4: cad_library, pose_estimator, size_filter
│   │   ├── grasping/              # L5: grasp_planner, grasp_database.yaml
│   │   ├── communication/         # L6: modbus_server
│   │   └── visualization/         # demo_ui, e2e_viz
│   ├── yolo_track/                # 트랙 2: YOLO 2D 인식 + Depth (현재 메인)
│   │   ├── pipeline/              # detect_and_output.py (6요소 좌표)
│   │   └── runs/                  # 학습 결과 (모델별 weights + metrics)
│   ├── scripts/
│   │   ├── demo_live_recognition.py
│   │   ├── basler_setup.sh
│   │   └── basler_smoke_test.py
│   ├── models/{cad, reference_clouds, fpfh_features}
│   ├── config/{resin_presets.py, grasp_database.yaml}
│   ├── tests/
│   └── tutorials/                 # Open3D 학습
│
├── factory-pc/file_receiver.py    # STL 파일 수신
├── scripts/                       # deploy_servers.sh · dev_develop.sh · smoke test
├── wireframe/                     # 라인 화면 와이어프레임 (Vite)
├── docs/                          # 설계·레퍼런스 (docs/juhee/ = 라인 MES v2 계획·설계·API 명세)
└── kaist_backup/                  # 동결 백업 (수정 금지)
```

---

## 기술 스택

### Backend
| 기술 | 용도 |
|------|------|
| Python 3.11+ · FastAPI · uvicorn | REST + WebSocket |
| httpx · pydantic-settings | Formlabs API 호출 · 환경변수 |
| SQLAlchemy + SQLite | web-api 로컬 DB |
| PyMySQL + MariaDB 11 | 자동화 제어 DB (sequence_service, 공장 PC) |
| psycopg 3 + PostgreSQL | 라인 MES 관측 DB (`line_mes/`) |
| pymodbus 3.x | 로봇 Modbus TCP 핸드셰이크 · 리모트 I/O 상태 감시 |
| aiomqtt | 엣지 AI 카메라 PoC (MQTT) |
| bcrypt + python-jose | JWT 로그인 |

### Frontend
React 18 · TypeScript 5 · Vite 5 · Tailwind CSS 4 · WebSocket (v1) / 폴링 + ETag (v2)

### 빈피킹 비전 (Phase 5)

**트랙 2 (YOLO)**: PyTorch 2.1 · Ultralytics 8.4.51 (YOLOv8/v11) · Roboflow (annotation + augmentation) · trimesh + pyrender (CAD 다각도 렌더 합성 데이터) · ONNX + ONNXRuntime-GPU (산업용 PC 배포)

**트랙 1 (6DoF)**: Open3D 0.19 · NumPy · OpenCV · trimesh · pypylon (Basler Blaze-112 + ace2) · pyrealsense2 (RealSense D435) · SciPy

**학습 인프라**: NVIDIA A100 80GB GPU · 컨테이너 환경

### Infrastructure
Docker · systemd --user · NSSM (Windows 서비스) · Cloudflare Tunnel · MQTT (Mosquitto, 카메라 PoC)

---

## 설치 및 실행

### 사전 요구사항
- Python 3.11+ · Node.js 18+
- (선택) Docker + docker-compose
- (라인 MES) PostgreSQL 14+
- (공장 PC) MariaDB 11 · PreFormServer · Windows

### 1. 환경 변수

`web-api/.env.example`을 복사해 `web-api/.env`를 만든다. **sequence_service도 같은 파일을 읽는다.**

```bash
# Formlabs Web API
FORMLABS_CLIENT_ID=your_client_id
FORMLABS_CLIENT_SECRET=your_client_secret

# 프린터 번호(1~4) ↔ 시리얼. 시리얼의 유일한 손 편집 지점
PRINTER_SERIAL_MAP={"1":"SERIAL1","2":"SERIAL2","3":"SERIAL3","4":"SERIAL4"}

# PreFormServer / 파일 수신
PREFORM_SERVER_HOST=127.0.0.1
PREFORM_SERVER_PORT=44388
FILE_RECEIVER_HOST=127.0.0.1
FILE_RECEIVER_PORT=8089

# 라인 MES v2 — 비우면 v2 전체 no-op. 비번은 DSN 에 넣지 말고 PGPASSWORD/.pgpass 로
LINE_DSN=
LINE_ID=RESIN-1-ASIS     # topology.yaml 의 active 라인과 같아야 한다

# 사용자 로그인 (JWT) — 셋 다 비면 인증 OFF (로컬 개발용)
AUTH_USERNAME=your_username
AUTH_PASSWORD_HASH=      # python -c "import bcrypt; print(bcrypt.hashpw(b'pw', bcrypt.gensalt(rounds=12)).decode())"
JWT_SECRET=              # python -c "import secrets; print(secrets.token_urlsafe(32))"
```

> **⚠️ `.env`는 절대 커밋하지 마세요.** credentials·IP·시리얼·경로는 로컬 설정 파일에서만 관리합니다.

### 2. 라인 MES DB (선택)

```bash
psql -f line_mes/schema.sql
python -m line_mes.topo_sync --check     # --plan → --apply
python -m line_mes.simulator             # 이벤트를 흘려 뷰 검증 (개발용)
# 이후 .env 의 LINE_DSN 을 채우면 v2 라우트·발행·프론트 라인 탭이 함께 켜진다
```

### 3. 실행

**방법 1: Docker** (web-api 만)
```bash
cd web-api
docker-compose up -d
```

**방법 2: 직접 실행**

백엔드 (web-api + sequence_service — 리포 루트에서):
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # line_mes 가 -e . 로 함께 설치된다
python main.py                   # web-api :8085 + sequence_service
```

web-api 만:
```bash
cd web-api
python -m venv venv
source venv/bin/activate         # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8085
```

프론트엔드 (개발):
```bash
cd frontend
npm install
npm run dev                      # :5180 → API 프록시 :8085
```

프론트엔드 (프로덕션 빌드):
```bash
cd frontend
npm run build
# dist/ 가 web-api에서 정적 서빙됨
```

개발용 포트 분리 (vite 5181 → web-api 8086, main 5180/8085 와 병행):
```bash
./scripts/dev_develop.sh
```

### 4. 빈피킹 데모

```bash
# 트랙 1 (6DoF Pose) — synthetic 씬 렌더 검증
python bin_picking/scripts/demo_live_recognition.py \
  --synthetic --test-render /tmp/demo.png

# 트랙 1 — RealSense D435 라이브
python bin_picking/scripts/demo_live_recognition.py --realsense

# 트랙 1 — Basler 라이브
python bin_picking/scripts/demo_live_recognition.py --basler

# 트랙 2 (YOLO) — 단일 이미지 → 6요소 좌표 출력
python bin_picking/yolo_track/pipeline/detect_and_output.py \
  --model path/to/best.pt --image path/to/scene.jpg --format yaml

# 트랙 2 — ONNX 변환 (산업용 PC 배포 준비)
yolo export model=path/to/best.pt format=onnx imgsz=640
```

---

## 문서

| 위치 | 내용 |
|---|---|
| `web-api/README.md` | 전체 라우트 표 (v1 61 + v2 18) |
| `sequence_service/README.md` | 로봇암 이송 명령표 · 레지스터 |
| `line_mes/README.md` · `schema.md` | 관측 도메인 파일 역할 · DB 스키마 |
| `docs/juhee/` | 라인 MES v2 조사 → 계획 → 설계 정본 → API 명세 → 와이어프레임 → FE 병합 |
| `docs/juhee/03_MES_v2_설계/서비스_역할_구조.md` | 세 서비스 역할·DB 소유·의존 방향 한 장 |
| `bin_picking/docs/README.md` | 빈피킹 절차서 색인 (현행 / 완료 기록 / 종료) |

---

## 라이선스

내부 프로젝트 (Private)

---

_Last updated: 2026-10-02_
