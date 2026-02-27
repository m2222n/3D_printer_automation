# 3D프린터 자동화 시스템 — 소스코드 인수인계 & API 가이드라인

> **작성일**: 2026-02-27
> **작성자**: 정태민 (오리누 주식회사)
> **대상**: 한솔코에버 개발팀

Formlabs Form 4 × 4대 + HCR 협동로봇 연동

---

## 1. 프로젝트 개요

### 1.1 시스템 목표

Formlabs Form 4 3D프린터 4대와 한화 HCR 협동로봇을 연동하여, 점자프린터 부품 생산의 24/7 무인 자동화 시스템을 구축합니다.

| Phase | 내용 | 담당 | 상태 |
|-------|------|------|------|
| Phase 1 | Web API 모니터링 + 알림 | 오리누 + 한솔코에버 | 진행중 |
| Phase 2 | Local API 원격 프린팅 | 오리누 + 한솔코에버 | 진행중 |
| Phase 3 | HCR 로봇 연동 | 한솔코에버 | 진행중 |
| Phase 4 | OpenMV 비전 검사 | 오리누 | 진행 예정 |

### 1.2 기술스택

| 분류 | 기술 | 활용 |
|------|------|------|
| 백엔드 | Python 3.11, FastAPI, httpx | API 서버, Formlabs API 비동기 통신, 15초 폴링 |
| 프론트엔드 | React 18, TypeScript, Vite, Tailwind 4 | 대시보드 5탭 UI, 실시간 모니터링 |
| DB | SQLite + SQLAlchemy | 프린트 이력, 프리셋, 알림 로그 |
| 실시간 | WebSocket + 15초 폴링 폴백 | 프린터 상태 실시간 푸시 |
| 인증 | OAuth 2.0 Client Credentials | Formlabs Web API 토큰 (24시간, 자동 갱신) |
| 알림 | 이메일, Slack Webhook, FCM | 완료/에러/레진 부족 알림 |
| 인프라 | Docker, WireGuard VPN | 컨테이너 배포, 서버↔공장PC 연결 |
| 서버 | RTX 6000 (개발) | 카카오 클라우드 (운영) 이전 예정 |

### 1.3 협업 담당자

| 소속 | 이름 | 연락처 | 이메일 |
|------|------|--------|--------|
| 오리누 | 정태민 | 010-2027-9514 | jtm@orinu.ai |
| 한솔코에버 | 김기원 주임 | 010-7251-6116 | kiwon.kim@hansol.com |
| 한솔코에버 | 이나라 주임 | 010-3693-6488 | naralee@hansol.com |

---

## 2. 소스코드 인수인계

### 2.1 프로젝트 구조

```
3D_printer_automation/
├─ CLAUDE.md                # 프로젝트 상태 문서
├─ web-api/                 # 백엔드 (FastAPI) - Phase 1+2
│  ├─ .env.example          # 환경변수 템플릿
│  ├─ app/main.py           # 앱 진입점
│  ├─ app/core/             # 설정, OAuth2 인증
│  ├─ app/services/         # Phase1: Web API 클라이언트
│  ├─ app/api/routes.py     # Phase1: REST API + WebSocket
│  ├─ app/local/            # Phase2: Local API 전체
│  └─ app/schemas/          # Pydantic 모델
├─ frontend/                # 프론트엔드 (React + Vite + TS)
│  ├─ src/components/       # UI 컴포넌트 (5탭 + 모달)
│  ├─ src/services/         # API 호출
│  └─ src/hooks/            # React 훅
├─ factory-pc/              # 공장 PC 스크립트
│  └─ file_receiver.py      # STL 파일 수신 + 스크린샷
├─ robot-control/           # Phase 3: 로봇 (한솔 담당)
└─ vision/                  # Phase 4: 비전 (미구현)
```

### 2.2 환경변수 (.env)

실제 값은 별도 채널로 전달합니다.

```
FORMLABS_CLIENT_ID=<별도 전달>
FORMLABS_CLIENT_SECRET=<별도 전달>
PREFORM_SERVER_HOST=<공장 PC VPN IP>
PREFORM_SERVER_PORT=44388
FILE_RECEIVER_HOST=<공장 PC VPN IP>
FILE_RECEIVER_PORT=8089
```

### 2.3 로컬 실행 방법

**백엔드**
```bash
cd web-api
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8085
```

**프론트엔드**
```bash
cd frontend
npm install
npm run build    # dist/ → FastAPI가 서빙
npm run dev      # 개발 서버 (localhost:5173)
```

---

## 3. Formlabs API (총 23개 사용 / 54개)

