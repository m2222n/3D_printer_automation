작성 2026-09-16 (화) KST · 조사 대상 = `web-api/` · `sequence_service/` · `bin_picking/`
🔒 **코드 변경 0건** — 전수 조사만.

# 0. 한 줄 결론

> **HTTP 서버는 `web-api` 하나뿐이다.** `sequence_service` 와 `bin_picking` 은 **엔드포인트를 0개 정의**하고
> **호출하는 쪽**이다. 등록 엔드포인트 **80개**(+ 앱 레벨 4 + docs 4 + 정적 mount 1) 중
> **프론트가 부르는 것은 38종**이고 **아무도 안 부르는 것이 27개**다.

| 저장소 | HTTP 서버 | 근거 |
| --- | --- | --- |
| **web-api** | ✅ FastAPI 1개 | `app/main.py:192-196` 라우터 5개 include |
| **sequence_service** | 🔴 **없음** | `FastAPI`·`Flask`·`http.server` grep **0건**. `app/main.py:58` 은 **web-api 를 uvicorn 자식 프로세스로 띄우는 것**뿐 |
| **bin_picking** | 🔴 **없음** | 같은 grep 0건. `pick_socket_server.py` 는 **raw TCP 소켓**(HTTP 아님) |

---

# 1. 조사 방법 — 라우터 파일이 아니라 런타임 등록표를 봤다

🚨 **데코레이터만 세면 틀린다** — `@router.api_route(methods=[...])` 가 있고,
`create_app()` 안에서 **런타임에 등록되는 SPA 폴백**이 있으며, **등록 순서가 동작을 바꾼다**.
그래서 **앱을 실제로 import 해 `app.routes` 를 덤프**했다.

```bash
cd web-api && venv/bin/python - <<'PY'
import os; os.environ.setdefault("DEBUG","true")
from app.main import app
from fastapi.routing import _IncludedRouter
for r in app.routes:
    if isinstance(r, _IncludedRouter):
        for sr in r.original_router.routes:
            print(",".join(sorted(getattr(sr,"methods",[]) or [])) or "WS", r.include_context.prefix + sr.path)
    else:
        print(",".join(sorted(getattr(r,"methods",[]) or [])) or type(r).__name__, getattr(r,"path","?"))
PY
```

⭐ **이 방법이 잡아준 것** = 아래 §2 순서 함정 · `PATCH,POST,PUT` 다중 메서드 1건 ·
FastAPI 가 스스로 뱉는 **Duplicate Operation ID 경고** 1건.

---

# 2. 등록 구조와 🚨 순서 함정

## 2-1. 등록 순서 (실측)

| # | 경로 | 정의 위치 |
| --- | --- | --- |
| 0~3 | `/openapi.json` `/docs` `/docs/oauth2-redirect` `/redoc` | FastAPI 기본 |
| 4~8 | **라우터 5개**(auth · api · local · vision · binpick) | `main.py:192-196` |
| 9 | `/assets` (StaticFiles mount) | `main.py:202` |
| **10** | 🚨 **`GET /{full_path:path}`** (SPA 폴백) | **`main.py:205`** — `create_app()` **안** |
| 11 | `GET /` | `main.py:229` — 모듈 레벨, `app = create_app()` **뒤** |
| 12 | `GET /health` | `main.py:245` — 같음 |

## 2-2. 🔴 `GET /health` 와 `GET /` 는 도달하지 않는다 [확인]

`/{full_path:path}` 가 **먼저 등록**되고 Starlette 는 **선착순 매칭**이라 뒤의 둘을 가린다.
TestClient 실측:

```
/health         200  text/html   <!doctype html> <html lang="ko"> …   ← JSON 이 아니라 index.html
/               200  text/html   <!doctype html> …
```

⇒ **`main.py:245` 의 헬스체크 핸들러(폴링 상태·모니터링 대수 반환)는 죽은 코드다.**
🚨 **조건** = `frontend/dist` 가 존재할 때만(폴백이 그 `if` 안에 있다). **3개 운영 서버 전부 dist 가 있다.**
⭐ 운영 헬스체크가 `deploy.bat:24` 의 **`/api/v1/local/health`** 인 것은 결과적으로 옳았다 — 그쪽은 라우터라 안 가려진다.

## 2-3. 🟡 Duplicate Operation ID 1건 [확인]

`/api/v1/local/automation/manual/modbus/write` 가 **두 번 정의**된다 —
`@router.api_route(methods=["POST","PUT","PATCH"])`(`local/routes.py:1602`) + `@router.get`(`:1643`).
FastAPI 가 import 시 경고를 낸다:

