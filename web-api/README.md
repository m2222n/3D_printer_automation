# Web API Backend (FastAPI)

> Phase 1 (Web API 모니터링) + Phase 2 (Local API 원격 제어) 통합 백엔드 서버

## 개요

Formlabs Form 4 3D프린터 4대를 실시간 모니터링하고 원격으로 프린트 작업을 전송하는 백엔드 서버입니다.

- **Phase 1**: Formlabs Cloud API 기반 실시간 모니터링 (OAuth2, 15초 폴링, WebSocket)
- **Phase 2**: PreFormServer 연동 원격 프린트 제어 (STL 업로드, 슬라이스, 프린트 전송)
- **Phase 3**: 자동화 셀 제어 UI 백엔드 — sequence_service 제어 DB(MariaDB)에 CMD 생성·셀 START/STOP·수동 I/O·Modbus
- **Phase 4**: 세척기/경화기 비전 상태 감시 — 카메라 MQTT 수신, 상태 전이 저장, WebSocket 푸시
- **Phase 5**: 빈피킹 인식 결과 수신 — 인식 모듈이 HTTP POST 한 장면/검출을 저장·조회
- **공통**: JWT 로그인(loopback 호출은 면제), 프린터 벤더 어댑터(`PRINTER_VENDOR`), 라인 MES(PostgreSQL) 배치 발행 — `POST /api/v1/local/print` 전송 성공 시 1건(`LINE_DSN` 설정 시) · 배치 내용물 = 프리셋 `part_type`
- **라인 MES v2 API** (`new`, 예정): 라인 모니터링·공정 제어 탭이 쓰는 `/api/v2/*` 18개 — 아직 미구현, 프런트는 목업으로 동작 (`frontend/src/services/lineApi.ts`)

## 프로젝트 구조