### 3.1 API 이원화 구조

Web API(모니터링)와 Local API(제어)는 완전히 독립된 API입니다.

| 구분 | Web API (클라우드) | Local API (로컬) |
|------|-------------------|------------------|
| 용도 | 상태 모니터링 (읽기 전용) | 프린트 작업 전송 (제어) |
| 버전 | 0.8.1 (Beta) | 0.9.11 |
| 서버 | api.formlabs.com | PreFormServer (Windows PC) |
| 인증 | OAuth 2.0 (Client Credentials) | 없음 (로컬) / login (원격) |
| 프린트 전송 | ❌ 불가능 | ✅ 가능 |
| Rate Limit | IP 100/sec, 사용자 1500/hr | 없음 |

> **핵심**: Web API = 읽기 전용. 원격 프린팅은 반드시 Local API. 모니터링은 Web API, 제어는 Local API — 하이브리드 아키텍처.

### 3.2 Web API — 6개 (모니터링)

Base URL: `https://api.formlabs.com/developer/v1`

| API | 용도 | 코드 위치 |
|-----|------|----------|
| `POST /o/token/` | OAuth2 토큰 발급 (자동 갱신) | auth.py |
| `GET /printers/` | 프린터 4대 상태 조회 (15초 폴링) | formlabs_client.py |
| `GET /printers/{serial}/` | 특정 프린터 상세 조회 | formlabs_client.py |
| `GET /prints/` | 전체 프린트 이력 | formlabs_client.py |
| `GET /printers/{serial}/prints/` | 프린터별 이력 | formlabs_client.py |
| `GET /events/` | 프린터 이벤트 (완료/에러) | formlabs_client.py |

### 3.3 Local API — 17개 (프린트 제어)

PreFormServer 기반. 공장 PC에서 실행 (포트 44388).

| API | 용도 | 코드 위치 |
|-----|------|----------|
| `GET /` | 연결 상태 확인 | preform_client.py |
| `POST /discover-devices/` | 프린터 검색 | preform_client.py |
| `POST /scene/` | Scene 생성 (레진/두께) | preform_client.py |
| `DELETE /scene/{id}/` | Scene 삭제 | preform_client.py |
| `GET /scene/{id}/` | Scene 정보 조회 | preform_client.py |
| `POST /scene/{id}/import-model/` | STL 파일 로드 | preform_client.py |
| `POST /scene/{id}/auto-orient/` | 자동 방향 설정 | preform_client.py |
| `POST /scene/{id}/auto-support/` | 자동 서포트 생성 | preform_client.py |
| `POST /scene/{id}/auto-layout/` | 자동 배치 | preform_client.py |
| `POST /scene/{id}/print/` | 프린터로 작업 전송 | preform_client.py |
| `GET /scene/{id}/print-validation/` | 유효성 검사 (서포트/영역) | preform_client.py + routes.py |
| `POST /.../duplicate/` | 모델 N개 복제 + 재배치 | preform_client.py + routes.py |
| `GET /list-materials/` | 사용 가능 레진 목록 | preform_client.py + routes.py |
| `POST /scene/{id}/hollow-model/` | 내부 비우기 (레진 절약) | preform_client.py + routes.py |
| `POST /scene/{id}/save-screenshot/` | 미리보기 스크린샷 | preform_client.py + routes.py |
| `POST /.../estimate-print-time/` | 정밀 시간 예측 (초 단위) | preform_client.py + routes.py |
| `POST /scene/{id}/interferences/` | 모델 간 간섭 검사 | preform_client.py + routes.py |

> **신규 7개 API (2/26 이후 추가 구현)**: print-validation, duplicate, list-materials, hollow-model, save-screenshot, estimate-print-time, interferences → 기존 문서의 '미사용 API'에서 '사용 중'으로 이동

### 3.4 프린트 워크플로우 (확장 10단계)

```
① Scene 생성 → ② STL 업로드+전송 → ③ STL 임포트
④ (선택) 내부 비우기 → ⑤ 자동 방향/서포트/배치
⑥ Scene 정보 조회 → ⑦ 정밀 시간 예측
⑧ 간섭 검사 → ⑨ 스크린샷 + 유효성 검사 → ⑩ 프린터 전송

(선택) 모델 복제: ⑤ 이후 duplicate → auto-layout → ⑦~⑨ 재실행
```

### 3.5 프린터 상태값 (status)