```
UserWarning: Duplicate Operation ID automation_manual_modbus_write_api_v1_local_… for function automation_manual_modbus_write
```

🟢 **라우팅은 정상**(메서드가 안 겹친다). 🔴 **OpenAPI 스키마·클라이언트 생성기에서만 충돌**한다.

---

# 3. 미들웨어 — 어디서 가로채나

`main.py` 등록 순서 = **JWTAuthMiddleware → CORSMiddleware**.

## 3-1. JWT (`app/core/jwt_middleware.py`)

| 규칙 | 근거 |
| --- | --- |
| **활성 조건** | `AUTH_USERNAME` · `AUTH_PASSWORD_HASH` · `JWT_SECRET` **셋 다** 있을 때만 (`:84`) |
| **보호 대상** | **`/api/` 로 시작하는 경로 전부** (`_is_protected_path` `:37-43`) |
| **공개 예외** | 🥇 **`/api/v1/auth/login` 하나뿐** (`PUBLIC_API_PATHS` `:31-33`) |
| OPTIONS | 전부 통과 (CORS preflight `:96`) |
| 🚨 **loopback 면제** | `client host ∈ {127.0.0.1, ::1, localhost}` 이면 **토큰 없이 통과** (`:105-110`) |
| WebSocket | 같은 규칙. 토큰은 **`?token=`** 쿼리 또는 Authorization 헤더 (`:53-64`). 실패 시 **close 4401** |
| 응답 헤더 | sliding refresh 시 `X-New-Token` + `Access-Control-Expose-Headers` |

**🔓 보호되지 않는 것** = `/` · `/health` · `/assets/*` · **`/docs` · `/redoc` · `/openapi.json`**
(`/api/` 로 시작하지 않는다) ⇒ TestClient 실측 `/docs` **200 · 인증 없음**, `/openapi.json` **200**.
⇒ ⚠️ **API 스키마 전문이 인증 없이 열린다.**

**🐛 문서와 코드가 어긋난다** — 파일 상단 독스트링(`:10`)은 *"예외 경로 … `/api/v1/auth/me`"* 라 적었는데
`PUBLIC_API_PATHS` 에 **`/me` 가 없다.** ⇒ **`/me` 는 미들웨어에서 먼저 401 이 난다**(핸들러까지 안 간다).
🟢 동작상 문제는 없다(어차피 토큰이 필요한 경로). 🔴 **주석이 사실과 다르다.**

## 3-2. 🚨🚨 확인이 필요한 구조적 질문 — 터널 경유 요청이 loopback 으로 보이나 [미확인]

`main.py:build_web_api_cmd` 의 uvicorn 실행에 **`--proxy-headers` / `--forwarded-allow-ips` 가 없다.**
그러면 `scope["client"]` = **TCP 피어**다.

```
외부 사용자 → Cloudflare → cloudflared(공장 PC 안) → ???:8085 → uvicorn
```

- cloudflared ingress 가 **`http://127.0.0.1:8085`** 또는 `localhost` 면
  ⇒ uvicorn 이 보는 client host 가 **127.0.0.1** ⇒ **loopback 면제가 모든 외부 요청에 적용**된다.
- ingress 가 **LAN IP** 면 ⇒ 면제 안 걸린다(현행 주석의 전제).

🚨 `jwt_middleware.py:108` 주석은 *"외부 노출 = Cloudflare Tunnel → **항상 외부 IP라 영향 없음**"* 이라 단정하는데,
**cloudflared 설정은 이 저장소에 없다**(repo 전체 grep = 회의록 언급 3건뿐, 설정 파일 0건).

📮 **확인 방법**(공장 PC 관리자 창, 1분) — 설정의 `service:` 주소를 본다.
```
cloudflared tunnel ingress url http://127.0.0.1:8085
type C:\Users\<user>\.cloudflared\config.yml
```
그리고 **외부 망(테더링)에서 토큰 없이 `GET /api/v1/dashboard`** 를 호출해 **401 이 나오는지**가 최종 판정이다.
⇒ **401 이면 현행 주석이 맞고, 200 이면 JWT 가 외부에 대해 무력**이다.
⚠️ **지금 판정하지 않는다** — 확인 전까지 어느 쪽도 사실로 적지 않는다.

---

# 4. 엔드포인트 전수 (80개)

**인증 열 규칙** — `/api/` 전부 🔒(JWT). `🔓` 는 미들웨어 예외. **loopback 은 전 경로 면제**(§3-1).
**호출자 열** — 🔴 = 저장소 어디에서도 호출하는 코드를 못 찾음.

## 4-1. 인증 `app/api/auth_routes.py` (prefix `/api/v1/auth`)