```
web-api/
├── app/
│   ├── main.py                 # 앱 진입점 (lifespan, CORS, SPA 서빙)
│   ├── core/
│   │   ├── config.py           # 환경변수 설정 관리 (pydantic-settings)
│   │   ├── user_auth.py        # 사용자 로그인 (bcrypt + JWT)
│   │   ├── jwt_middleware.py   # JWT 인증 미들웨어 (loopback 호출은 면제)
│   │   └── auth.py             # Formlabs OAuth2 토큰 관리 (자동 갱신)
│   ├── api/
│   │   ├── auth_routes.py      # 로그인 / 세션 (3 routes)
│   │   └── routes.py           # Phase 1: REST API + WebSocket (10 routes)
│   ├── services/
│   │   ├── formlabs_client.py  # Formlabs Cloud API 클라이언트
│   │   ├── polling_service.py  # 프린터 상태 폴링 (15초 주기, 변경 감지)
│   │   └── notification_service.py  # 알림 발송 (Email, Slack)
│   ├── local/                  # Phase 2: Local API (50 routes)
│   │   ├── routes.py           # /api/v1/local/* 라우터
│   │   ├── schemas.py          # 프리셋/작업/Scene 스키마
│   │   ├── models.py           # SQLAlchemy ORM 모델
│   │   ├── services.py         # 프리셋/작업 CRUD 서비스
│   │   ├── database.py         # SQLite 연결 설정
│   │   ├── automation_db.py    # 자동화 제어 DB(MariaDB) 접근 — CMD 생성/셀 상태/로그
│   │   ├── ajin_io.py          # 수동 제어 화면용 DIO (Windows)
│   │   ├── line_publish.py     # 라인 MES(PostgreSQL)에 배치 발행 (LINE_DSN 비면 no-op)
│   │   └── preform_client.py   # PreFormServer 클라이언트 (Scene 관리, 프린트 전송)
│   ├── adapters/               # 프린터 벤더 추상화 (PrinterAdapter Protocol)
│   │   ├── base.py             # 계약 — PrinterSummary 5필드는 로봇 핸드셰이크 계약(동결)
│   │   ├── factory.py          # PRINTER_VENDOR 로 구현 선택 (formlabs | demo)
│   │   └── demo.py             # 자격증명·실물 없이 UI 확인용 (지어낸 값)
│   ├── vision/                 # 세척기/경화기 상태 감시 (10 routes)
│   │   ├── routes.py           # /api/v1/vision/* 라우터
│   │   ├── mqtt_client.py      # 카메라 MQTT 수신
│   │   ├── camera_manager.py   # 카메라 상태/하트비트 관리
│   │   ├── simulator.py        # 상태 시뮬 발행 (개발용)
│   │   └── models.py, schemas.py
│   ├── binpick/                # 빈피킹 인식 결과 수신 (6 routes)
│   │   ├── routes.py           # /api/v1/binpick/* 라우터
│   │   └── models.py, schemas.py
│   └── schemas/
│       └── printer.py          # Pydantic 모델 (PrinterSummary 21필드, PrintStatus enum)
├── uploads/                    # STL 파일 업로드 저장소
├── data/                       # SQLite DB
├── scripts/                    # 개발용 시드 스크립트
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
| `LINE_DSN` | 라인 MES(PostgreSQL) DSN. 비어 있으면 배치 발행을 하지 않음 |
| `LINE_ID` | 라인 MES 가 보는 라인 = 지금 물리적으로 물건이 밟는 경로 (기본: RESIN-1-ASIS). FE 는 `/system/config` 의 `line_id` 로 받는다 — 하드코딩 금지. 재배치 날 `topology.yaml` 의 `active` 와 함께 바꾼다 |
| `PRINTER_VENDOR` | 프린터 어댑터 (기본: formlabs, UI 확인용: demo) |

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

## API 엔드포인트 (총 79 routes)

### Phase 1: Web API 모니터링 (10 routes)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/v1/dashboard` | 4대 프린터 상태 요약 |
| `GET` | `/api/v1/printers` | 프린터 목록 |
| `GET` | `/api/v1/printers/{serial}` | 특정 프린터 상세 `TODO` M2c — 폴링이 잡은 PRINTING/ERROR/PAUSED 를 라인 MES `State(RUN/ERROR/HOLD)` 로 발행. `DONE` 은 여기서 내지 않는다(FINISHED 는 15초 폴링이 놓치는 전이 상태 → 제어 `cmd_status=40` 이 1차 정보원, 병존 ④-4) |
| `GET` | `/api/v1/printers/{serial}/refresh` | 상태 즉시 새로고침 |
| `GET` | `/api/v1/prints` | 프린트 이력 |
| `GET` | `/api/v1/printers/{serial}/prints` | 특정 프린터 이력 |
| `GET` | `/api/v1/statistics` | 프린트 통계 |
| `GET` | `/api/v1/system/token-status` | Formlabs API 토큰 상태 |
| `GET` | `/api/v1/system/config` | 시스템 설정 조회. 9/23 `printer_serial_map`·`line_id`·`line_mes`(LINE_DSN 유무 — FE 라인 화면이 실 API/목업을 이걸로 가른다) 추가 |
| `WS` | `/api/v1/ws` | WebSocket 실시간 업데이트 `TODO` 라인 모니터링 탭은 이 WS 를 쓰지 않는다(v2 는 폴링). 같은 프린터가 두 화면에서 다른 주기로 갱신됨 — 값이 엇갈려 보이면 여기가 원인 |

