# 3D Printer Automation System

> 3D프린터-로봇 연동 자동화 시스템 | Formlabs Form 4 + HCR 협동로봇

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5+-3178C6?logo=typescript&logoColor=white)](https://typescriptlang.org)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://docker.com)

---

## 프로젝트 개요

점자프린터 플라스틱 부품(약 20종) 생산 공정을 자동화하는 시스템입니다.

### 목표
- **1차 목표**: 웹/앱에서 프린터 완료 신호 수신 및 새로운 프린팅 요청 전송
- **궁극적 목표**: 서버가 3D프린터 현황 모니터링 + 로봇 작업 지시 + 전체 공정 자동화 제어

### 하드웨어 구성

| 장비 | 모델 | 수량 | 용도 |
|------|------|------|------|
| 3D 프린터 | Formlabs Form 4 | 4대 | SLA 레진 프린팅 |
| 협동로봇 | HCR-12 | 1대 | 빌드플레이트 교체, 세척기 투입 |
| 협동로봇 | HCR-10L | 1대 | 후가공 탭, 제품 이송 |
| 세척기 | Form Wash | 2대 | 레진 세척 |
| 경화기 | Form Cure | 2대 | UV 경화 |

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web Dashboard                             │
│                   (React + TypeScript + Vite)                    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Backend Server (FastAPI)                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   REST API  │  │  WebSocket  │  │   Background Services   │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
          │                                        │
          ▼                                        ▼
┌──────────────────┐                    ┌──────────────────┐
│  Formlabs Cloud  │                    │   HCR Robots     │
│   (Web API)      │                    │  (Modbus TCP)    │
└──────────────────┘                    └──────────────────┘
          │                                        │
          ▼                                        ▼
┌──────────────────┐                    ┌──────────────────┐
│   Form 4 x 4     │                    │  HCR-12, HCR-10L │
└──────────────────┘                    └──────────────────┘
```

---

## 개발 단계 (Phase)

| Phase | 항목 | 상태 | 설명 |
|-------|------|------|------|
| **Phase 1** | Web API 모니터링 | ✅ 완료 | Formlabs Cloud API 연동, 실시간 대시보드 |
| **Phase 2** | Local API 원격 제어 | 🔜 예정 | PreFormServer 연동, STL 업로드, 원격 프린팅 |
| **Phase 3** | HCR 로봇 연동 | 📋 계획 | Modbus TCP 통신, 로봇 작업 지시 |
| **Phase 4** | YOLO 비전 검사 | 📋 계획 | 부품 식별, 불량 검출, 완료 감지 |

---

## Phase 1: Web API 모니터링

### 주요 기능
- **OAuth2 인증**: Formlabs API 토큰 자동 발급 및 갱신
- **실시간 모니터링**: 15초 주기 폴링, 상태 변경 감지
- **WebSocket**: 프론트엔드 실시간 업데이트
- **알림 서비스**: Slack, Email 알림 (프린트 완료, 에러 등)
- **대시보드**: 4대 프린터 상태 한눈에 확인

### 스크린샷

```
┌────────────────────────────────────────────────────────────┐
│  🖨️ 3D Printer Dashboard                                   │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ CapableGecko │  │ HeavenlyTuna │  │CorrectPelican│     │
│  │    🟢 IDLE   │  │   🟢 IDLE    │  │   🟢 IDLE    │     │
│  │              │  │              │  │              │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                            │
│  ┌──────────────┐                                         │
│  │ ShrewdStork  │                                         │
│  │   🟢 IDLE    │                                         │
│  │              │                                         │
│  └──────────────┘                                         │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

### API 엔드포인트

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/v1/dashboard` | 4대 프린터 상태 요약 |
| `GET` | `/api/v1/printers` | 프린터 목록 |
| `GET` | `/api/v1/printers/{serial}` | 특정 프린터 상세 상태 |
| `GET` | `/api/v1/prints` | 프린트 이력 조회 |
| `WS` | `/api/v1/ws` | WebSocket 실시간 업데이트 |

---

## 프로젝트 구조

```
3D_printer_automation/
├── README.md
├── CLAUDE.md                    # 프로젝트 상태 문서
├── docs/                        # 문서
│   └── Phase1_WebAPI_개발설계서.docx
│
├── web-api/                     # Phase 1: 백엔드 (FastAPI)
│   ├── app/
│   │   ├── main.py              # 앱 진입점
│   │   ├── core/
│   │   │   ├── config.py        # 설정 관리
│   │   │   └── auth.py          # OAuth2 인증
│   │   ├── services/
│   │   │   ├── formlabs_client.py     # Formlabs API 클라이언트
│   │   │   ├── polling_service.py     # 상태 폴링 서비스
│   │   │   └── notification_service.py # 알림 서비스
│   │   ├── api/
│   │   │   └── routes.py        # REST API + WebSocket
│   │   └── schemas/
│   │       └── printer.py       # Pydantic 모델
│   ├── tests/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── requirements.txt
│
├── frontend/                    # Phase 1: 프론트엔드 (React)
│   ├── src/
│   │   ├── components/          # UI 컴포넌트
│   │   ├── types/               # TypeScript 타입
│   │   ├── hooks/               # 커스텀 훅
│   │   └── services/            # API 서비스
│   ├── vite.config.ts
│   └── package.json
│
├── local-api/                   # Phase 2: Local API (예정)
├── robot-control/               # Phase 3: 로봇 제어 (예정)
├── vision/                      # Phase 4: 비전 검사 (예정)
└── shared/                      # 공유 유틸리티 (예정)
```

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

# 폴링 설정
POLLING_INTERVAL_SECONDS=15

# 알림 설정 (선택)
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
SMTP_HOST=smtp.gmail.com
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
```

### 방법 1: Docker로 실행 (권장)

```bash
cd web-api
docker compose up -d

# 로그 확인
docker compose logs -f
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

### 접속
- **대시보드**: http://localhost:8085
- **API 문서**: http://localhost:8085/docs

---

## 기술 스택

### Backend
| 기술 | 버전 | 용도 |
|------|------|------|
| Python | 3.11+ | 메인 언어 |
| FastAPI | 0.109+ | 웹 프레임워크 |
| httpx | - | 비동기 HTTP 클라이언트 |
| pydantic-settings | - | 설정 관리 |
| uvicorn | - | ASGI 서버 |

### Frontend
| 기술 | 버전 | 용도 |
|------|------|------|
| React | 18+ | UI 라이브러리 |
| TypeScript | 5+ | 타입 안전성 |
| Vite | 5+ | 빌드 도구 |
| Tailwind CSS | 3+ | 스타일링 |

### Infrastructure
| 기술 | 용도 |
|------|------|
| Docker | 컨테이너화 |
| Docker Compose | 멀티 컨테이너 관리 |

---

## Formlabs API 참고

### Web API vs Local API

| 구분 | Web API | Local API |
|------|---------|-----------|
| 기반 | 클라우드 (api.formlabs.com) | 로컬 PC (PreFormServer) |
| 인증 | OAuth 2.0 | 없음 |
| **프린터 모니터링** | ✅ 가능 | ⚠️ 제한적 |
| **작업 전송** | ❌ 불가 | ✅ 가능 |
| **STL 로드** | ❌ 불가 | ✅ 가능 |

> **참고**: Phase 1은 Web API (모니터링), Phase 2는 Local API (원격 프린팅) 사용

### 공식 문서
- [Formlabs Web API](https://support.formlabs.com/s/article/Formlabs-Web-API)
- [Formlabs Local API](https://formlabs-dashboard-api-resources.s3.amazonaws.com/formlabs-local-api-latest.html)
- [Formlabs Python Library](https://github.com/Formlabs/formlabs-api-python)

---

## 공정 흐름 (16단계)

```
① 3D프린팅        → Web API 모니터링
        ↓
② 플레이트 분리    → 로봇1 (HCR-12)
        ↓
③ 레진 제거       → 로봇1
        ↓
④ 새 플레이트 장착 → 로봇1
        ↓
⑤ 출력물 분리
        ↓
⑥ 세척기 투입     → 로봇1
        ↓
⑦ 경화기 투입     → 로봇1
        ↓
⑧ 서포트 제거     → 자동 (BARREL)
        ↓
⑨ 후가공 지그 장착
        ↓
⑩ 탭핑 작업      → 로봇2 (HCR-10L)
        ↓
⑪ 버제거/샌딩     → 로봇2
        ↓
⑫ 비전 검사      → YOLO
        ↓
⑬ 박스/트레이 적재 → 로봇2
```

---

## 라이선스

이 프로젝트는 사내 전용입니다.

---

## 문의

- **개발자**: 정태민
- **회사**: 오리누 주식회사

