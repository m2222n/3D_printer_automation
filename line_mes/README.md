# line_mes — 라인 MES 관측 도메인

"배치(빌드플레이트)와 부품이 지금 어디 있나"를 기록하는 순수 파이썬 패키지.
HTTP 도, 상주 프로세스도 없다 — `web-api` 와 `sequence_service` 가 `import` 해서 쓴다.

## 파일

| 파일 | 역할 |
|---|---|
| `contract.py` | 이벤트 4종 `Spawn` · `State` · `Moved` · `Split` (dataclass · `to_dict`/`from_dict`). **두 서비스가 닿는 유일한 경계** |
| `state_engine.py` | `StateEngine.handle(event)` — 이벤트를 받아 `product_state` · `product_event` 갱신 · 채번 |
| `publish.py` | `LinePublisher` — 논블로킹 발행기 (`emit_state` · `emit_moved`). 호출자는 `put_nowait` 한 줄, PG 접속은 데몬 스레드 |
| `schema.sql` | PostgreSQL 14+ 테이블 18 · 뷰 24 · 함수 2 · 트리거 1 (설명 = `schema.md`) |
| `topology.yaml` | 라인 · 노드 · 칸 · 경로 · 반송자원 정의. **활성 라인은 하나** (`active: true` = web-api `.env` `LINE_ID`) |
| `topo_sync.py` | `python -m line_mes.topo_sync --check \| --plan \| --apply` — yaml 을 DB 에 적재. 프린터 시리얼은 `web-api/.env` `PRINTER_SERIAL_MAP` 에서 주입 |
| `simulator.py` | `python -m line_mes.simulator` — 이벤트를 흘려 뷰를 검증하는 개발 도구 |
| `tools/dev_up.sh` | 개발 PostgreSQL + Grafana 기동 |
| `tools/dev_reset.sh` | 개발 DB 재생성 → 스키마 → 토폴로지 → 시뮬 → 결과 조회 (sudo · `PGPASSWORD` 필요) |

## 원칙

- **의존은 들어오기만 한다** — 이 패키지는 표준 라이브러리 · `psycopg` · `pyyaml` 외 아무것도 import 하지 않는다.
- **발행은 관측이다** — 큐가 차면 버리고, 엔진이 거부해도 로그만 남긴다. 제어는 관측 때문에 멈추지 않는다.
- **위치를 바꾸는 것은 `Moved` 뿐**, 채번도 그때만. 카메라 · 프린터 API 는 `State` 만 낸다.
- **참조 해석은 스레드가 한다** — 호출자는 자기 어휘로 말한다: `("printer_serial", …)` · `("mqtt", "wash_1")` → `node.external_ref` 역조회, `cmd_id` → `unit`.
- **`LINE_DSN` 이 비면 전부 no-op** — DSN 없는 서버에서도 import 와 호출이 무해하다.

## 설치 · 설정

```bash
pip install -r requirements.txt            # 리포 루트 — `-e .` 로 이 패키지가 함께 깔린다
export LINE_DSN=postgresql://user@host/db   # 비번은 DSN 에 넣지 않는다 → PGPASSWORD 또는 .pgpass
psql "$LINE_DSN" -f line_mes/schema.sql
python -m line_mes.topo_sync --check       # → --plan → --apply
python -m line_mes.simulator --minutes 600 --speed 500 --spawn-every 700
```

`web-api/.env` 의 `LINE_DSN` 을 채우면 **한 값으로 세 층이 켜진다** — `/api/v2` 라우트 · 두 서비스의 발행 · 프론트 라인 탭(`/system/config.line_mes`).

## 누가 발행하나

| 이벤트 | 발행 지점 | 소스 |
|---|---|---|
| `Spawn` | web-api `app/local/line_publish.py` (`/local/print` 성공 직후) | ADAPTER |
| `State` 프린터 RUN/HOLD | web-api 폴링 서비스 → `app/line/publisher.py` | ADAPTER |
| `State` 프린터 DONE · `Moved` 로봇 | sequence_service `app/cell/line_events.py` | ADAPTER · ROBOT |
| `State` 세척기 · 경화기 | web-api 비전 MQTT 클라이언트 | CAMERA |
| `Split` · `Moved` · `State` 작업자 | web-api `app/line/routes_write.py` (W1~W6) | MANUAL |

## 재배치 날 바꿀 것

`topology.yaml` 의 두 라인 `active` 를 서로 바꾸고 `topo_sync --apply`, 같은 날 web-api `.env` `LINE_ID` 도 함께. 재배치 전에 목표 라인을 활성화하면 unit 이 부품 분리대 앞에서 영영 멈춘다.

문서: `schema.md`(테이블 · 뷰 · 제약 · 알려진 약점) · `docs/juhee/03_MES_v2_설계/서비스_역할_구조.md` · `docs/juhee/04_API_명세/20260921_API명세.md`

---

_Last updated: 2026-10-02_