| 메서드 | 경로 | 파일:줄 | 요청 | 응답 | 인증 | 호출자 |
| --- | --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/auth/login` | `auth_routes.py:37` | `LoginRequest` | `LoginResponse` | 🔓 **유일한 공개** | `frontend/src/services/auth.ts:48` · `tests/test_auth.py` |
| GET | `/api/v1/auth/me` | `:70` | – | `MeResponse` | 🔒 | `auth.ts:94` · `tests/test_auth.py:46` |
| POST | `/api/v1/auth/logout` | `:87` | – | dict(모델 없음) | 🔒 | `auth.ts:75` |

## 4-2. 모니터링 `app/api/routes.py` (prefix `/api/v1`)

| 메서드 | 경로 | 파일:줄 | 요청 | 응답 | 호출자 |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/dashboard` | `routes.py:31` | – | `DashboardData` | `api.ts:37 getDashboard` → `useDashboard` · `scripts/deploy_servers.sh`(4곳) · `tests` |
| GET | `/api/v1/printers` | `:67` | – | `List[PrinterSummary]` | 🔴 **없음** (`api.ts:42 getPrinters` 가 **어디서도 import 안 됨**) |
| GET | `/api/v1/printers/{serial}` | `:90` | – | `PrinterSummary` | `api.ts:52 getPrinterSummary` · 🥇 **`sequence_service/app/cell/printer_interface.py:79`** |
| GET | `/api/v1/printers/{serial}/refresh` | `:118` | – | `PrinterSummary` | 🔴 **없음** (프론트에 함수 자체가 없다) |
| GET | `/api/v1/prints` | `:150` | q: `printer_serial` `status` `date_from` `date_to` `page` `page_size` | `PrintHistoryResponse` | `api.ts:73 getPrintHistory` |
| GET | `/api/v1/printers/{serial}/prints` | `:196` | q: `limit` | `List[PrintHistoryItem]` | 🔴 **없음** |
| GET | `/api/v1/statistics` | `:225` | q: `printer_serial` `date_from` `date_to` | 🟡 **모델 없음**(dict) | `api.ts:108 getStatistics` |
| GET | `/api/v1/system/token-status` | `:346` | – | 모델 없음 | 🔴 **없음** |
| GET | `/api/v1/system/config` | `:363` | – | 모델 없음 | 🔴 **없음** |
| **WS** | `/api/v1/ws` | `:424` | – | `{type: dashboard_update\|notification}` | `frontend/src/hooks/useWebSocket.ts:58` ⚠️ §6 |

## 4-3. 제어 `app/local/routes.py` (prefix `/api/v1/local`) — 51개

**프리셋 · 파일 · 작업**

| 메서드 | 경로(`/api/v1/local` 생략) | 줄 | 요청 | 응답 | 호출자 |
| --- | --- | --- | --- | --- | --- |
| GET | `/health` | 132 | – | 모델 없음 | `localApi.ts:59` · 🥇 **`deploy.bat:24` 배포 검증** |
| POST | `/printers/discover` | 153 | q:`timeout` | `List[DiscoveredPrinter]` | 🔴 **없음**(`discoverPrinters` 미사용) |
| POST | `/presets` | 182 | `PresetCreate` | `PresetResponse` | `localApi.ts:97` |
| GET | `/presets` | 199 | q:`skip,limit,part_type,printer_serial` | `PresetListResponse` | `localApi.ts:89` |
| GET | `/presets/{preset_id}` | 218 | – | `PresetResponse` | 🔴 **없음**(`getPreset` 미사용) |
| PUT | `/presets/{preset_id}` | 233 | `PresetUpdate` | `PresetResponse` | 🔴 **없음**(`updatePreset` 미사용) |
| DELETE | `/presets/{preset_id}` | 252 | – | 모델 없음 | `localApi.ts:111` |
| POST | `/upload` | 269 | **multipart** `UploadFile` | 모델 없음 | `localApi.ts:124`(authFetch 직접) · 🥇 **`printer_interface.py:41`** |
| GET | `/files` | 318 | – | 모델 없음 | `localApi.ts:139` |
| DELETE | `/files/{filename}` | 341 | – | 모델 없음 | `localApi.ts:143` |
| POST | `/print` | 400 | `PrintJobCreate` | `PrintJobResponse` | `localApi.ts:153` · 🥇 **`printer_interface.py:70`** · `tests/test_print_job.py` |
| GET | `/print/{job_id}` | 506 | – | `PrintJobResponse` | ⭐ **프론트는 미사용이나** 🥇 **`printer_interface.py:86`** ⇒ **죽지 않았다** |
| GET | `/print` | 521 | q:`skip,limit` | `List[PrintJobResponse]` | `localApi.ts:164` |

