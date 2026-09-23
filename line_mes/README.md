# line_mes — 라인 MES 관측 도메인

| 파일 | 역할 |
|---|---|
| `contract.py` | M2 → M3a 이벤트 4종(Spawn · State · Moved · Split). **유일한 경계** — web-api 와 sequence_service 가 둘 다 import |
| `state_engine.py` | M3a. 이벤트를 받아 `product_state`·`product_event` 갱신 · 채번 |
| `schema.sql` | M4. PostgreSQL 테이블 · 뷰 · 트리거 (문서 = `schema.md`) |
| `topology.yaml` | 라인·노드·경로·반송자원 정의. `topo_sync` 가 DB 에 적재 |
| `topo_sync.py` | `python -m line_mes.topo_sync --check|--plan|--apply`. 프린터 시리얼은 `web-api/.env` `PRINTER_SERIAL_MAP` 에서 주입 |
| `simulator.py` | `python -m line_mes.simulator` — 이벤트를 흘려 뷰를 검증하는 개발 도구 |
| `tools/dev_reset.sh` | 개발 DB 재생성 → 스키마 → 토폴로지 → 시뮬 (sudo 필요) |

설치: 리포 루트 `pip install -r requirements.txt` (`-e .` 포함). 접속: `LINE_DSN` 환경변수, 비번은 `PGPASSWORD`.
HTTP 계층은 여기 없다 — `web-api/app/line/` 이 이 패키지를 호출한다. 계획 = `docs/plan/20260922_API개발_전체계획.md`.