| 상태 | 설명 | 대응 |
|------|------|------|
| IDLE | 대기 중 | 다음 작업 가능 |
| QUEUED | 작업 대기 | 대기열 표시 |
| PREHEAT | 예열 중 | 예열 표시 |
| PRINTING | 출력 중 | 진행률 모니터링 |
| FINISHED | 완료 | 완료 알림 |
| ERROR | 오류 | 에러 알림 |
| PAUSED | 일시정지됨 | 재개 대기 |
| ABORTING | 중단 중 | 상태 대기 |
| WAITING_FOR_RESOLUTION | 조치 필요 | 탱크/mixer 확인 |

> **Enum 파싱 주의**: API가 문서 외 새 상태값을 반환할 수 있음. 반드시 UNKNOWN 폴백 처리 필요. (실제 버그 경험)

### 3.6 레진 코드 매핑 (필수)

display_name이 빈 문자열을 반환하므로 (4대 모두), 아래 매핑 필수.

| 코드 | 이름 | 용도 |
|------|------|------|
| FLGPGR05 | Grey Resin V5 | 범용 |
| FLGPCL05 | Clear Resin V5 | 투명 |
| FLGPBK05 | Black Resin V5 | 범용 |
| FLGPWH05 | White Resin V5 | 범용 |
| FLRGPCL04 | Rigid 4000 V4 | 고강도 |
| FLRGPWH04 | Rigid 10K V4 | 고강도/내열 |
| FLFLPGR03 | Flexible 80A V3 | 유연 |
| FLELPBK03 | Elastic 50A V3 | 탄성 |
| FLTOPBK03 | Tough 2000 V3 | 터프 |
| FLDCBL01 | Draft V1 | 고속 |
| FLFL8011 | Flexible 80A V1.1 | 신규 |
| FLFL8001 | Flexible 80A | 신규 |

### 3.7 미사용 API (참고)

**Web API 미사용 — 13개**

| API | 기능 | 활용 가치 |
|-----|------|----------|
| `POST /o/revoke_token/` | 토큰 폐기 | 낮음 |
| `GET /tanks/` | 레진 탱크 이력 | 중 |
| `GET /cartridges/` | 카트리지 소모 이력 | 중 |
| `GET~DELETE /groups/*` | 그룹 관리 (10개) | 낮음 |

**Local API 미사용 — 주요 항목**

| API | 기능 | 활용 가치 |
|-----|------|----------|
| `GET /devices/` | 프린터 캐시 조회 | 중 |
| `POST /.../add-drain-holes/` | 드레인 홀 추가 | 중 |
| `POST /.../label-part/` | 모델 라벨 각인 | 중 |
| `POST /load-form/` | .form 파일 로드 | 중 |
| `POST /save-form/` | Scene → .form 저장 | 중 |

### 3.8 API로 불가능한 것

| 기능 | 상태 | 대안 |
|------|------|------|
| 프린트 일시정지/재개/취소 (원격) | 미지원 | 터치스크린 |
| Webhook (실시간 이벤트) | 미지원 | 15초 폴링 |
| Form Wash/Cure 제어 | API 없음 | OpenMV 카메라 감지 (Phase 4) |
| 프린터 설정 변경 | 미지원 | 터치스크린 |
| 프린트 큐 원격 관리 | 읽기만 | 자체 큐 시스템 구현 완료 |

---

## 4. 오리누 서버 API (총 38개)

한솔코에버가 소스코드를 받으면 이 API를 통해 시스템과 통신합니다.

### 4.1 Phase 1 API — 6개 (모니터링)

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/dashboard` | 4대 프린터 상태 요약 |
| GET | `/api/v1/printers` | 프린터 목록 |
| GET | `/api/v1/printers/{serial}` | 특정 프린터 상태 |
| GET | `/api/v1/prints` | 프린트 이력 (필터) |
| GET | `/api/v1/statistics` | 통계 (재료/일별/프린터별) |
| WS | `/api/v1/ws` | 실시간 WebSocket |

### 4.2 Phase 2 API — 32개 (프린트 제어)

**프린터 / 파일 관리**

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/local/health` | Local API + PreFormServer 상태 |
| POST | `/api/v1/local/printers/discover` | 프린터 검색 |
| POST | `/api/v1/local/upload` | STL 파일 업로드 |
| GET | `/api/v1/local/files` | 업로드 파일 목록 |
| DELETE | `/api/v1/local/files/{filename}` | 파일 삭제 |
| GET | `/api/v1/local/materials` | 사용 가능 레진 목록 |