**Scene (PreFormServer 연동)**

| 메서드 | 경로 | 줄 | 요청 | 응답 | 호출자 |
| --- | --- | --- | --- | --- | --- |
| POST | `/scene/prepare` | 541 | `ScenePrepareRequest` | `SceneEstimate` | `localApi.ts:181` |
| POST | `/scene/{scene_id}/print` | 591 | q:`printer_serial,job_name` | 모델 없음 | `localApi.ts:196` |
| DELETE | `/scene/{scene_id}` | 635 | – | 모델 없음 | `localApi.ts:202` |
| GET | `/scene/{scene_id}/validate` | 657 | – | 모델 없음 | 🔴 **없음**(`validateScene` 미사용) |
| GET | `/scene/{scene_id}/models` | 673 | – | 모델 없음 | `localApi.ts:216` |
| POST | `/scene/{scene_id}/models/{model_id}/duplicate` | 685 | `DuplicateModelRequest` | 모델 없음 | `localApi.ts:224` |
| GET | `/materials` | 753 | – | 모델 없음 | 🔴 **없음**(`listMaterials` 미사용) |
| GET | `/scene/{scene_id}/screenshot/{filename}` | 773 | – | **FileResponse(이미지)** | ⭐ **함수는 없지만 죽지 않았다** — 서버가 만든 `screenshot_url`(`:736`,`:892`)을 프론트가 `<img src>` 로 건다(`PrinterPrintControl.tsx:480`) |
| POST | `/scene/{scene_id}/estimate-time` | 801 | – | 모델 없음 | 🔴 **없음**(`estimatePrintTime` 미사용) |
| POST | `/scene/{scene_id}/interferences` | 829 | q:`collision_offset_mm` | 모델 없음 | 🔴 **없음**(`getInterferences` 미사용) |
| POST | `/scene/{scene_id}/screenshot` | 857 | q:`view_type,image_size_px` | 모델 없음 | 🔴 **없음**(`saveScreenshot` 미사용) |
| POST | `/presets/{preset_id}/print` | 900 | q:`printer_serial` | `PrintJobResponse` | 🔴 **없음**(`printWithPreset` 미사용) |

**메모 · 알림**

| 메서드 | 경로 | 줄 | 응답 | 호출자 |
| --- | --- | --- | --- | --- |
| GET | `/notes/{print_guid}` | 939 | 모델 없음 | 🔴 **없음**(`getNotes` 미사용 — 화면은 `getNotesBulk` 를 쓴다) |
| GET | `/notes` | 962 | 모델 없음 | `localApi.ts:299`(q:`guids`) |
| POST | `/notes/{print_guid}` | 990 | 모델 없음 | `localApi.ts:303` |
| PUT | `/notes/{note_id}` | 1019 | 모델 없음 | `localApi.ts:310` |
| DELETE | `/notes/{note_id}` | 1051 | 모델 없음 | `localApi.ts:317` |
| GET | `/notifications` | 1072 | 모델 없음 | `localApi.ts:343` |
| POST | `/notifications/mark-read` | 1108 | 모델 없음 | `localApi.ts:347` |

**자동화 (셀 제어 · 한솔 계열)** — 🚨 **이 27개 전부 `response_model` 이 없다**

| 메서드 | 경로 | 줄 | 요청 | 호출자 |
| --- | --- | --- | --- | --- |
| POST | `/automation/commands` | 1176 | `AutomationCommandCreate` | `localApi.ts:441` |
| GET | `/automation/commands` | 1222 | q:`limit` | `localApi.ts:448` |
| POST | `/automation/commands/use` | 1235 | `AutomationCommandUseUpdate` | `localApi.ts:455` |
| POST | `/automation/control/{action}` | 1251 | – | `localApi.ts:472` |
| POST | `/automation/simul` | 1267 | q:`mode` | `localApi.ts:466` |
| GET | `/automation/state` | 1281 | – | `localApi.ts:462` |
| GET | `/automation/queues` | 1294 | – | `localApi.ts:478` |
| GET | `/automation/logs` | 1307 | q:`limit` | `localApi.ts:482` |
| GET | `/automation/manual/io/state` | 1320 | q:`board_no,count,io_type` | `localApi.ts:602` |
| POST | `/automation/manual/io/output` | 1371 | `AutomationIoWrite` | `localApi.ts:608` |
| POST | `/automation/manual/robot-send` | 1403 | `AutomationManualSend` | 🔴 **없음** |
| POST | `/automation/manual/vision-send` | 1427 | `AutomationManualSend` | 🔴 **없음** |
| GET | `/automation/manual/robot-status` | 1451 | – | `localApi.ts:544` |
| GET | `/automation/manual/vision-status` | 1479 | – | 🔴 **없음** |
| GET | `/automation/manual/comm-config` | 1507 | – | `localApi.ts:552` |
| POST | `/automation/manual/comm-config` | 1528 | `AutomationCommConfigUpdate` | `localApi.ts:561` |
| GET | `/automation/manual/modbus/registers` | 1554 | q:`start_addr,end_addr` | `localApi.ts:573` |
| **POST,PUT,PATCH** | `/automation/manual/modbus/write` | **1602** (`api_route`) | `AutomationModbusWrite` | `localApi.ts:579`(**POST 만**) |
| GET | `/automation/manual/modbus/write` | 1643 | q:`address,value` | 🔴 **없음** (쿼리 폴백) |