### Phase 2: Local API 원격 제어 (32 routes)

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
| `POST` | `/api/v1/local/print` | 프린트 작업 시작 `TODO` 라인 MES 배치 발행은 코드에 들어갔으나 `LINE_DSN` 미설정이면 no-op — 운영 PC 에 PostgreSQL + `schema.sql` + `topo_sync` 적용 후 DSN 을 채워야 실제로 발행된다. `simul_mode` 는 발행하지 않기로 함(장비 없음 = 배치 없음, 배포 검증 경로 오염 방지) — 확정 필요. 주문(`order_id`)은 추후 연결 |
| `GET` | `/api/v1/local/print` | 프린트 작업 목록 |
| `GET` | `/api/v1/local/print/{id}` | 프린트 작업 상태 |
| `POST` | `/api/v1/local/scene/prepare` | Scene 준비 (슬라이스 + 예상 시간/재료) |
| `POST` | `/api/v1/local/scene/{id}/print` | 준비된 Scene 프린터 전송 |
| `DELETE` | `/api/v1/local/scene/{id}` | Scene 삭제 |
| `GET` | `/api/v1/local/scene/{id}/validate` | 프린트 전 유효성 검사 |
| `GET` | `/api/v1/local/scene/{id}/models` | Scene 모델 목록 |
| `POST` | `/api/v1/local/scene/{id}/models/{model_id}/duplicate` | 모델 복제 (대량 배치) |
| `POST` | `/api/v1/local/scene/{id}/estimate-time` | 정밀 프린트 시간 예측 |
| `POST` | `/api/v1/local/scene/{id}/interferences` | 모델 간 간섭 검사 |
| `POST` | `/api/v1/local/scene/{id}/screenshot` | 스크린샷 저장 |
| `GET` | `/api/v1/local/scene/{id}/screenshot/{filename}` | 스크린샷 이미지 프록시 |
| `GET` | `/api/v1/local/materials` | 사용 가능한 재료(레진) 목록 |
| `GET` | `/api/v1/local/notes` | 여러 프린트 작업의 메모 일괄 조회 |
| `GET` | `/api/v1/local/notes/{print_guid}` | 프린트 작업 메모 조회 |
| `POST` | `/api/v1/local/notes/{print_guid}` | 프린트 작업에 메모 추가 |
| `PUT` | `/api/v1/local/notes/{note_id}` | 메모 수정 |
| `DELETE` | `/api/v1/local/notes/{note_id}` | 메모 삭제 |
| `GET` | `/api/v1/local/notifications` | 알림 이벤트 목록 |
| `POST` | `/api/v1/local/notifications/mark-read` | 알림 읽음 처리 |

> `POST /api/v1/local/print` 는 응답을 즉시 돌려주고 실제 전송은 백그라운드에서 한다. 전송 성공 시 라인 MES에 배치 1건을 발행한다(`LINE_DSN` 설정 시). 발행이 실패해도 출력은 이미 시작됐으므로 작업의 `error_message` 에 `LINE_UNTRACKED:` 로만 남긴다.
> 배치 내용물은 **프리셋의 `part_type`** 에서 온다 — 프리셋으로 건 출력이면 `unit_content` 에 그 부품 1개(플레이트 한 장 = STL 1회 import)가 실리고, 프리셋 없이 직접 설정으로 걸면 내용 미상(0행)이다. `part_type` 이 부품 마스터에 없으면 그 이름으로 생성한다.

### 인증 (3 routes)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/api/v1/auth/login` | 로그인 → JWT (7일 sliding, 30일 절대 최대) |
| `GET` | `/api/v1/auth/me` | 현재 세션 |
| `POST` | `/api/v1/auth/logout` | 로그아웃 |

