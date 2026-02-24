# Web API Backend (FastAPI)

> Phase 1 (Web API 모니터링) + Phase 2 (Local API 원격 제어) 통합 백엔드 서버

## 개요

Formlabs Form 4 3D프린터 4대를 실시간 모니터링하고 원격으로 프린트 작업을 전송하는 백엔드 서버입니다.

- **Phase 1**: Formlabs Cloud API 기반 실시간 모니터링 (OAuth2, 15초 폴링, WebSocket)
- **Phase 2**: PreFormServer 연동 원격 프린트 제어 (STL 업로드, 슬라이스, 프린트 전송)

## 프로젝트 구조

```
web-api/
├── app/
│   ├── main.py                 # 앱 진입점 (lifespan, CORS, SPA 서빙)
│   ├── core/
│   │   ├── config.py           # 환경변수 설정 관리 (pydantic-settings)
│   │   └── auth.py             # Formlabs OAuth2 토큰 관리 (자동 갱신)
│   ├── api/
│   │   └── routes.py           # Phase 1: REST API + WebSocket (10 routes)
│   ├── services/
│   │   ├── formlabs_client.py  # Formlabs Cloud API 클라이언트
│   │   ├── polling_service.py  # 프린터 상태 폴링 (15초 주기, 변경 감지)
│   │   └── notification_service.py  # 알림 발송 (Email, Slack)
│   ├── local/                  # Phase 2: Local API (17 routes)
│   │   ├── routes.py           # /api/v1/local/* 라우터
│   │   ├── schemas.py          # 프리셋/작업/Scene 스키마
│   │   ├── models.py           # SQLAlchemy ORM 모델
│   │   ├── services.py         # 프리셋/작업 CRUD 서비스
│   │   ├── database.py         # SQLite 연결 설정
│   │   └── preform_client.py   # PreFormServer 클라이언트 (Scene 관리, 프린트 전송)
│   └── schemas/
│       └── printer.py          # Pydantic 모델 (PrinterSummary 21필드, PrintStatus enum)
├── uploads/                    # STL 파일 업로드 저장소
├── data/                       # SQLite DB
├── tests/                      # 테스트
├── .env.example                # 환경변수 템플릿
├── requirements.txt            # Python 의존성
├── Dockerfile
└── docker-compose.yml
```

## 설치 및 실행

### 1. 환경 설정

```bash
cd web-api
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 실제 값으로 수정
```

필수 환경변수:

| 변수 | 설명 |
|------|------|
| `FORMLABS_CLIENT_ID` | Formlabs API Client ID |
| `FORMLABS_CLIENT_SECRET` | Formlabs API Client Secret |
| `PRINTER_SERIALS` | 모니터링할 프린터 시리얼 번호 (JSON 배열) |
| `PREFORM_SERVER_HOST` | PreFormServer 실행 PC IP |
| `PREFORM_SERVER_PORT` | PreFormServer 포트 (기본: 44388) |

### 3. 서버 실행

```bash
# 개발 모드
uvicorn app.main:app --reload --host 0.0.0.0 --port 8085

# 프로덕션 모드
uvicorn app.main:app --host 0.0.0.0 --port 8085
```

### 4. Docker 실행

```bash
docker compose up -d
docker compose logs -f
```

## API 엔드포인트 (총 27 routes)

### Phase 1: Web API 모니터링 (10 routes)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/v1/dashboard` | 4대 프린터 상태 요약 |
| `GET` | `/api/v1/printers` | 프린터 목록 |
| `GET` | `/api/v1/printers/{serial}` | 특정 프린터 상세 |
| `GET` | `/api/v1/printers/{serial}/refresh` | 상태 즉시 새로고침 |
| `GET` | `/api/v1/prints` | 프린트 이력 |
| `WS` | `/api/v1/ws` | WebSocket 실시간 업데이트 |

### Phase 2: Local API 원격 제어 (17 routes)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/v1/local/health` | Local API 상태 확인 |
| `POST` | `/api/v1/local/printers/discover` | 네트워크 프린터 검색 |
| `POST` | `/api/v1/local/presets` | 프리셋 생성 |
| `GET` | `/api/v1/local/presets` | 프리셋 목록 |
| `GET` | `/api/v1/local/presets/{id}` | 프리셋 상세 |
| `PUT` | `/api/v1/local/presets/{id}` | 프리셋 수정 |
| `DELETE` | `/api/v1/local/presets/{id}` | 프리셋 삭제 |
| `POST` | `/api/v1/local/presets/{id}/print` | 프리셋으로 바로 프린트 |
| `POST` | `/api/v1/local/upload` | STL 파일 업로드 (100MB 제한) |
| `GET` | `/api/v1/local/files` | 업로드된 파일 목록 |
| `DELETE` | `/api/v1/local/files/{filename}` | 파일 삭제 |
| `POST` | `/api/v1/local/print` | 프린트 작업 시작 |
| `GET` | `/api/v1/local/print` | 프린트 작업 목록 |
| `GET` | `/api/v1/local/print/{id}` | 프린트 작업 상태 |
| `POST` | `/api/v1/local/scene/prepare` | Scene 준비 (슬라이스 + 예상 시간/재료) |
| `POST` | `/api/v1/local/scene/{id}/print` | 준비된 Scene 프린터 전송 |
| `DELETE` | `/api/v1/local/scene/{id}` | Scene 삭제 |

## 기술 스택

| 기술 | 버전 | 용도 |
|------|------|------|
| Python | 3.11+ | 메인 언어 |
| FastAPI | 0.109+ | 웹 프레임워크 (lifespan, async) |
| httpx | 0.26+ | 비동기 HTTP 클라이언트 |
| pydantic-settings | 2.1+ | 환경변수 설정 관리 |
| SQLAlchemy | 2.0+ | ORM (SQLite) |
| uvicorn | 0.27+ | ASGI 서버 |
| websockets | 12.0+ | WebSocket 실시간 업데이트 |

## Formlabs API 참고

| 구분 | Web API | Local API |
|------|---------|-----------|
| 기반 | 클라우드 (api.formlabs.com) | 로컬 PC (PreFormServer) |
| 인증 | OAuth 2.0 | 없음 (로컬 실행) |
| Rate Limit | IP 100 req/sec | 없음 |
| 프린터 모니터링 | O | 제한적 |
| 작업 전송 | X | O |
| STL 로드/슬라이스 | X | O |

- [Formlabs Web API 문서](https://support.formlabs.com/s/article/Formlabs-Web-API)
- [Formlabs Local API 문서](https://formlabs-dashboard-api-resources.s3.amazonaws.com/formlabs-local-api-latest.html)
- [Formlabs Python Library](https://github.com/Formlabs/formlabs-api-python)