## 4-4. 비전 `app/vision/routes.py` (prefix `/api/v1/vision`) — 10개 · **전부 호출자 0**

| 메서드 | 경로 | 줄 | 요청 | 응답 | 호출자 |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/vision/health` | 41 | – | `VisionHealthResponse` | 🔴 |
| GET | `/api/v1/vision/cameras` | 60 | – | `CameraListResponse` | 🔴 |
| GET | `/api/v1/vision/cameras/{camera_id}` | 74 | – | `CameraResponse` | 🔴 |
| GET | `/api/v1/vision/devices` | 86 | – | `DeviceListResponse` | 🔴 |
| GET | `/api/v1/vision/devices/{device_type}/{device_id}` | 113 | – | `DeviceResponse` | 🔴 |
| GET | `/api/v1/vision/events` | 141 | q:`page,page_size` | `EventListResponse` | 🔴 |
| GET | `/api/v1/vision/events/latest` | 189 | q:`limit` | 모델 없음 | 🔴 |
| POST | `/api/v1/vision/simulate` | 216 | `SimulateRequest` | 모델 없음 | 🔴 (개발용) |
| POST | `/api/v1/vision/simulate/scenario` | 229 | `SimulateScenarioRequest` | 모델 없음 | 🔴 (개발용) |
| **WS** | `/api/v1/vision/ws` | 244 | – | 상태 변화 푸시 | 🔴 |

⭐ **"호출자 0" 이 곧 "모듈이 안 돈다" 는 아니다** — 실제 데이터 경로는 **MQTT**(`vision/mqtt_client.py`)
→ `camera_manager` → DB 이고, **이 HTTP 계층은 조회용 창구인데 아직 화면이 없다.**

## 4-5. 빈피킹 `app/binpick/routes.py` (prefix `/api/v1/binpick`) — 6개

| 메서드 | 경로 | 줄 | 요청 | 응답 | 호출자 |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/binpick/reports` | 119 | `BinPickReportIn` | `BinPickIngestResponse` **201** | 🥇 **`bin_picking/src/run_binpick_e2e.py:259`**(`--web-url` 기본 `…:8085/api/v1/binpick/reports`, `:40`) · `tests/test_binpick_ingest.py:81` |
| GET | `/api/v1/binpick/health` | 211 | – | `BinPickHealthResponse` | 🟡 **테스트만** (`test_binpick_ingest.py:289`) |
| GET | `/api/v1/binpick/scenes` | 234 | q:`page,page_size,gate_verdict,trusted_only,label` | `SceneListResponse` | 🟡 테스트만 |
| GET | `/api/v1/binpick/scenes/latest` | 274 | – | `Optional[SceneDetailResponse]` | 🟡 테스트만 |
| GET | `/api/v1/binpick/scenes/{scene_pk}` | 296 | – | `SceneDetailResponse` | 🟡 테스트만 |
| **WS** | `/api/v1/binpick/ws` | 317 | – | 장면 수신 푸시 | 🔴 **없음** |

## 4-6. 앱 레벨 · 정적

| 메서드 | 경로 | 파일:줄 | 인증 | 비고 |
| --- | --- | --- | --- | --- |
| GET | `/{full_path:path}` | `main.py:205` | 🔓 | SPA 폴백. `api/` `docs` `redoc` 로 시작하면 404 |
| GET | `/` | `main.py:229` | 🔓 | 🔴 **§2-2 로 가려짐** |
| GET | `/health` | `main.py:245` | 🔓 | 🔴 **§2-2 로 가려짐 — HTML 이 나온다** |
| Mount | `/assets` | `main.py:202` | 🔓 | `frontend/dist/assets` |
| GET | `/docs` `/redoc` `/openapi.json` `/docs/oauth2-redirect` | FastAPI 기본 | 🔓 | **인증 없이 스키마 전문 열림** |