### Phase 3: 자동화 셀 제어 (18 routes) — sequence_service 연동

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/api/v1/local/automation/commands` | Sequence CMD 생성 (제어 DB `print_command` 에 QUEUED 1행) |
| `GET` | `/api/v1/local/automation/commands` | Sequence CMD 목록 ✅ 9/23 각 항목에 `line_tracked`(라인 MES `unit.cmd_id` 대조 · `LINE_DSN` 없으면 null) — false = Spawn 누락 CMD |
| `POST` | `/api/v1/local/automation/commands/use` | CMD use_yn 일괄 변경 |
| `POST` | `/api/v1/local/automation/control/{action}` | START / STOP / PAUSE / RESUME ✅ 정정 — `set_cell_state` 가 `automation_log` 에 `Control action: START` 로 이미 기록한다(9/22 "미기록" 은 오독). v2 `command_log` 에는 넣지 않는다(`cell_state` 는 기존 DB 개념) |
| `POST` | `/api/v1/local/automation/simul` | 시뮬 모드 토글 |
| `GET` | `/api/v1/local/automation/state` | Sequence 동작 상태 |
| `GET` | `/api/v1/local/automation/queues` | 런타임 큐 스냅샷 |
| `GET` | `/api/v1/local/automation/logs` | Sequence/Program 로그 |
| `GET` | `/api/v1/local/automation/manual/io/state` | DIO 입출력 비트 읽기 |
| `POST` | `/api/v1/local/automation/manual/io/output` | DIO 출력 비트 쓰기 **유지**(관리자용). ✅ 9/23 `automation_log(source=manual)` 기록 추가 |
| `POST` | `/api/v1/local/automation/manual/robot-send` | 로봇 TCP 수동 송신 **유지**(관리자용 · W6 는 카탈로그의 검증된 명령만 보내는 작업자용 문). ✅ 9/23 `automation_log(source=manual)` 기록 추가 |
| `POST` | `/api/v1/local/automation/manual/vision-send` | 비전 TCP 수동 송신 |
| `GET` | `/api/v1/local/automation/manual/robot-status` | 로봇 TCP 연결 상태 |
| `GET` | `/api/v1/local/automation/manual/vision-status` | 비전 TCP 연결 상태 |
| `GET` | `/api/v1/local/automation/manual/comm-config` | 수동 통신 대상 설정 조회 |
| `POST` | `/api/v1/local/automation/manual/comm-config` | 수동 통신 대상 설정 변경 |
| `GET` | `/api/v1/local/automation/manual/modbus/registers` | 로봇 Modbus holding register 읽기 |
| `GET` | `/api/v1/local/automation/manual/modbus/write` | Modbus register 1개 쓰기 (query 파라미터) **유지**(관리자용). ✅ 9/23 `automation_log(source=manual)` 기록 추가. 쓰기인데 GET 인 것은 FE 호출부가 있어 그대로 |

### Phase 4: 비전 상태 감시 (10 routes)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/v1/vision/health` | MQTT 연결 · 카메라 온라인 수 |
| `GET` | `/api/v1/vision/cameras` | 카메라 목록 `TODO` M2a — `wash_1 → WSH-01` 매핑은 개명이 아니라 `node.external_ref.mqtt` 조회. 🚨 `wash_1` 문자열이 4곳에 박혀 있어(camera_manager · simulator · schemas · routes) 하나라도 개명하면 동시에 깨진다 |
| `GET` | `/api/v1/vision/cameras/{camera_id}` | 카메라 상세 |
| `GET` | `/api/v1/vision/devices` | 장비별(세척기/경화기) 상태 |
| `GET` | `/api/v1/vision/devices/{device_type}/{device_id}` | 장비 상세 |
| `GET` | `/api/v1/vision/events` | 상태 전이 이력 `TODO` M2a — 상태 전이마다 라인 MES `State` 발행. 🚨 `mqtt_client.py` 의 `except Exception` 블록 안에 넣지 않는다(지금 그 블록이 ValidationError 를 삼켜 실물 메시지를 전건 버리고 있다 → 선행 수정: `schemas.py:38 timestamp: str → float | str`) |
| `GET` | `/api/v1/vision/events/latest` | 최근 이벤트 |
| `POST` | `/api/v1/vision/simulate` | 상태 1건 시뮬 발행 (개발용) `TODO` 시뮬도 같은 어댑터 경로를 타야 한다 — 실물과 발행 경로가 갈리면 시뮬 통과가 실물 보증이 안 된다 |
| `POST` | `/api/v1/vision/simulate/scenario` | 시나리오 시뮬 (개발용) |
| `WS` | `/api/v1/vision/ws` | 실시간 상태 푸시 |

