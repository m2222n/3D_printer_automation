# 3D Printer Automation System

> 3D프린터-로봇 연동 자동화 시스템 | Formlabs Form 4 + HCR 협동로봇 + 3D 빈피킹 비전 + MaixCAM

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)](https://vitejs.dev)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![Open3D](https://img.shields.io/badge/Open3D-0.19-4B8BBE?logo=python&logoColor=white)](http://www.open3d.org)
[![Modbus](https://img.shields.io/badge/Modbus_TCP-pymodbus_3-FF6F00?logo=python&logoColor=white)](https://pymodbus.readthedocs.io)
[![trimesh](https://img.shields.io/badge/trimesh-4.x-green?logo=python&logoColor=white)](https://trimesh.org)
[![Basler](https://img.shields.io/badge/Basler-pypylon-0078D4?logoColor=white)](https://www.baslerweb.com)
[![RealSense](https://img.shields.io/badge/Intel_RealSense-D435-0071C5?logo=intel&logoColor=white)](https://www.intelrealsense.com)
[![SciPy](https://img.shields.io/badge/SciPy-1.x-8CAAE6?logo=scipy&logoColor=white)](https://scipy.org)
[![MQTT](https://img.shields.io/badge/MQTT-Mosquitto-660066?logo=mqtt&logoColor=white)](https://mosquitto.org)
[![WireGuard](https://img.shields.io/badge/WireGuard-VPN-88171A?logo=wireguard&logoColor=white)](https://www.wireguard.com)
[![Cloudflare](https://img.shields.io/badge/Cloudflare-Tunnel-F38020?logo=cloudflare&logoColor=white)](https://www.cloudflare.com)

---

## 프로젝트 개요

점자프린터 플라스틱 부품(약 29종) 생산 공정을 자동화하는 시스템입니다.

| 항목 | 내용 |
|------|------|
| 회사 | 오리누 주식회사 (구 플릭던) |
| 사업 | 2025년 경기도 제조로봇 이니셔티브 (사업비 2억원) |
| 사업 기간 | 협약일 ~ 2025.12.31 |
| 담당 개발자 | 정태민 (1인 개발) |
| 협업 | 한솔코에버 (로봇·시퀀스 서비스 개발, 이예승 사원) |

### 목표
- **1차 목표**: 웹/앱에서 프린터 실시간 모니터링 + 원격 프린트 전송
- **궁극적 목표**: 3D프린터 + 로봇 + 3D 비전(빈피킹) + 엣지 AI(MaixCAM)를 통합한 완전 자동화 생산 라인 → SaaS 플랫폼화

### 하드웨어 구성

| 장비 | 모델 | 수량 | 용도 | 상태 |
|------|------|------|------|------|
| 3D 프린터 | Formlabs Form 4 | 4대 | SLA 레진 프린팅 | ✅ 전체 운용 중 (4/3 ShrewdStork 헤드커버 수리 완료) |
| 협동로봇 | HCR-12 | 1대 | 빌드플레이트 교체, 세척기 투입 | 현장 배치 |
| 협동로봇 | HCR-10L | 1대 | 후가공 탭, 제품 이송 | 현장 배치, 4/14 펜던트 교육 1회차 수료 |
| 세척기 | Form Wash | 2대 | 레진 세척 | ✅ |
| 경화기 | Form Cure | 2대 | UV 경화 | ✅ |
| 3D 카메라 | Basler Blaze-112 (ToF) | 1대 | 빈피킹 Depth 취득 | 🚚 **2026-04-23 도착 예정** |
| 2D 카메라 | Basler ace2 5MP | 1대 | 빈피킹 RGB 취득 | 🚚 **2026-04-23 도착 예정** |
| 깊이 카메라 | Intel RealSense D435 | 1대 | 빈피킹 임시 검증 (USB 20cm 제약) | ✅ 라이브 연동 성공 (4/13) |
| 엣지 AI 카메라 | Sipeed MaixCAM | 1+대 | 세척기/경화기 완료 감지 (OpenMV 대체) | 🔄 리서치 완료, PoC 대기 |

> **참고**: 4/14 대표님 지시로 기존 OpenMV AE3 → Sipeed MaixCAM 전환. MaixCAM이 RISC-V + 1 TOPS NPU + WiFi 6로 성능 우위.

---

## 개발 단계

### Phase별 상태

| Phase | 항목 | 우선순위 | 상태 |
|-------|------|----------|------|
| **Phase 1** | Web API 모니터링 (Formlabs Cloud) | 🔴 URGENT | ✅ 완료 |
| **Phase 2** | Local API 원격 프린트 제어 + 프론트엔드 UI | 🔴 URGENT | ✅ 완료 |
| **Phase 3** | HCR 로봇 연동 + 시퀀스 서비스 | 🟡 HIGH | ✅ 한솔코에버 코드 2회 머지(4/3, 4/16). 3/27 최종 시연 완료 |
| **Phase 4** | 장비 모니터링 (MaixCAM — OpenMV 대체) | 🟡 HIGH | 🔄 리서치 완료, 빈피킹 우선 후 PoC |
| **Phase 5** | 3D 빈피킹 비전 시스템 | 🔴 URGENT | 🔄 W6 — L1~L6 SW 완성 + 데모 UI 안정화, Basler 4/23 입고 대기 |

### 현재 상태 (2026-04-22 저녁)

#### ✅ 완료된 것
- Phase 1 + Phase 2 **프로덕션 운영 중** (카카오 VM + 6000 서버)
- Phase 3 한솔코에버 코드 메인 머지 완료 (`sequence_service` + Automation/Automation_Manual UI)
- Phase 5 **L1~L6 파이프라인 SW 완성** + 그래스프 DB 29종 + 데모 UI 안정화
  - 인식률: easy 100%, crowded 90%, hard 60% (FPFH 한계, Colored ICP 준비됨)
  - 매칭 시간: 0.4~0.6s/부품
  - 데모 UI 2×2 그리드 + 3상태 색상 코딩 (ACCEPT/WARN/REJECT), synthetic 리허설 1.5s
- WireGuard VPN 안정화 (4/17 복구)
- 카카오 VM 이전 + Basic Auth (4/16)
- 레진 프리셋 SSOT 4종 (grey/white/clear/flexible)
- Basler 설치 자동화 스크립트 (카메라 도착 당일 3시간 → 1시간 단축 예상)

#### 🔄 진행 중
- Basler Blaze-112 + ace2 입고 준비 (4/23 목요일 도착)
- Cloudflare Tunnel (`factory.flickdone.com`) — 대표님 계정 초대 대기
- sequence_service 배포 정책 — 4/23 이예승 사원 미팅 예정

#### ⏳ 대기
- 실제 핸드-아이 캘리브레이션 2세트 (eye-to-hand + eye-in-hand) — 카메라 입고 후
- Colored ICP 실데이터 검증 (코드 준비 완료)
- HCR-10L 실전 피킹 + 그리퍼 장착 후 TCP 오프셋·작업 영역 실측
- MaixCAM 장비 모니터링 PoC

---

## 시스템 아키텍처

### 서버 구성

```
┌──────────────────────────────────────────────────────────────┐
│ 브라우저 (태민 노트북 / 예승 노트북 / 공장 PC)                 │
└──────────────┬───────────────────────────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
       ▼                ▼
┌──────────────┐  ┌──────────────┐
│ 카카오 VM    │  │ 6000 서버     │
│ 61.109.*:8085│  │ 106.244.*:8085│
│              │  │              │
│ web-api만    │  │ web-api +    │
│ (모니터링)   │  │ 프린터 제어   │
│ Basic Auth   │  │ (VPN 경유)   │
└──────────────┘  └──────┬───────┘
                         │ WireGuard
                         ▼
              ┌─────────────────────────┐
              │ 공장 PC (Windows)       │
              │ 10.145.113.3            │
              │                         │
              │ • PreFormServer :44388  │
              │ • file_receiver :8089   │
              │ • sequence_service      │
              │ • HCR-10L, Ajin IO      │
              │ • MySQL (자동화 로그)    │
              └─────────────────────────┘
                         │
                         ▼
              ┌─────────────────────────┐
              │ Form 4 ×4, HCR-12/10L,  │
              │ Form Wash/Cure,         │
              │ Basler (4/23 입고),     │
              │ MaixCAM                 │
              └─────────────────────────┘
```

### 운영 서버 현황

| 서버 | URL | 역할 | 상태 |
|------|-----|------|------|
| 카카오 VM | `http://61.109.239.142:8085/` | 모니터링 (Cloud API 폴링) | ✅ Basic Auth |
| 6000 서버 | `http://106.244.6.242:8085/` | 모니터링 + 프린터 제어 (VPN) | ✅ 병행 운영 |
| 6000 서버 SSH | - | 개발 환경 (Claude Code, git) | ✅ |
| Mac (로컬) | - | 빈피킹 개발 (Open3D — 6000 서버는 AVX2 미지원) | ✅ |
| 공장 PC | AnyDesk | PreFormServer + file_receiver + sequence_service + MySQL | ✅ |

> **접속**: 현시점 기준 `admin` / `orinu2026!` (Basic Auth). Cloudflare Tunnel 적용 후 로그인 페이지 + JWT로 업그레이드 예정.

### 빈피킹 비전 파이프라인 (Phase 5)

```
L1 영상 취득       → L2 전처리          → L3 분할           → L4 인식+자세        → L5 그래스프     → L6 로봇 전송
  pypylon           Open3D              DBSCAN              FPFH+RANSAC+        grasp_planner     Modbus TCP
  (Blaze-112 +      (ROI, 이상치,       (클러스터링)         (Colored) ICP       (29종 DB)        (INT16, Reg 130~)
  ace2 듀얼 캡처)    다운샘플, RANSAC)                        + OBB SizeFilter
```

- 모든 단계 Python 단독 구현, CAD 기반 인식 (STL 29종)
- 레진별 프리셋 4종 (grey/white/clear/flexible) 일관 적용
- 데모 시각화: 2×2 그리드 + 3상태 색상 코딩

---

## 주요 기능

### Phase 1: 실시간 모니터링

- Formlabs Cloud API 15초 폴링 → WebSocket 실시간 push
- 프린터 4대 그리드 대시보드 + 상태 필터
- 타임라인 간트 차트 + 프린터 상세 모달 (Details/Settings/Services 3탭)
- 프린트 이력 + 통계 (재료 도넛, 일별 바차트, 프린터별 가동률)

### Phase 2: 원격 프린트 제어

- 파일 업로드 → 프리셋 저장 → 프린터로 전송
- 프리셋 CRUD (프린터별 독립 관리, 4/16 예승님 머지 이후)
- 프린트 readiness 체크 (6가지 검증 + 경고 배너)
- 프린트 전 유효성/간섭 검사, 내부 비우기(레진 절약), 시간 예측
- 대기 중/히스토리 큐 + 드래그앤드롭 순서 변경
- 알림벨 (30초 폴링, 드롭다운)

### Phase 3: HCR 로봇 연동 (한솔코에버 주도 개발)

- Modbus TCP (pymodbus 3.x) — HCR-10L 실스펙 INT16 매핑
- 비전PC→로봇: Reg 130(CMD) / 131(부품ID) / 132~137(XYZ Rxyz INT16 1/10mm,1/10deg) / 138~139(그리퍼) / 140(시퀀스)
- 로봇→비전PC: Reg 150(ROBOT_STATE) / 151(seq echo)
- HCR-10L 내장 (읽기): Reg 400~405(TCP 좌표) / 600(Program State) / 700~702(Command)
- 자동화 시퀀스: Automation 탭(CMD 생성) + Automation_Manual(수동 제어)
- 공장 PC 전용 실행 (Ajin IO + WinDLL 물리 의존)

### Phase 5: 3D 빈피킹 비전 시스템 (L1~L6 SW 완성)

- STL 29종 라이브러리 (cad_library.py FPFH 캐싱)
- Multi-resolution ICP (4mm → 2mm → 1mm coarse-to-fine)
- Colored ICP 파이프라인 (카메라 입고 후 검증)
- OBB SizeFilter (회전 불변) + 포인트 비율 필터
- 레진 프리셋 SSOT (L2 전처리 + L4 판정 임계값 일관 적용)
- 핸드-아이 캘리브레이션 (eye-to-hand + eye-in-hand 2세트 설계)
- 데모 라이브 인식 UI (2×2 그리드, ACCEPT/WARN/REJECT 색상 코딩)
- E2E 시각화 (실패 케이스 자동 저장)

### 웹앱 인프라
- systemd user service (`formlabs-web.service`) — 자동 시작 + 크래시 시 자동 재시작
- Raw ASGI Basic Auth 미들웨어 (HTTP + WebSocket)
- pymysql + Ajin WinDLL Linux 호환 가드

---

## 프론트엔드 UI (5탭 + 자동화 + 알림벨)

| 탭 | 컴포넌트 | 기능 |
|----|----------|------|
| **모니터링** | Dashboard.tsx | 프린터 4대 그리드 카드, 상태 필터, 타임라인 |
| **프린트 제어** | PrintPage.tsx | 프린터별 독립 컨테이너 (업로드·프리셋·프린트) |
| **대기 중인 작업** | QueuePage.tsx | 드래그앤드롭 순서 변경, 예약 시간 |
| **이전 작업 내용** | HistoryPage.tsx | 로컬+클라우드 이력, 필터, CSV, 메모 |
| **통계** | StatisticsPage.tsx | 재료 도넛, 일별 바, 프린터별 가동률 |
| **Automation** | AutomationPage.tsx | 자동화 CMD 생성·프린터 할당·진행 상황 (한솔코에버) |
| **Automation_Manual** | AutomationManualPage.tsx | 수동 제어 (한솔코에버) |
| 🔔 알림벨 | App.tsx | 미읽음 뱃지, 드롭다운, 30초 폴링 |

> **유의**: Automation / Automation_Manual 탭은 **공장 PC에서 sequence_service가 실행 중일 때만** 실제 동작합니다. 카카오 VM / 6000 서버에는 sequence_service 백엔드가 없어 UI만 보이고 동작하지 않습니다. (4/23 예승님 미팅에서 원격 정책 합의 예정)

---

## 16단계 공정 흐름

| # | 공정 | 담당 |
|---|------|------|
| ① | STL 파일 업로드 | 사용자 (웹/앱) |
| ② | 프린터로 작업 전송 | 백엔드 (Local API) |
| ③ | 3D 프린팅 | Form 4 (4대) |
| ④ | 프린팅 완료 감지 | 백엔드 (Web API 폴링) |
| ⑤~⑥ | 빌드플레이트 픽업 → 세척기 투입 | HCR-12 |
| ⑦ | 세척 완료 감지 | MaixCAM #1, #2 |
| ⑧ | 경화기 투입 | HCR-12 |
| ⑨ | 경화 완료 감지 | MaixCAM #3, #4 |
| ⑩~⑫ | 픽업 → 서포트 제거 → 후가공 | HCR-10L |
| ⑬ | 3D 빈피킹 + 비전 검사 | Basler Blaze-112 + ace2 |
| ⑭~⑮ | 양품/불량 분류 → 적재 | HCR-10L |
| ⑯ | 완료 보고 | 백엔드 (알림) |

---

## API 엔드포인트

### Phase 1: Web API 모니터링 (11 routes)
```
GET  /api/v1/dashboard            # 4대 프린터 상태 요약
GET  /api/v1/printers             # 프린터 목록
GET  /api/v1/printers/{serial}    # 특정 프린터 상태
GET  /api/v1/prints               # 프린트 이력 (필터)
GET  /api/v1/statistics           # 통계
WS   /api/v1/ws                   # 실시간 업데이트
```

### Phase 2: Local API 원격 제어 (32 routes)
```
GET    /api/v1/local/health
POST   /api/v1/local/printers/discover
CRUD   /api/v1/local/presets            # 프리셋 관리
POST   /api/v1/local/presets/{id}/print # 프리셋으로 프린트
POST   /api/v1/local/upload
GET    /api/v1/local/files
CRUD   /api/v1/local/print              # 프린트 작업
CRUD   /api/v1/local/scene/*            # Scene + 모델 복제 + 유효성 + 간섭
GET    /api/v1/local/materials
POST   /api/v1/local/scene/{id}/screenshot
POST   /api/v1/local/scene/{id}/estimate-time
CRUD   /api/v1/local/notes
GET    /api/v1/local/notifications
```

---

## Formlabs API 사용 현황

| 구분 | 전체 | 사용 중 | 사용률 |
|------|------|--------|--------|
| Web API | 19개 | 6개 | 32% |
| Local API | 35개 | 17개 | 49% |
| **합계** | **54개** | **23개** | **43%** |

- Web API: **읽기 전용** (모니터링만)
- Local API: **제어 가능** (프린트 전송, Scene 관리)
- API 한계: Webhook 미지원 → 15초 폴링, Form Wash/Cure 제어 불가 → MaixCAM 카메라로 완료 감지

---

## 프로젝트 구조

```
3D_printer_automation/
├── CLAUDE.md                      # 프로젝트 상태 문서
├── CLAUDE.local.md                # 세션별 작업 이력 (git 제외)
├── README.md                      # 이 파일
│
├── docs/                          # 설계 문서 + 회의록
│   ├── Phase1_WebAPI_개발설계서.docx
│   ├── Phase2_LocalAPI_아키텍처설계.md
│   ├── Phase4_OpenMV_개발설계서.md
│   ├── binpicking_summary.md
│   ├── meeting_0422.md
│   ├── meeting_0423_sequence_service.md   # 4/23 예승님 미팅용
│   ├── basler_download_checklist.md
│   └── WireGuard_LAN_VPN_연결_가이드.md
│
├── web-api/                       # 백엔드 (FastAPI, Phase 1+2)
│   ├── app/
│   │   ├── main.py                # 앱 진입점
│   │   ├── core/                  # 설정, OAuth2, Basic Auth 미들웨어
│   │   ├── services/              # Formlabs 클라이언트, 폴링, 알림
│   │   ├── api/routes.py          # Phase 1 REST + WebSocket
│   │   ├── local/                 # Phase 2 로컬 API (32 routes)
│   │   └── schemas/               # Pydantic 모델
│   ├── data/local.db              # SQLite
│   └── Dockerfile / docker-compose.yml
│
├── frontend/                      # React + Vite + TS + Tailwind CSS 4
│   └── src/{components, services, types}
│
├── sequence_service/              # Phase 3 한솔코에버 시퀀스 런타임 (Windows 전용)
│   ├── app/cell/                  # 시퀀스, Modbus, 로봇/프린터 제어
│   ├── app/core/config.py         # SIMUL_MODE, AJIN_SIMULATION, Modbus 레지스터 매핑
│   ├── app/db/                    # MySQL 모델/세션
│   ├── app/io/                    # Ajin IO (AXL.dll, WinDLL)
│   └── app/main.py                # 서비스 진입점
│
├── main.py                        # 통합 런처 (web-api + sequence_service, 공장 PC용)
│
├── factory-pc/
│   └── file_receiver.py           # STL 파일 수신 (포트 8089)
│
├── bin_picking/                   # Phase 5 3D 빈피킹
│   ├── src/
│   │   ├── acquisition/           # L1: realsense_capture, basler_capture, depth_to_pointcloud
│   │   ├── preprocessing/         # L2: cloud_filter (레진별 프리셋)
│   │   ├── segmentation/          # L3: dbscan_segmenter
│   │   ├── recognition/           # L4: cad_library, pose_estimator, size_filter (OBB)
│   │   ├── grasping/              # L5: grasp_planner, grasp_database.yaml
│   │   ├── communication/         # L6: modbus_server (INT16, Reg 130~)
│   │   └── visualization/         # demo_ui, e2e_viz
│   ├── scripts/
│   │   ├── demo_live_recognition.py   # 시연 데모 (2×2 그리드)
│   │   ├── basler_setup.sh            # 현장 설치 자동화
│   │   └── basler_smoke_test.py       # 9단계 스모크 테스트
│   ├── models/{cad, reference_clouds, fpfh_features}
│   ├── config/{resin_presets.py, grasp_database.yaml}
│   ├── tests/                     # E2E (Redwood, 29종 CAD, D435)
│   └── tutorials/                 # Open3D 학습 01~11
│
├── OpenMV/                        # (참고자료, MaixCAM으로 전환됨)
├── robot-control/                 # Phase 3 로봇 제어 (legacy)
├── vision/                        # Phase 4 비전 검사 (legacy)
└── shared/                        # 공유 유틸리티 (미구현)
```

---

## 기술 스택

### Backend
| 기술 | 버전 | 용도 |
|------|------|------|
| Python | 3.11+ | 런타임 |
| FastAPI | 0.109+ | REST + WebSocket |
| uvicorn | 0.27+ | ASGI 서버 |
| httpx | 0.26+ | Formlabs API 호출 |
| pydantic-settings | 2.1+ | 환경변수 로드 |
| SQLAlchemy + SQLite | 2.0+ | 로컬 DB (web-api) |
| PyMySQL | 1.1+ | MySQL (sequence_service) |
| pymodbus | 3.6+ | Modbus TCP |
| aiomqtt | 2.0+ | MQTT 비동기 클라이언트 (Phase 4) |
| python-multipart | 0.0.6+ | 파일 업로드 |

### Frontend
| 기술 | 버전 | 용도 |
|------|------|------|
| React | 18.3 | SPA |
| TypeScript | 5.6 | 타입 시스템 |
| Vite | 5.4 | 개발 서버 + 빌드 |
| Tailwind CSS | 4.0 (beta) | 스타일링 |
| WebSocket | 네이티브 | 실시간 업데이트 |

### 빈피킹 비전 (Phase 5)
| 기술 | 버전 | 용도 |
|------|------|------|
| Open3D | 0.19 | 포인트 클라우드 처리 (Mac/공장 PC — 6000 서버는 AVX2 미지원) |
| NumPy | 1.26+ | 수치 계산 |
| OpenCV | 4.8+ | 이미지 처리 + UI 렌더 |
| trimesh | 4.x | STL 로드 |
| pypylon | 26.x | Basler 카메라 |
| pyrealsense2 | 2.57 | Intel RealSense D435 |
| SciPy | 1.x | 회전/정합 수학 |

### Infrastructure
| 기술 | 용도 |
|------|------|
| Docker + docker-compose | 웹앱 컨테이너화 |
| WireGuard VPN | 6000 서버 ↔ 공장 PC |
| Cloudflare Tunnel | (준비 중) `factory.flickdone.com` 외부 노출 |
| systemd --user | formlabs-web 자동 시작 |
| Mosquitto MQTT | MaixCAM ↔ 백엔드 (Phase 4) |

---

## 설치 및 실행

### 사전 요구사항
- Python 3.11+
- Node.js 18+
- (선택) Docker + docker-compose
- 빈피킹 개발은 Open3D 호환 CPU(AVX2) 필요 — 6000 서버 대신 Mac 또는 공장 PC 권장

### 환경 변수 설정

`web-api/.env.example`을 복사해 `.env` 생성:
```bash
# Formlabs Web API
FORMLABS_CLIENT_ID=your_client_id
FORMLABS_CLIENT_SECRET=your_client_secret

# PreFormServer (공장 PC VPN)
PREFORM_SERVER_HOST=10.145.113.3
PREFORM_SERVER_PORT=44388

# 공장 PC 파일 수신
FILE_RECEIVER_HOST=10.145.113.3
FILE_RECEIVER_PORT=8089

# 폴링
POLLING_INTERVAL_SECONDS=15

# Basic Auth (공인 IP 노출 시)
BASIC_AUTH_USERNAME=admin
BASIC_AUTH_PASSWORD=your_password
```

### 방법 1: Docker로 실행 (권장)
```bash
cd web-api
docker-compose up -d
# 프론트엔드 dist 빌드 후 SPA 서빙됨
```

### 방법 2: 직접 실행

**백엔드**:
```bash
cd web-api
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8085
```

**프론트엔드 (개발)**:
```bash
cd frontend
npm install
npm run dev
```

**프론트엔드 (프로덕션 빌드)**:
```bash
cd frontend
npm run build
# dist/ 가 web-api에서 정적으로 서빙됨
```

**공장 PC — 통합 런처 (sequence_service + web-api)**:
```cmd
cd C:\3D_printer_automation
python main.py
```
> 공장 PC는 Ajin IO (Windows WinDLL) + HCR-10L + MySQL + PreFormServer 의존.
> 4/23 예승님과 배포 디렉토리·자동 시작 방식 합의 예정.

### 접속

| 환경 | URL |
|------|-----|
| 카카오 VM | http://61.109.239.142:8085/ |
| 6000 서버 | http://106.244.6.242:8085/ |
| 로컬 개발 | http://localhost:8085/ (또는 5173 — Vite dev) |
| Cloudflare Tunnel (예정) | https://factory.flickdone.com/ |

### 빈피킹 데모 실행 (Mac / 공장 PC)

```bash
# synthetic 씬 렌더 검증 (~1.5s)
.venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py \
  --synthetic --test-render /tmp/demo.png

# RealSense D435 근접 테스트 (USB 20cm 제약 대응)
sudo .venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py \
  --realsense --roi-z-min 0.02 --roi-z-max 0.30 \
  --depth-min 0.02 --depth-max 0.50

# Basler 라이브 (4/23 이후)
sudo .venv/binpick/bin/python bin_picking/scripts/demo_live_recognition.py --basler
```

---

## 확인된 프린터 (4대)

| 이름 | 시리얼 | IP | 비고 |
|------|--------|-----|------|
| CapableGecko | Form4-CapableGecko | 192.168.219.46 | Grey V5 |
| HeavenlyTuna | Form4-HeavenlyTuna | 192.168.219.48 | Clear V5 |
| CorrectPelican | Form4-CorrectPelican | 192.168.219.43 | Flexible 80A V1.1 |
| ShrewdStork | Form4-ShrewdStork | 192.168.219.45 | ✅ 운용 중 (4/3 헤드커버 수리 완료) |

---

## 최근 주요 마일스톤

| 날짜 | 마일스톤 |
|------|----------|
| 2026-02-12 | 대표님 데모 성공 (Phase 2 UI) |
| 2026-03-12 | 화성시 디지털 가속성장 발표평가 |
| 2026-03-20 | 데모 시연 (경기ITP-코에버 3자 최종 확인) |
| 2026-03-27 | 한솔코에버 최종 시연 |
| 2026-04-03 | 한솔 머지 1차 (`9c161dc`) — 김기원 주임 코드 |
| 2026-04-08 | 빈피킹 L1~L6 SW 파이프라인 완성 (일정 4주 앞당김) |
| 2026-04-13 | RealSense D435 라이브 연동 + E2E 시각화 |
| 2026-04-14 | HCR-10L 로봇 교육 1회차 + D435 Full Pipeline PASS |
| 2026-04-15 | Modbus INT16 재설계 + Colored ICP + Basler 듀얼 캡처 모듈 |
| 2026-04-16 | 한솔 머지 2차 (`e68c2b1`) — 이예승 사원 프린터 할당 + 카카오 VM 이전 |
| 2026-04-21 | 도메인 확정 (`factory.flickdone.com`) + Basler 설치 자동화 + 레진 프리셋 SSOT |
| 2026-04-22 | 데모 리허설 피드백 6건 반영 (synthetic 9.7s → 1.5s) |
| **2026-04-23** | **Basler 입고 + 예승님 sequence_service 배포 미팅** |

---

## 라이선스

내부 프로젝트 (Private)

## 문의

- **개발자**: 정태민 (jtm@flickdone.com)
- **회사**: 오리누 주식회사 (구 플릭던)
- **리포지토리**: https://github.com/orinu-ai/3D_printer_automation (Private, 한솔 협업 미러: https://github.com/m2222n/3D_printer_automation)