**프리셋 관리**

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/v1/local/presets` | 프리셋 생성 |
| GET | `/api/v1/local/presets` | 프리셋 목록 |
| GET | `/api/v1/local/presets/{id}` | 프리셋 상세 |
| PUT | `/api/v1/local/presets/{id}` | 프리셋 수정 |
| DELETE | `/api/v1/local/presets/{id}` | 프리셋 삭제 |
| POST | `/api/v1/local/presets/{id}/print` | 프리셋으로 바로 프린트 |

**Scene / 프린트 제어**

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/v1/local/scene/prepare` | Scene 준비 (슬라이스+예측+스크린샷) |
| POST | `/api/v1/local/scene/{id}/print` | Scene 프린터 전송 |
| DELETE | `/api/v1/local/scene/{id}` | Scene 삭제 |
| GET | `/api/v1/local/scene/{id}/validate` | 유효성 검사 |
| GET | `/api/v1/local/scene/{id}/models` | 모델 목록 |
| POST | `/.../models/{id}/duplicate` | 모델 복제 + 재배치 |
| GET | `/api/v1/local/scene/{id}/screenshot/{f}` | 스크린샷 프록시 |
| POST | `/api/v1/local/scene/{id}/estimate-time` | 정밀 시간 예측 |
| POST | `/api/v1/local/scene/{id}/interferences` | 간섭 검사 |
| POST | `/api/v1/local/scene/{id}/screenshot` | 스크린샷 저장 |
| POST | `/api/v1/local/print` | 프린트 작업 시작 |
| GET | `/api/v1/local/print` | 프린트 작업 목록 |
| GET | `/api/v1/local/print/{id}` | 프린트 작업 상태 |