### Phase 5: 빈피킹 결과 수신 (6 routes)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/api/v1/binpick/reports` | 인식 모듈 → 서버 (검출 개수 불일치는 거부 대신 `warnings`) `TODO` (P5) 테이블은 이관하지 않는다(주제가 인식 품질). 로봇이 집으면 `Moved(source=ROBOT)` 이 따로 오고 `scene_id` 는 `product_event.msg` 참조로만 |
| `GET` | `/api/v1/binpick/health` | 상태 (신뢰되지 않은 장면 수 포함) |
| `GET` | `/api/v1/binpick/scenes` | 장면 목록 (`gate_verdict` · `trusted_only` · `label` 필터) |
| `GET` | `/api/v1/binpick/scenes/latest` | 최신 장면 |
| `GET` | `/api/v1/binpick/scenes/{scene_pk}` | 장면 상세 (검출 순서 보존) |
| `WS` | `/api/v1/binpick/ws` | 실시간 |

### 라인 MES v2 (18 routes) — `new` · 미구현 · 명세 = `docs/plan/20260921_API명세.md`

신규 스키마(`schema.sql`, PostgreSQL)와 라인 모니터링·공정 제어 탭을 위해 새로 정의된 API. 전부 `/api/v2` prefix, 전부 JWT, WebSocket 없음(폴링). 프런트(`lineApi.ts`)는 `USE_MOCK = true` 로 목업이 답하고 있으며, 백엔드가 생기면 그 파일의 함수 본문만 바뀐다.

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/v2/lines/{line_id}/nodes` | `new` R1 노드 현황 (설비·랙 점유, 진척, 담당 반송자원) |
| `GET` | `/api/v2/lines/{line_id}/transporters` | `new` R2 반송 자원 (큐·대기 시간) |
| `GET` | `/api/v2/lines/{line_id}/wip` | `new` R3 재공 파이프라인 |
| `GET` | `/api/v2/lines/{line_id}/control-menu` | `new` R4 제어 서브 메뉴 (설비 목록·화면 종류) |
| `GET` | `/api/v2/nodes/{node_id}/inbound` | `new` R5 투입 대기 큐 |
| `GET` | `/api/v2/nodes/{node_id}/source-racks` | `new` R6 직전 출처 랙 목록 |
| `GET` | `/api/v2/racks/{node_id}/slots` | `new` R7 랙 칸 목록 |
| `GET` | `/api/v2/racks/{node_id}/slots/{slot_no}/queue` | `new` R8 칸 FIFO 대기열 |
| `GET` | `/api/v2/nodes/{node_id}/groups` | `new` R9 노드의 묶음(바구니·트레이) |
| `GET` | `/api/v2/nodes/{node_id}/parts` | `new` R10 부품 판정 목록 |
| `GET` | `/api/v2/transporters/{transporter_id}/commands` | `new` R11 로봇 명령 카탈로그 (`transporter.attrs`) |
| `GET` | `/api/v2/parts` | `new` R12 부품 마스터 — 내용 미상 배치(주문·프리셋 없이 걸린 출력)의 파트별 판정에서 작업자가 부품을 고르는 목록 |
| `POST` | `/api/v2/units/{unit_id}/split` | `new` W1 배치 완료 등록 — 부품 분리 (`Split`) |
| `POST` | `/api/v2/moves` | `new` W2 이동 (`Moved`) |
| `POST` | `/api/v2/nodes/{node_id}/state` | `new` W3 설비 상태 변경 (`State`) |
| `POST` | `/api/v2/judgements` | `new` W4 부품 판정 |
| `POST` | `/api/v2/commands` | `new` W5 조작 기록 (`command_log`) |
| `POST` | `/api/v2/transporters/{transporter_id}/commands/{command_id}` | `new` W6 로봇 명령 실행 |

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
| psycopg | 3.1+ | 라인 MES(PostgreSQL) 배치 발행 |
| aiomqtt | - | 비전 카메라 MQTT 수신 |
| bcrypt, PyJWT | - | 사용자 로그인 (JWT) |

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