---

# 5. 🔴 아무도 안 부르는 엔드포인트 (27개)

**판정 기준 3단** = ①프론트에 서비스 함수가 있나 → ②그 함수를 컴포넌트·훅이 import 하나 →
③프론트 밖(`sequence_service` · `bin_picking` · `scripts` · `deploy.bat` · 테스트)에 호출자가 있나.
**셋 다 아니면 🔴.**

| # | 엔드포인트 | 사유 |
| --- | --- | --- |
| 1 | `GET /api/v1/printers` | `getPrinters` 정의만 있고 import 0 |
| 2 | `GET /api/v1/printers/{serial}/refresh` | 프론트에 함수 자체가 없음 |
| 3 | `GET /api/v1/printers/{serial}/prints` | 〃 |
| 4 | `GET /api/v1/system/token-status` | 〃 |
| 5 | `GET /api/v1/system/config` | 〃 |
| 6 | `POST /api/v1/local/printers/discover` | `discoverPrinters` 미사용 |
| 7 | `GET /api/v1/local/presets/{preset_id}` | `getPreset` 미사용 |
| 8 | `PUT /api/v1/local/presets/{preset_id}` | `updatePreset` 미사용 |
| 9 | `POST /api/v1/local/presets/{preset_id}/print` | `printWithPreset` 미사용 |
| 10 | `GET /api/v1/local/scene/{id}/validate` | `validateScene` 미사용 |
| 11 | `GET /api/v1/local/materials` | `listMaterials` 미사용 |
| 12 | `POST /api/v1/local/scene/{id}/estimate-time` | `estimatePrintTime` 미사용 |
| 13 | `POST /api/v1/local/scene/{id}/interferences` | `getInterferences` 미사용 |
| 14 | `POST /api/v1/local/scene/{id}/screenshot` | `saveScreenshot` 미사용 |
| 15 | `GET /api/v1/local/notes/{print_guid}` | `getNotes` 미사용(화면은 `getNotesBulk`) |
| 16 | `POST /api/v1/local/automation/manual/robot-send` | `manualRobotSend` 미사용 |
| 17 | `POST /api/v1/local/automation/manual/vision-send` | `manualVisionSend` 미사용 |
| 18 | `GET /api/v1/local/automation/manual/vision-status` | `getManualVisionStatus` 미사용 |
| 19 | `GET /api/v1/local/automation/manual/modbus/write` | 쿼리 폴백 — 프론트는 POST 만 |
| 20~29 | **`/api/v1/vision/*` 10개 전부**(WS 포함) | 프론트에 `vision` HTTP 호출 0건 |
| 30 | `WS /api/v1/binpick/ws` | 구독자 0 |
| 31 | `GET /` · `GET /health` | **경로가 가려져 도달 불가**(§2-2) |

> ⚠️ **"지우자" 는 뜻이 아니다.** 10~14·16~18 은 **`AutomationManualPage`·`PrinterPrintControl` 이
> 쓰려고 만든 것**이고 vision 10개는 **화면이 아직 없는 것**이다. 🥇 **지금 의미는 "여기엔 회귀 감시가 없다"** —
> 고장 나도 아무도 모른다.

## 5-1. 🟡 "테스트만 부르는 것" 5개 (위와 분리해서 센다)

`GET /binpick/health` · `/binpick/scenes` · `/binpick/scenes/latest` · `/binpick/scenes/{pk}` (+`POST /reports` 는 실사용 있음)
⇒ **`tests/test_binpick_ingest.py` 가 유일한 호출자.** 운영 화면이 아직 없다.

## 5-2. ⭐ "프론트가 안 불러도 죽지 않은 것" 2개 — 이게 함정이다

| 엔드포인트 | 진짜 호출자 |
| --- | --- |
| `GET /api/v1/local/print/{job_id}` | 🥇 **`sequence_service/app/cell/printer_interface.py:86`** |
| `GET /api/v1/local/scene/{id}/screenshot/{filename}` | 🥇 **브라우저 `<img src>`** — 서버가 만든 `screenshot_url` 을 그대로 건다 |

📌 ***"프론트가 안 부른다" 를 "아무도 안 부른다" 로 읽으면 이 둘을 지운다.***
`GET /api/v1/printers/{serial}` 도 같은 형태(프론트 + `sequence_service` 양쪽).

---

# 6. 🔴 정의 없이 불리는 경로 (1개)