**메모 / 알림**

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/v1/local/notes/{guid}` | 프린트 메모 조회 |
| GET | `/api/v1/local/notes` | 메모 일괄 조회 |
| POST | `/api/v1/local/notes/{guid}` | 메모 생성 |
| PUT | `/api/v1/local/notes/{id}` | 메모 수정 |
| DELETE | `/api/v1/local/notes/{id}` | 메모 삭제 |
| GET | `/api/v1/local/notifications` | 알림 이벤트 조회 |
| POST | `/api/v1/local/notifications/mark-read` | 알림 읽음 처리 |

---

## 5. 프론트엔드 UI (5탭)

| 탭 | 컴포넌트 | 기능 |
|----|----------|------|
| 모니터링 | Dashboard.tsx | 프린터 4대 그리드 카드, WebSocket 실시간, 타임라인 간트 |
| 프린트 제어 | PrintPage.tsx | 프린터별 독립 컨테이너 (STL→슬라이스→전송) |
| 대기 중인 작업 | QueuePage.tsx | 드래그앤드롭 순서 변경, 프린터 필터 |
| 이전 작업 | HistoryPage.tsx | 로컬+클라우드 이력, CSV 내보내기, 메모 |
| 통계 | StatisticsPage.tsx | 재료 도넛차트, 일별 바차트, 가동률 테이블 |

\+ 알림벨 (헤더): 미읽음 뱃지, 30초 폴링, 드롭다운

### 5.1 프린터 상세 모달 (3탭)

| 탭 | 내용 |
|----|------|
| Details | 최근 작업 카드, 기기 정보, 카트리지 잔량 바 |
| Settings | Firmware, Remote Print, Printer Group, 온도 |
| Services | Warranty, Service Plans |

### 5.2 프린트 제어 워크플로우 (웹 UI)

1. STL 파일 드래그앤드롭 업로드
2. 레진 종류 / 레이어 두께 선택 (프리셋 저장 가능)
3. "슬라이스 미리보기" → Scene 생성 → 자동 방향/서포트/배치
4. 미리보기 카드: 스크린샷, 예상 시간, 재료량, 유효성 검사 결과
5. (선택) 내부 비우기, 모델 복제, 간섭 검사
6. "프린터로 전송" → 출력 시작

---

## 6. 프린터 & 인프라

### 6.1 보유 프린터 (4대, 현재 3대 운용)

| 이름 | 시리얼 | IP | 연결 | 상태 |
|------|--------|-----|------|------|
| CapableGecko | Form4-CapableGecko | 192.168.219.46 | WiFi | ✅ 운용 |
| HeavenlyTuna | Form4-HeavenlyTuna | 192.168.219.48 | WiFi | ✅ 운용 |
| CorrectPelican | Form4-CorrectPelican | 192.168.219.43 | WiFi | ✅ 운용 |
| ShrewdStork | Form4-ShrewdStork | 192.168.219.45 | WiFi | ❌ 고장 |

> **ShrewdStork 사용 중단**: 헤드커버 고장으로 잠정 중단. 현재 3대 운용.

### 6.2 후처리 장비

| 장비 | 수량 | API | 대안 |
|------|------|-----|------|
| Form Wash | 2대 | ❌ | 카메라/타이머 (Phase 4) |
| Form Cure | 2대 | ❌ | 카메라/타이머 (Phase 4) |

### 6.3 인프라 구조

| 구분 | 서버 | 포트 | 용도 | 상태 |
|------|------|------|------|------|
| 개발 | RTX 6000 | 8085 | 개발/테스트 | ✅ 동작 중 |
| 운영 | 카카오 클라우드 | 미정 | 운영 | 이전 예정 |

### 6.4 공장 PC

| 항목 | 값 |
|------|-----|
| PreFormServer | 포트 44388 (v3.55.0.606) |
| file_receiver | 포트 8089 (→ C:\STL_Files) |
| 스크린샷 저장 | C:\STL_Files\screenshots\ |
| 자동 시작 | WireGuard + PreFormServer + file_receiver + AnyDesk |
| 절전 모드 | 비활성화 (디스플레이 30분, 절전 안 함) |

> **VPN IP**: 공장 PC의 VPN IP는 .env 환경변수로 관리. PREFORM_SERVER_HOST / FILE_RECEIVER_HOST 참조.

---

## 7. 발견된 이슈

### 7.1 API 버그 (기존 5건)

| # | 버그 | 심각 | 상태 | 해결 |
|---|------|------|------|------|
| 1 | Enum 파싱 에러 | 높음 | ✅ | 전체 상태값 + UNKNOWN 폴백 |
| 2 | Timezone TypeError | 높음 | ✅ | datetime.now(timezone.utc) 통일 |
| 3 | 필터링 0대 | 중 | ✅ | 전체 반환 폴백 |
| 4 | display_name 빈값 | 중 | ✅ | 레진 코드 매핑 테이블 |
| 5 | mixer not detected | 중 | ⚠️ | 탱크 재장착 + 알림 |

### 7.2 공장 현장 이슈 (신규 3건)

**이슈 #6: 예열 상태 미감지**
> Web API가 예열(preheat/dispensing) 중에도 IDLE 반환. progress_percent가 -1.7% 등 음수 반환 가능. → 대시보드에서 예열 상태 표시 불가. 프론트엔드에서 음수 처리 필요.

**이슈 #7: VPN 라우팅 충돌**
> 공장 WiFi 연결 시 VPN 라우팅이 깨져서 PreFormServer 접근 불가. → 공장 현장에서는 PreForm 앱 직접 출력, 웹은 모니터링 전용. (Web API는 Formlabs Cloud 경유라 VPN 무관)

**이슈 #8: ShrewdStork 하드웨어 고장**
> 헤드커버 고장으로 잠정 중단. 현재 3대 운용. 수리 시까지 해당 프린터 작업 전송 금지.

### 7.3 에러 핸들링 가이드

| # | 상황 | 코드 | 처리 |
|---|------|------|------|
| 1 | 토큰 만료 | 401 | 자동 재발급 |
| 2 | Rate Limit | 429 | Retry-After 대기 |
| 3 | 서버 에러 | 500 | 30초 후 재시도 |
| 4 | PreFormServer 미응답 | timeout | VPN 확인 |
| 5 | 프린터 오프라인 | - | discover 재확인 |
| 6 | enum 파싱 | - | 로깅 + UNKNOWN |
| 7 | 탱크 미장착 | - | 알림 발송 |

---

## 8. 역할 분담 & 작업 규칙

### 8.1 Phase별 담당

| 구분 | 오리누 | 한솔코에버 | 상태 |
|------|--------|----------|------|
| Phase 1 (Web API) | 구현 완료 | 소스코드 인수 + 공동 개발 | 진행중 |
| Phase 2 (Local API) | 구현 완료 | 소스코드 인수 + 공동 개발 | 진행중 |
| Phase 3 (로봇 연동) | - | 한솔 담당 | 진행중 |
| Phase 4 (비전 검사) | 오리누 담당 | - | 진행 예정 |
| 공장 PC | 초기 세팅 완료 | 현장 운용 | ✅ |

### 8.2 참고 링크

| 자료 | URL |
|------|-----|
| Web API 문서 | https://support.formlabs.com/s/article/Formlabs-Web-API |
| Local API 문서 | https://formlabs-dashboard-api-resources.s3.amazonaws.com/formlabs-local-api-latest.html |
| Python 라이브러리 | https://github.com/Formlabs/formlabs-api-python |
| PreForm 다운로드 | https://formlabs.com/software/ |
| Dashboard | https://dashboard.formlabs.com |

---

*— 문서 끝 —*
