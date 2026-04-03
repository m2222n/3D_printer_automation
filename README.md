# 3D Printer Automation System

> 3D프린터-로봇 연동 자동화 시스템 | Formlabs Form 4 + HCR 협동로봇 + 3D 빈피킹 비전 + OpenMV

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://docker.com)
[![Open3D](https://img.shields.io/badge/Open3D-0.19-4B8BBE?logo=python&logoColor=white)](http://www.open3d.org)

---

## 프로젝트 개요

점자프린터 플라스틱 부품(약 30종) 생산 공정을 자동화하는 시스템입니다.

| 항목 | 내용 |
|------|------|
| 회사 | 오리누 주식회사 |
| 사업 | 2025년 경기도 제조로봇 이니셔티브 |
| 담당 개발자 | 정태민 |
| 협업 | 한솔코에버 (로봇 연동, 담당: 이예승 사원) |

### 목표
- **1차 목표**: 웹에서 프린터 실시간 모니터링 + 원격 프린트 전송
- **궁극적 목표**: 3D프린터 + 로봇 + 3D 비전(빈피킹) + OpenMV를 통합한 완전 자동화 생산 라인 → SaaS 플랫폼화

### 하드웨어 구성

| 장비 | 모델 | 수량 | 용도 |
|------|------|------|------|
| 3D 프린터 | Formlabs Form 4 | 4대 | SLA 레진 프린팅 |
| 협동로봇 | HCR-12 | 1대 | 빌드플레이트 교체, 세척기 투입 |
| 협동로봇 | HCR-10L | 1대 | 후가공 탭, 제품 이송 |
| 세척기 | Form Wash | 2대 | 레진 세척 |
| 경화기 | Form Cure | 2대 | UV 경화 |
| 3D 카메라 | Basler Blaze-112 (ToF) | 1대 | 빈피킹 Depth 취득 |
| 2D 카메라 | Basler ace2 5MP | 1대 | 빈피킹 RGB 취득 |
| 깊이 카메라 | Intel RealSense D435 | 1대 | RGB-D 스테레오 (빈피킹 보조/테스트) |
| 비전 카메라 | OpenMV AE3 | 4대 (예정) | 세척기/경화기 완료 감지 |

---

## 개발 단계

| Phase | 항목 | 상태 | 설명 |
|-------|------|------|------|
| **Phase 1** | Web API 모니터링 | ✅ 완료 | Formlabs Cloud API, 실시간 대시보드, WebSocket |
| **Phase 2** | Local API 원격 제어 + UI | ✅ 완료 | PreFormServer 연동, 5탭 UI, 슬라이스/통계/알림 |
| **Phase 3** | HCR 로봇 연동 | ✅ 코드 머지 완료 | 한솔코에버 시퀀스 서비스 + 자동화 프론트엔드 통합 |
| **Phase 4** | OpenMV + YOLO 비전 검사 | 🔄 진행 중 (일시 대기) | WiFi+MQTT E2E 성공, 학습 이미지 350장 — 빈피킹 우선 |
| **Phase 5** | 3D 빈피킹 비전 시스템 | 🔄 진행 중 | Basler Blaze-112 + ace2, 30종 부품 6DoF 인식, 파이프라인 SW 구현 |

### 현재 상태 (2026-04-03)
- **Phase 1 + 2 완료**: 웹 모니터링 + 원격 프린트 제어 + 5탭 UI 전체 구현
- **Phase 3 머지 완료**: 한솔코에버 시퀀스 서비스(sequence_service/) + 자동화 UI 통합, 3/27 최종 시연 완료
- **Phase 5 W2 완료**: 빈피킹 파이프라인 L1~L4 SW 구현, Redwood RGB-D E2E 테스트 PASS
- **다음 단계**: STL 부품 모델 수거 + RealSense 카메라 연동 테스트

---

## 시스템 아키텍처

```
+----------------------------------------------------------+
|           Web Dashboard (React 18 + TypeScript)          |
| Tabs: Monitor | Print | Queue | History | Stats + Alarm  |
|       + AutomationPage (Phase 3)                         |
+----------------------------------------------------------+
                           |
               REST API + WebSocket
                           |
+----------------------------------------------------------+
|                Backend Server (FastAPI)                   |
| +-----------+ +-----------+ +---------------------------+|
| | REST API  | | WebSocket | | Background Services       ||
| |(43 routes)| | (Realtime)| | (15s Polling + Notify)    ||
| +-----------+ +-----------+ +---------------------------+|
| +--------------------------+ +--------------------------+|
| | Phase 1: Web API (11 r.)| | Phase 2: Local API (32)  ||
| +--------------------------+ +--------------------------+|
+----------------------------------------------------------+
      |                  |                    |
      v                  v                    v
+----------------+ +------------------+ +-------------------------------+
| Formlabs Cloud | | Sequence Service | | Factory PC (Windows)          |
| (Web API)      | | (Phase 3)        | | +---------------------------+ |
| - Monitoring   | | - SequenceThread | | | PreFormServer (Local API) | |
| - Print Hist.  | | - Ajin IO        | | | - Slice + Print dispatch  | |
| - Statistics   | | - MySQL Jobs     | | +---------------------------+ |
| - Alerts       | | - HCR Robot Ctrl | | | file_receiver (STL upload)| |
+----------------+ +------------------+ | +---------------------------+ |
                                        | | Form 4 x4 (WiFi)         | |
                                        +-------------------------------+
                                                    |
                                            WireGuard VPN
                                                    |
                                         +---------------------+
                                         | Server (FastAPI)    |
                                         | Dev: 6000 (:8085)   |
                                         | Prod: Kakao Cloud   |
                                         +---------------------+
```

### 빈피킹 비전 파이프라인 (Phase 5)

```
L1 Acquisition     L2 Preprocessing     L3 Segmentation    L4 Recognition     L5 Pose         L6 Robot
+--------------+   +----------------+   +---------------+  +---------------+  +------------+  +-----------+
| Blaze-112    |   | ROI Crop       |   | DBSCAN        |  | FPFH Feature  |  | 6DoF Pose  |  | HCR-10L   |
| depth map    |-->| SOR Outlier    |-->| Clustering    |->| Global RANSAC |->| Estimation |->| Pick Cmd  |
| + ace2 RGB   |   | Voxel Down     |   | Size Filter   |  | ICP Refine    |  |            |  |           |
| → PointCloud |   | RANSAC Plane   |   | BBox Extract  |  | STL Matching  |  |            |  |           |
+--------------+   +----------------+   +---------------+  +---------------+  +------------+  +-----------+
       ✅                  ✅                  ✅                  ✅              예정           예정
```

### Network

```
Office                                      Factory
+----------------------+ WireGuard VPN +--------------------------+
| Server (FastAPI)     | <============> | Factory PC              |
| Dev: 6000 (:8085)    |  10.145.113.x  | PreFormServer :44388    |
| Prod: Kakao Cloud    |                | file_receiver :8089     |
+----------------------+                | Form 4 x4 (WiFi)        |
                                        +-------------------------+
```

---

## 주요 기능

### Phase 1: 실시간 모니터링
- **OAuth2 인증**: Formlabs Cloud API 토큰 자동 갱신
- **15초 폴링**: 프린터 상태 변경 감지 + WebSocket 실시간 푸시
- **4대 동시 모니터링**: 프린터별 상태, 진행률, 레진 잔량 한눈에 확인
- **타임라인 간트 차트**: 24시간 시간축, 프린터별 작업 바, 미니 달력
- **프린터 상세 모달**: 3탭 (Details/Settings/Services) PreForm 앱 수준
- **알림 시스템**: 헤더 벨 아이콘 + 미읽음 뱃지 + 드롭다운 패널 + DB 저장
- **통계**: 재료 사용량 도넛차트, 일별 출력 바차트, 프린터별 가동률 테이블

### Phase 2: 원격 프린트 제어
- **STL 파일 업로드**: 드래그앤드롭 (100MB 제한)
- **슬라이스 미리보기**: Scene 준비 → 예상 시간/재료 사용량 + 스크린샷 이미지
- **프린트 유효성 검사**: 서포트/빌드 영역 사전 검증 (통과/경고/에러 표시)
- **모델 복제 (대량 배치)**: 빌드 플레이트에 N개 복제 + 자동 재배치
- **내부 비우기 (레진 절약)**: hollow 기능, 벽 두께 설정
- **정밀 시간 예측**: 초 단위 정밀 시간 (preprint/printing 분리)
- **프리셋 관리**: 부품별 최적 설정 저장 (레진 종류, 레이어 두께 등)
- **예약 출력**: KST 시간 피커로 예약 시간 설정
- **재출력**: 이전 작업에서 프린터 선택 + 설정 변경 후 재출력
- **대기 큐**: 드래그앤드롭 순서 변경, 프린터별 필터
- **이력 관리**: 로컬+클라우드 이력, 날짜/결과 필터, CSV 내보내기, 메모 CRUD

### Phase 3: HCR 로봇 연동 (한솔코에버)
- **시퀀스 서비스**: 독립 프로세스, SequenceThread 컨트롤러 + SequenceBase 상속
- **자동화 시퀀스**: 프린트 디스패치(print_dispatch) + 후처리(post_process: 세척/경화)
- **Ajin IO 제어**: AXL.dll ctypes 래퍼, 시뮬레이션 모드 지원
- **MySQL 기반 Job 관리**: 작업 상태 전이, step별 DB 기록
- **자동화 프론트엔드**: AutomationPage + AutomationManualPage

### Phase 5: 3D 빈피킹 비전 시스템
- **포인트 클라우드 취득**: Blaze-112 ToF depth + ace2 RGB → colored PointCloud
- **전처리**: ROI 크롭 → SOR 이상치 제거 → Voxel 다운샘플링 → RANSAC 바닥면 제거 → 법선 추정
- **분할**: DBSCAN 클러스터링, 포인트 수/크기 필터링, 바운딩 박스 추출
- **인식**: FPFH 특징 + Global RANSAC 정합 + ICP 정밀 정합, STL 모델 매칭
- **레진별 프리셋**: Grey/White/Clear/Flexible 각각 최적 파라미터

### 프린터 상태 표시
- **출력 중 (PRINTING)**: 진행률, 경과/남은/전체 시간, 레이어 정보
- **예열 중 (PREHEAT)**: 온도 표시, 주황색 애니메이션
- **일시정지 (PAUSED)**: 노란색 표시 + 터치스크린 재개 안내
- **중단 중 (ABORTING)**: 빨간색 표시
- **출력 완료 (FINISHED)**: 빌드 플레이트 회수 안내
- **미준비 (NOT READY)**: 빌드플레이트/레진탱크/카트리지 상태별 안내
- **오프라인 (OFFLINE)**: 연결 끊김 표시

---

## 프론트엔드 UI (5탭 + 자동화 + 알림벨)

| 탭 | 컴포넌트 | 기능 |
|----|----------|------|
| **모니터링** | Dashboard.tsx | 4대 프린터 그리드 카드, 상태 필터(클릭), 타임라인 간트 차트, 프린터 상세 뷰 |
| **프린트 제어** | PrintPage.tsx | 프린터별 독립 컨테이너, 슬라이스 미리보기(스크린샷), 유효성 검사, 모델 복제 |
| **대기 중인 작업** | QueuePage.tsx | 드래그앤드롭 순서 변경, 프린터 필터, 예약 시간, 30초 자동 새로고침 |
| **이전 작업 내용** | HistoryPage.tsx | 로컬+클라우드 이력, 날짜/결과 필터, CSV 내보내기(모달), 메모 CRUD, 활동 타임라인 |
| **통계** | StatisticsPage.tsx | 재료 사용량 도넛차트, 일별 출력 바차트, 프린터별 가동률 테이블, 기간 필터 |
| **자동화** | AutomationPage.tsx | 로봇 시퀀스 모니터링, 수동 제어 (Phase 3) |
| **알림벨** | App.tsx (헤더) | 알림 드롭다운, 미읽음 뱃지, 전체 읽음, 30초 폴링 |

---

## 16단계 공정 흐름

```
① STL 업로드 (웹)          → Phase 2        ✅ 구현 완료
② 슬라이스 + 프린터 전송    → Phase 2        ✅ 구현 완료
③ 3D 프린팅                → Form 4          ✅ 모니터링 완료
④ 프린팅 완료 감지          → Phase 1         ✅ 구현 완료
⑤ 빌드플레이트 픽업         → HCR-12          ✅ Phase 3 (한솔코에버 머지)
⑥ 세척기 투입              → HCR-12          ✅ Phase 3
⑦ 세척 완료 감지           → OpenMV           🔄 Phase 4 (대기)
⑧ 경화기 투입              → HCR-12          ✅ Phase 3
⑨ 경화 완료 감지           → OpenMV           🔄 Phase 4 (대기)
⑩ 경화기에서 픽업           → HCR-10L         ✅ Phase 3
⑪ 서포트 제거              → 자동/수동
⑫ 후가공 탭 작업           → HCR-10L         ✅ Phase 3
⑬ 3D 빈피킹 비전           → Basler+Open3D   🔄 Phase 5 (W2 완료)
⑭ 양품/불량 분류           → HCR-10L         ✅ Phase 3
⑮ 박스/트레이 적재          → HCR-10L         ✅ Phase 3
⑯ 완료 보고                → 서버 알림        ✅ 알림 구현 완료
```

---

## API 엔드포인트

### Phase 1: Web API 모니터링 (11 routes)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/v1/dashboard` | 4대 프린터 상태 요약 |
| `GET` | `/api/v1/printers` | 프린터 목록 |
| `GET` | `/api/v1/printers/{serial}` | 특정 프린터 상세 |
| `GET` | `/api/v1/prints` | 프린트 이력 (날짜/상태/프린터 필터) |
| `GET` | `/api/v1/statistics` | 통계 데이터 (재료/일별/프린터별 집계) |
| `WS` | `/api/v1/ws` | WebSocket 실시간 업데이트 |

### Phase 2: Local API 원격 제어 (32 routes)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/v1/local/health` | Local API 상태 확인 |
| `POST` | `/api/v1/local/printers/discover` | 네트워크 프린터 검색 |
| **프리셋** | | |
| `POST` | `/api/v1/local/presets` | 프리셋 생성 |
| `GET` | `/api/v1/local/presets` | 프리셋 목록 |
| `GET` | `/api/v1/local/presets/{id}` | 프리셋 상세 |
| `PUT` | `/api/v1/local/presets/{id}` | 프리셋 수정 |
| `DELETE` | `/api/v1/local/presets/{id}` | 프리셋 삭제 |
| `POST` | `/api/v1/local/presets/{id}/print` | 프리셋으로 바로 프린트 |
| **파일** | | |
| `POST` | `/api/v1/local/upload` | STL 파일 업로드 |
| `GET` | `/api/v1/local/files` | 업로드된 파일 목록 |
| `DELETE` | `/api/v1/local/files/{filename}` | 파일 삭제 |
| **프린트** | | |
| `POST` | `/api/v1/local/print` | 프린트 작업 시작 |
| `GET` | `/api/v1/local/print` | 프린트 작업 목록 |
| `GET` | `/api/v1/local/print/{id}` | 프린트 작업 상태 |
| **Scene** | | |
| `POST` | `/api/v1/local/scene/prepare` | Scene 준비 (슬라이스 + 예측 + 스크린샷) |
| `POST` | `/api/v1/local/scene/{id}/print` | 준비된 Scene 프린터 전송 |
| `DELETE` | `/api/v1/local/scene/{id}` | Scene 삭제 |
| `GET` | `/api/v1/local/scene/{id}/validate` | Scene 유효성 검사 (서포트/빌드 영역) |
| `GET` | `/api/v1/local/scene/{id}/models` | Scene 모델 목록 조회 |
| `POST` | `/api/v1/local/scene/{id}/models/{model_id}/duplicate` | 모델 복제 + 재배치 |
| `POST` | `/api/v1/local/scene/{id}/estimate-time` | 정밀 프린트 시간 예측 |
| `POST` | `/api/v1/local/scene/{id}/interferences` | 모델 간 간섭 검사 |
| `POST` | `/api/v1/local/scene/{id}/screenshot` | 스크린샷 저장 |
| `GET` | `/api/v1/local/scene/{id}/screenshot/{filename}` | 스크린샷 이미지 프록시 |
| `GET` | `/api/v1/local/materials` | 사용 가능 레진 목록 |
| **메모** | | |
| `GET` | `/api/v1/local/notes/{print_guid}` | 특정 프린트 메모 조회 |
| `GET` | `/api/v1/local/notes` | 메모 일괄 조회 (guids 파라미터) |
| `POST` | `/api/v1/local/notes/{print_guid}` | 메모 생성 |
| `PUT` | `/api/v1/local/notes/{note_id}` | 메모 수정 |
| `DELETE` | `/api/v1/local/notes/{note_id}` | 메모 삭제 |
| **알림** | | |
| `GET` | `/api/v1/local/notifications` | 알림 이벤트 조회 |
| `POST` | `/api/v1/local/notifications/mark-read` | 알림 읽음 처리 |

---

## Formlabs API 사용 현황

### Web API vs Local API

| 구분 | Web API | Local API |
|------|---------|-----------|
| 기반 | 클라우드 (api.formlabs.com) | 로컬 PC (PreFormServer) |
| 인증 | OAuth 2.0 | 없음 (로컬 실행) |
| Rate Limit | IP 100 req/sec | 없음 |
| **프린터 모니터링** | ✅ 가능 | ⚠️ 제한적 |
| **작업 전송** | ❌ 불가 | ✅ 가능 |
| **STL 로드/슬라이스** | ❌ 불가 | ✅ 가능 |

> **설계**: Phase 1은 Web API (모니터링), Phase 2는 Local API (원격 프린팅)

### 사용 중인 API

| 구분 | 전체 | 사용 중 | 사용률 |
|------|------|--------|--------|
| Web API | 19개 | 6개 | 32% |
| Local API | 35개 | 17개 | 49% |
| **합계** | **54개** | **23개** | **43%** |

---

## 프로젝트 구조

```
3D_printer_automation/
├── README.md
├── CLAUDE.md                    # 프로젝트 상태 문서
├── docs/                        # 문서
│
├── web-api/                     # 백엔드 (FastAPI) - Phase 1 + 2 통합
│   ├── .env.example             # 환경변수 템플릿
│   ├── data/local.db            # SQLite 데이터베이스
│   ├── app/
│   │   ├── main.py              # 앱 진입점 (lifespan, CORS, SPA)
│   │   ├── core/
│   │   │   ├── config.py        # 설정 관리 (Web + Local API)
│   │   │   └── auth.py          # OAuth2 인증
│   │   ├── services/            # Phase 1: Web API 서비스
│   │   │   ├── formlabs_client.py     # Formlabs Cloud API
│   │   │   ├── polling_service.py     # 상태 폴링 (15초)
│   │   │   └── notification_service.py # 알림 발송
│   │   ├── api/
│   │   │   └── routes.py        # Phase 1: REST API + WebSocket (11 routes)
│   │   ├── local/               # Phase 2: Local API
│   │   │   ├── routes.py        # /api/v1/local/* 라우터 (32 routes)
│   │   │   ├── schemas.py       # 프리셋/작업/Scene 스키마
│   │   │   ├── models.py        # SQLAlchemy 모델
│   │   │   ├── services.py      # 프리셋/작업 서비스
│   │   │   ├── database.py      # SQLite 설정
│   │   │   └── preform_client.py # PreFormServer 클라이언트
│   │   └── schemas/
│   │       └── printer.py       # Pydantic 모델
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
│
├── frontend/                    # 프론트엔드 (React 18 + Vite + TS + Tailwind CSS 4)
│   ├── src/
│   │   ├── App.tsx              # 메인 라우터 (5탭 + 자동화 + 알림벨)
│   │   ├── components/
│   │   │   ├── Dashboard.tsx           # 모니터링 탭
│   │   │   ├── PrintPage.tsx           # 프린트 제어 탭
│   │   │   ├── QueuePage.tsx           # 대기 큐 탭
│   │   │   ├── HistoryPage.tsx         # 이력 탭
│   │   │   ├── StatisticsPage.tsx      # 통계 탭
│   │   │   ├── AutomationPage.tsx      # 자동화 모니터링 (Phase 3)
│   │   │   ├── AutomationManualPage.tsx # 자동화 수동 제어 (Phase 3)
│   │   │   └── ...
│   │   ├── types/
│   │   ├── services/
│   │   └── hooks/
│   └── package.json
│
├── sequence_service/            # Phase 3: 시퀀스 서비스 (한솔코에버)
│   ├── README.md                # 구조/실행 가이드
│   ├── app/
│   │   ├── main.py              # 서비스 진입점
│   │   ├── cell/
│   │   │   ├── runtime.py       # SequenceThread 컨트롤러
│   │   │   ├── repository.py    # MySQL Job 관리
│   │   │   └── sequences/       # 시퀀스 정의 (print_dispatch, post_process)
│   │   ├── io/
│   │   │   ├── axl.py           # Ajin AXL.dll ctypes 바인딩
│   │   │   └── ajin_io.py       # 고수준 IO 래퍼
│   │   └── core/config.py       # 환경 설정
│   └── requirements.txt
│
├── bin_picking/                 # Phase 5: 3D 빈피킹 비전 시스템
│   ├── src/
│   │   ├── acquisition/         # L1: 카메라 취득
│   │   │   ├── depth_to_pointcloud.py  # Blaze-112 depth → PointCloud
│   │   │   └── blaze112_*.py           # pypylon 연동
│   │   ├── preprocessing/       # L2: 전처리
│   │   │   └── cloud_filter.py         # 5단계 필터 파이프라인
│   │   ├── segmentation/        # L3: 분할
│   │   │   └── dbscan_segmenter.py     # DBSCAN 클러스터링
│   │   ├── recognition/         # L4: 인식/정합
│   │   ├── pose/                # L5: 6DoF 포즈 (예정)
│   │   └── robot/               # L6: 로봇 명령 (예정)
│   ├── tests/
│   │   └── test_e2e_redwood.py  # E2E 파이프라인 검증
│   └── models/                  # STL 부품 모델 (수거 예정)
│
├── factory-pc/                  # 공장 PC 스크립트
│   └── file_receiver.py         # STL 파일 수신 + 스크린샷 서빙 (포트 8089)
│
├── OpenMV/                      # Phase 4: OpenMV 참고 자료
├── vision/                      # Phase 4: 비전 검사
├── robot-control/               # 로봇 제어 참고
└── shared/                      # 공유 유틸리티
```

---

## 기술 스택

### Backend

| 기술 | 버전 | 용도 |
|------|------|------|
| Python | 3.11+ | 메인 언어 |
| FastAPI | 0.109+ | 웹 프레임워크 (lifespan, async) |
| httpx | - | 비동기 HTTP 클라이언트 |
| pydantic-settings | - | 설정 관리 |
| SQLAlchemy | - | ORM (SQLite) |
| uvicorn | - | ASGI 서버 |

### Frontend

| 기술 | 버전 | 용도 |
|------|------|------|
| React | 18+ | UI 라이브러리 |
| TypeScript | 5+ | 타입 안전성 |
| Vite | 5+ | 빌드 도구 |
| Tailwind CSS | 4 | 스타일링 |

### 빈피킹 비전 (Phase 5)

| 기술 | 버전 | 용도 |
|------|------|------|
| Open3D | 0.19 | 포인트 클라우드 처리, 정합 |
| pypylon | 26.3 | Basler 카메라 SDK (Blaze-112, ace2) |
| NumPy | - | 수치 연산 |
| OpenCV | - | 이미지 처리 |
| trimesh | - | STL 모델 로드/처리 |
| SciPy | - | 공간 연산 |

### Infrastructure

| 기술 | 용도 |
|------|------|
| Docker | 컨테이너화 |
| Docker Compose | 멀티 컨테이너 관리 |
| WireGuard | VPN (서버 ↔ 공장 PC) |
| SQLite | 데이터베이스 (향후 PostgreSQL 전환 예정) |
| MySQL | 시퀀스 서비스 Job 관리 (Phase 3) |
| Mosquitto | MQTT 브로커 (OpenMV → 서버) |

---

## 설치 및 실행

### 사전 요구사항
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (선택)

### 환경 변수 설정

```bash
cd web-api
cp .env.example .env
```

`.env` 파일 수정:
```bash
# Formlabs Web API (필수)
FORMLABS_CLIENT_ID=your_client_id
FORMLABS_CLIENT_SECRET=your_client_secret

# PreFormServer 연결 (필수 - Local API)
PREFORM_SERVER_HOST=<FACTORY_PC_VPN_IP>
PREFORM_SERVER_PORT=44388

# 공장 PC 파일 수신 서버
FILE_RECEIVER_HOST=<FACTORY_PC_VPN_IP>
FILE_RECEIVER_PORT=8089

# 폴링 설정
POLLING_INTERVAL_SECONDS=15
```

### 방법 1: Docker로 실행 (권장)

```bash
cd web-api
docker compose up -d
```

### 방법 2: 직접 실행

**백엔드:**
```bash
cd web-api
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8085
```

**프론트엔드 (개발 모드):**
```bash
cd frontend
npm install
npm run dev
```

**시퀀스 서비스 (Phase 3):**
```bash
cd sequence_service
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app/main.py
```

### 접속
- **대시보드**: http://localhost:8085
- **API 문서**: http://localhost:8085/docs

---

## 확인된 프린터 (4대)

| 이름 | 시리얼 | 카트리지 | 상태 |
|------|--------|---------|------|
| CapableGecko | Form4-CapableGecko | Grey V5 | 운용 중 |
| HeavenlyTuna | Form4-HeavenlyTuna | Clear V5 | 운용 중 |
| CorrectPelican | Form4-CorrectPelican | Flexible 80A V1.1 | 운용 중 |
| ShrewdStork | Form4-ShrewdStork | Clear V5 | ⚠️ 헤드커버 고장 |

---

## 라이선스

이 프로젝트는 사내 전용입니다.

---

## 문의

- **개발자**: 정태민
- **회사**: 오리누 주식회사