| 호출 | 실제 경로 | 문제 |
| --- | --- | --- |
| `frontend/src/services/api.ts:113` `fetchApi('/../health')` | `/api/v1/../health` → 브라우저 정규화 → **`/health`** | `/health` 는 **§2-2 로 가려져 HTML 을 반환** ⇒ `response.json()` 이 깨진다 |

🟢 **지금 사고는 안 난다** — `getHealthCheck` 를 **아무도 호출하지 않는다**(§5 #1 계열).
⇒ ⭐ **"안 불리는 함수" 가 "깨진 경로" 를 가리고 있다.** 부르는 순간 터진다.

📌 그 외에는 **없다.** 프론트가 부르는 38종을 등록표와 대조해 전부 일치했다
(1차 대조에서 `{X}` 자리표시자 차이로 🔴 12건이 나왔으나 **내 정규화 버그였고 양쪽을 `{}` 로 맞추니 소멸**했다).

---

# 7. WebSocket 3개 — 인증이 특히 중요하다

| 경로 | 파일:줄 | 구독자 | 토큰 |
| --- | --- | --- | --- |
| `/api/v1/ws` | `api/routes.py:424` | `hooks/useWebSocket.ts:58` | 🚨 **안 붙인다** |
| `/api/v1/vision/ws` | `vision/routes.py:244` | 🔴 없음 | – |
| `/api/v1/binpick/ws` | `binpick/routes.py:317` | 🔴 없음 | – |

🚨 **`useWebSocket.ts:58` 은 `ws(s)://<host>/api/v1/ws` 로만 접속하고 `?token=` 을 붙이지 않는다.**
미들웨어는 `/api/` 라 **보호 대상**이고, 토큰이 없으면 **close 4401** 이다.
⇒ **loopback 이 아닌 클라이언트에서는 WS 가 닫힌다.**

⚠️ **지금 증상이 보이지 않는 이유 2가지** — ①`useDashboard` 에 **15초 폴링 폴백**이 있어 조용히 넘어간다
②§3-2 가 참이면(터널이 loopback 으로 보이면) **면제로 통과**해 버린다.
⇒ 🥇 **§3-2 를 확인하면 이 항목의 답도 같이 나온다.** **둘은 같은 질문이다.**

**SSE** = 저장소 전체에 **0건**(`StreamingResponse`·`text/event-stream`·`EventSource` grep 0).

---

# 8. `response_model` 실사용 검증

**선언 31건 / 미선언 49건.** 선언한 것은 핸들러가 실제로 그 모델을 만들거나, FastAPI 가 강제 변환한다.

| 형태 | 예 | 판정 |
| --- | --- | --- |
| 모델을 **직접 생성** | `LoginResponse(...)` · `SceneListResponse(...)` · `BinPickIngestResponse(...)` · `VisionHealthResponse(...)` | 🟢 일치 |
| **ORM/객체 반환 → 강제 변환** | `create_preset` → `service.create(data)` · `get_print_job` → `job` · `get_camera` → `camera` | 🟢 정상 경로 |
| **dict 반환 → 모델로 필터** | `prepare_scene`(`local/routes.py:587`) → `result["estimate"]` | 🟢 **확인함** — `preform_client.py:769` 가 **`SceneEstimate` 인스턴스를 직접 만든다**(`screenshot_url` 포함 `:783`) ⇒ 필드 유실 없음 |
| 🟡 **모델 없음(dict 직행)** | `/statistics` · `/system/*` · **`/automation/*` 27개 전부** · 대부분의 `/scene/*` | 응답 계약이 코드에만 있다 |

🚨 **🟡 의 실질 위험** = 프론트 타입(`localApi.ts` 제네릭 `AutomationState` 등)과 서버 dict 가
**어긋나도 아무 데서도 안 잡힌다.** 8/7 *"게이트 키를 추측해 조용히 `None` 이 나갔다"* 와 같은 계열이다.
⭐ 반대로 **`response_model` 이 있는 31건은 어긋나면 서버가 500 을 내거나 필드를 떨군다** — 최소한 드러난다.

---

# 9. `sequence_service` · `bin_picking` = 서버가 아니라 **클라이언트**

## 9-1. `sequence_service` → web-api (4개 경로)

`app/cell/printer_interface.py` — *"Thin HTTP client for web-api print endpoints used by PrinterSequence"*(`:12`)

| 줄 | 호출 | 용도 |
| --- | --- | --- |
| `:41` | `POST {base}/api/v1/local/upload` | STL 업로드(multipart 수동 조립) |
| `:70` | `POST {base}/api/v1/local/print` | 프린트 작업 생성 |
| `:79` | `GET {base}/api/v1/printers/{printer_serial}` | 프린터 상태 확인 |
| `:86` | `GET {base}/api/v1/local/print/{job_id}` | 작업 상태 폴링 |

🥇 **이 4개가 loopback 면제(§3-1)의 실제 수혜자다** — 5/29 JWT 회귀 사고의 fix 대상이 정확히 이 경로다.

## 9-2. `bin_picking` → web-api (1개 경로)

`src/communication/web_reporter.py:192 http_transport(url)` — **URL 을 인자로 받는 범용 전송기**.
실제 URL 은 `src/run_binpick_e2e.py:40` 의 `--web-url` 기본값 = `http://127.0.0.1:8085/api/v1/binpick/reports`
⇒ `:259` 에서 주입. 🟢 **URL 을 코드에 박지 않은 설계**(8/7 *"엔드포인트 미확정 → transport 분리"* 의 결과).

## 9-3. HTTP 가 아닌 통신 (조사 범위 밖이나 혼동 방지용)

| 경로 | 실체 |
| --- | --- |
| `bin_picking/.../pick_socket_server.py` | **raw TCP 5000** — 로봇 펜던트가 붙는다. HTTP 아님 |
| `sequence_service/app/cell/modbus_protocol.py` | **Modbus TCP 502** — 우리가 마스터 |
| `web-api/app/vision/mqtt_client.py` | **MQTT 구독** |
| `web-api/app/local/preform_client.py` | **PreFormServer(외부 프로세스) HTTP 클라이언트** — 우리 엔드포인트가 아니다 |

## 9-4. 부록 — `factory-pc/file_receiver.py` (별도 HTTP 서버 1개)

조사 대상 3곳 밖이지만 **web-api 가 이걸 호출**하므로 같이 적는다. `BaseHTTPRequestHandler` · 포트 8089.

| 메서드 | 경로 | 줄 |
| --- | --- | --- |
| POST | `/upload` | `:13` |
| GET | `/` | `:41` |
| GET | `/screenshots/{filename}` | `:48` |

🔓 **인증 없음.** 🚨 위 §4-3 의 `screenshot_url` 과 **경로 이름이 비슷하지만 다른 서버**다 — 혼동 주의.

---

# 10. 요약 숫자

| 항목 | 수 |
| --- | --- |
| 등록 엔드포인트(라우터) | **80** |
| ├ HTTP | 77 |
| └ WebSocket | **3** |
| 앱 레벨(`/`·`/health`·SPA 폴백) | 3 (**그중 2개 도달 불가**) |
| FastAPI 기본(`/docs` 등) | 4 (**인증 없음**) |
| 정적 mount | 1 |
| 프론트가 부르는 경로 | **38종** |
| 🔴 아무도 안 부르는 것 | **27** |
| 🟡 테스트만 부르는 것 | 4 |
| 🔴 정의 없이 불리는 경로 | **1** |
| `response_model` 선언 / 미선언 | 31 / 49 |

---

# 부록 — 재현 명령

```bash
# 1. 권위 있는 등록표 (§1 스크립트)
cd web-api && venv/bin/python -c "
import os; os.environ.setdefault('DEBUG','true')
from app.main import app
print(len(app.routes))"

# 2. §2-2 가려짐 실증
cd web-api && venv/bin/python -c "
import os; os.environ.setdefault('DEBUG','true')
from fastapi.testclient import TestClient; from app.main import app
r=TestClient(app).get('/health'); print(r.status_code, r.headers['content-type'])"

# 3. 미들웨어 보호 규칙
sed -n '31,43p'   web-api/app/core/jwt_middleware.py     # PUBLIC_API_PATHS
sed -n '105,110p' web-api/app/core/jwt_middleware.py     # loopback 면제

# 4. 프론트 호출자
grep -nE "fetchApi|fetchLocalApi" frontend/src/services/*.ts
grep -n  "wsUrl" frontend/src/hooks/useWebSocket.ts

# 5. 프론트 밖 호출자
grep -n "/api/v1" sequence_service/app/cell/printer_interface.py
grep -n "web-url" bin_picking/src/run_binpick_e2e.py
grep -n "api/v1"  scripts/deploy_servers.sh deploy.bat

# 6. sequence_service·bin_picking 에 HTTP 서버가 없다는 근거
grep -rnE "FastAPI|Flask|http\.server|BaseHTTPRequestHandler" sequence_service bin_picking --include=*.py
```

⚠️ **이 조사가 답하지 않는 것** = §3-2(터널이 loopback 으로 보이나) 는 **공장 PC 의 cloudflared 설정**이 있어야 판정된다.
저장소 안에는 그 설정이 없다.
