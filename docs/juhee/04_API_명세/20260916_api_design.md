작성 2026-09-16 (화) KST · 대상 = **신규 모니터링·제어 API**
🔒 **코드 변경 0건** — 명세만. 구현은 이 문서가 합의된 뒤.

📌 읽은 것 = `docs/juhee/01_조사_실측/20260909_api_survey.md`(요청문의 `20260916_api_survey.md` 는 **이 파일이다** — 날짜만 다르다) ·
`schema.sql` · `contract.py` · `topology.yaml` · `state_engine.py` ·
`docs/juhee/01_조사_실측/20260909_schema_survey.md` · `docs/juhee/02_개발계획/20260914_coexistence_plan.md` ·
`docs/juhee/03_MES_v2_설계/모듈 상세 설계.md`(M4·M5) · `docs/juhee/03_MES_v2_설계/모니터링 대시보드 상세.md` ·
와이어프레임 = **`docs/juhee/07_FE_병합_스냅샷/20260916_fe_merged.html`**(확정본) + `docs/juhee/06_와이어프레임_HTML/wireframe_pages.html`

---

# 0. 한 줄 결론

> **web-api 에 `/api/v2` 라우터 하나를 더한다. 읽기 11개 · 쓰기 6개 · WebSocket 0개.**
> 읽기는 M4 뷰를 얇게 감싸고(신규 뷰 5개 추가), 쓰기는 **전부 이벤트 4개 + `judgement`/`command_log`** 로만 간다.
> **`product_state` 직접 UPDATE 0건.**

🔴 **그러나 이 명세대로 다 만들 수는 없다** — 화면이 요구하는데 **스키마에 자리가 없는 것이 4건**
(설비 중지 상태 · 가동 시간 입력 · 측정 스펙 · 박스 마감)이고, **데이터원이 아예 없는 것이 1건**(인터록)이다.
해당 엔드포인트는 **설계를 유보**하고 §9 에 모았다.

---

# 1. 붙일 위치 — 3안 비교와 권고

## 1-1. 비교

| | **A. web-api 에 라우터 추가** | B. 별도 서비스 | C. 기존 라우터 확장 |
| --- | --- | --- | --- |
| DB | 🔴 한 프로세스가 **DBMS 3개**(SQLite + MariaDB + PG) → §1-6 | 🟢 PostgreSQL 만 | 🔴 A 와 같음 |
| 인증 | 🟢 기존 미들웨어 재사용 | 🔴 새로 정해야 (JWT 발급처가 web-api) | 🟢 A 와 같음 |
| 배포 | 🟢 프로세스 그대로 | 🔴 프로세스 +1 · 포트 +1 · NSSM 항목 +1 | 🟢 그대로 |
| 프론트 | 🟢 same-origin | 🔴 CORS 또는 프록시 | 🟢 same-origin |
| 기존 80개 영향 | 🟢 0 (경로가 안 겹친다 §1-3) | 🟢 0 | 🔴 **`/api/v1/local` 이 51개에서 더 커진다** |
| 계약 분리 | 🟢 `/api/v2` 로 버전이 갈린다 | 🟢 완전 분리 | 🔴 v1 dict 관행과 섞인다 |
| 관측/제어 경계 | 🟢 coexistence §3-5 와 일치 | 🟡 그 문서에 없는 4번째 프로세스 | 🔴 제어 라우터에 관측이 섞인다 |

## 1-2. 권고 = **A**

근거 셋. 전부 이미 문서화된 판단이고 새로 만든 전제가 아니다.

1. **이미 정해져 있다.** `20260914_coexistence_plan.md` §3-5 최종 형태 —
   *"`web-api/` API — HTTP · WS · 인증 · 정적. **두 DB 를 읽기만**, 쓰기는 소유자 경유"*.
   A 는 그 그림 그대로다. B 는 그 문서에 없는 프로세스를 하나 만든다.
2. **서버를 늘린 선례가 없다.** 조사 §9 — `sequence_service` 와 `bin_picking` 은
   HTTP 서버를 **0개** 정의하고 전부 **클라이언트**다. B 는 이 프로젝트에서 처음 있는 형태가 된다.
3. **C 는 v1 의 문제를 물려받는다.** `/api/v1/local` 은 이미 51개이고 그중
   `/automation/*` 27개가 **전부 `response_model` 없이 dict 직행**이다(조사 §8).
   같은 라우터에 넣으면 "여기는 dict, 저기는 모델" 이 한 파일에 섞인다.

⚠️ **A 가 공짜는 아니다 — 받아들이는 비용 3가지를 적어둔다.**

| 비용 | 내용 | 완화 |
| --- | --- | --- |
| 🥇 **DBMS 3개** | 🚨 **초안이 "SQLite + PG 둘" 이라 적은 것은 틀렸다** — web-api 는 이미 **SQLite + MariaDB** 를 본다(`local/automation_db.py:23`). v2 를 붙이면 **셋** | 트랜잭션은 안 건넌다(🟢) 그러나 **운영 절차가 3벌**이 된다 → §1-6 |
| loopback 면제 상속 | §7 · 조사 §3-2 미확인 | 🔴 **판정 유보** — §7 에 조건부 권고 |
| 🥇 **인스턴스 3개 중 하나에서만 돈다** | web-api 는 **공장 PC · 카카오 VM · 6000** 셋에서 돈다. PG 에 닿는 것은 그중 하나뿐 | §1-4 |

## 1-3. 경로 충돌 확인 (A6) — 실측

```
등록 경로 88 · /api/ 80
prefix: /api/v1/{auth,binpick,dashboard,local,printers,prints,statistics,system,vision,ws}
/api/v2 충돌: 없음
SPA 폴백 규칙: if full_path.startswith("api/") or ... → 404
```

⇒ 🟢 **`/api/v2/*` 는 비어 있고, SPA 폴백(`GET /{full_path:path}`)이 `api/` 를 제외하므로 가려지지 않는다.**
🚨 **단 등록 순서를 지켜야 한다** — 라우터 include 는 `main.py:192-196` 블록 안에서 하고,
`create_app()` 안의 폴백 등록(`main.py:205`)보다 **앞**이어야 한다. 조사 §2-2 의 `GET /health` 가
그 순서를 어겨 **HTML 을 반환**하고 있다. 같은 실수를 반복하지 않는다.

📌 **재현 명령**
```bash
cd web-api && DEBUG=true venv/bin/python -c "
from app.main import app
from fastapi.routing import _IncludedRouter
ps=[]
for r in app.routes:
    if isinstance(r,_IncludedRouter):
        ps += [r.include_context.prefix+s.path for s in r.original_router.routes]
    else: ps.append(getattr(r,'path','?'))
print([p for p in ps if p.startswith('/api/v2')] or '충돌 없음')"
```

## 1-4. 🔴 A 를 택하면 생기는 질문 — 어느 인스턴스에서 도나

web-api 는 세 곳에서 돈다(CLAUDE.md 운영 인프라). 신규 라우터는 **PostgreSQL 에 닿는 인스턴스에서만** 의미가 있다.

| 인스턴스 | 역할 | v2 라우터 |
| --- | --- | --- |
| **공장 PC** | 실제 프린터 제어 · MariaDB 소유 | 🟢 **여기서 돈다**(PG 가 같은 머신일 때) |
| 카카오 VM · 6000 | 모니터링 · 개발 | 🔴 PG 에 못 닿으면 **503 이어야 한다** |

⇒ **판정** — `DATABASE_URL_LINE`(가칭) 이 비면 **v2 라우터를 include 하지 않는다.**
경로 자체가 없으면 404 이고, 이는 "있는데 500" 보다 낫다.

🚨 **그래서 `/api/v2/health` 를 만들지 않는다.** 처음 초안에는 있었는데
**§8 자가검증이 "호출 화면 없음" 으로 잡아냈다** — 조사가 찾은 죽은 27개와 같은 형태였다.
프론트가 v2 탭을 감추는 근거는 **R4(`control-menu`) 의 404/503 로 충분하다**. 셸은 그 응답이 어차피 필요하다.

## 1-6. 🔴 "v1 과 v2 의 DBMS 를 통일하면 어떤가" — 측정하고 답한다

질문이 옳다. **위 §1-1 의 DB 행을 실제보다 낙관적으로 적었다.**

### 지금 web-api 가 보는 DBMS (실측)

| DB | 무엇 | 어디서 | 드라이버 |
| --- | --- | --- | --- |
| **SQLite** | 프리셋·작업·알림·메모·비전·빈피킹 8테이블 | `core/config.py:117` `sqlite:///./presets.db` | 내장 |
| **MariaDB** | `cell_state`·`print_command`·`automation_log`(제어 DB, 소유는 `sequence_service`) | `local/automation_db.py:23` ← `config.py:140` | `pymysql` |
| PostgreSQL | (v2 로 추가하려는 것) | – | `psycopg` **신규** |

⇒ **"두 DB" 가 아니라 이미 둘이고, v2 를 붙이면 셋**이다. 드라이버도 3개가 된다.
🚨 `requirements.txt` 의 **`alembic` 은 주석 처리**되어 있다 — **지금 마이그레이션 도구가 없다.**

### 통일 방향 두 가지를 각각 재봤다

**① v2 를 SQLite 로 내린다 → 🔴 불가.** `schema.sql` 을 SQLite 에 그대로 먹여본 실측:

```
뷰 19개 중 통과 3 · 실패 16      (통과: v_node_order · v_unit_lineage · v_retrievable)
함수 2개는 시도조차 못 함        (SQLite 에 CREATE FUNCTION 이 없다)
```

막는 구문 = `::캐스트` 34회 · `timestamptz` 14회 · `uuid`/`gen_random_uuid` 9회 ·
`extract(epoch FROM …)` 8회 · `bigserial` 4회 · `jsonb` 3회 ·
`string_agg(… ORDER BY)` 2 · `array_agg` 2 · `DISTINCT ON` · `CROSS JOIN LATERAL` + `generate_series` ·
`text_pattern_ops` · PL/pgSQL 트리거.

⇒ **M4(조회 계약) 를 통째로 다시 쓰는 일**이고, 그러면 *"뷰가 M4 와 M5 사이의 계약"* 이라는
설계 근거 자체가 사라진다. 🥇 특히 **`next_place()` 를 애플리케이션으로 올리면
*"M3b 지시와 M3a 기록이 같은 함수를 쓴다"* 는 요점이 깨진다** — 두 벌이 갈라질 수 있는 자리가 정확히 그거다.

**② v1 을 PostgreSQL 로 올린다 → 🟢 기술적으로 싸다. 막는 것은 운영이다.**

| | 실측 |
| --- | --- |
| v1 SQLite 쪽 | **SQLAlchemy ORM 4모델 · 36컬럼 · FK 0 · 뷰 0 · 트리거 0** |
| SQLite 전용 SQL | **0건** (원시 SQL 은 전부 MariaDB 쪽이고 그건 `SHOW COLUMNS`·`ADD COLUMN … AFTER` 로 **MySQL 전용**) |
| 종속 지점 | `config.py:117` **기본값 한 줄** |

⇒ **DSN 만 바꾸면 대체로 돈다.** 그런데 막는 것이 셋 있다.

| 막는 것 | 내용 |
| --- | --- |
| 🥇 **인스턴스가 3대다** | web-api 는 **공장 PC · 카카오 VM · 6000** 에서 돌고 **각자 자기 SQLite** 를 갖는다. v1 을 PG 로 올리면 **PG 를 3벌 깔거나, 두 대가 인터넷 너머 PG 를 본다.** 이사가 하나가 아니라 셋이다 |
| **원칙을 깬다** | `20260914_coexistence_plan.md` §1-0 — *"기존 DB DDL 변경 0건 · 기존 운영 코드 변경 0건"*. 이것이 첫 위반이 된다 |
| **시점** | 운영 데이터가 있다(알림 282행 등 · CLAUDE.md). 10/31 앞에서 **몇 달 돌던 것을 건드리는 쪽**의 위험이 얻는 것보다 크다 |

### ⇒ 권고

1. **지금은 A 그대로** — v2 만 PG. DBMS 3개를 **의식적으로 받아들인다**(전에는 모르고 적었다).
2. **방향은 ② 가 맞다** — 통일한다면 **v1 → PG** 이고 그 반대는 측정상 불가다.
   **P5(10/31 이후) 항목으로 등록**한다. 그때는 카카오·6000 인스턴스를 어떻게 할지가 본 안건이다.
3. 🥇 **지금 당장 통일할 수 있는 것은 DBMS 가 아니라 "관리 방식" 이다** — 이건 싸고 지금 한다.

| 통일 대상 | 지금 | v2 에서 |
| --- | --- | --- |
| 라이브러리 | SQLAlchemy 2.0 | 🟡 **읽기만 같게** — 🚨 아래 정정 |
| 엔진·세션 수명 | `local/database.py` 패턴 + FastAPI `Depends` | 🟢 **같은 패턴으로** |
| 마이그레이션 | 🔴 **없음**(`alembic` 주석) | 🟢 **v2 부터 alembic 을 켠다.** v1 은 나중에 같은 도구로 흡수 |
| 백업·모니터링 절차 | SQLite 파일 복사 · MariaDB 별도 | 🟡 PG 추가 = 3벌. **②가 끝나야 2벌이 된다** |

🚨🚨 **[2026-09-16 정정] 위 "v2 도 SQLAlchemy Core, `psycopg` 를 직접 쓰지 않는다" 는 읽기에만 참이다.**
`StateEngine` 은 **psycopg3 API** 를 쓴다 — `state_engine.py:27` `with self.conn.transaction():` 와
**`%s` 자리표시자 83곳**. 쓰기는 psycopg 를 직접 쓸 수밖에 없고,
엔진을 SQLAlchemy 로 고치는 것은 **유일한 검증 지점을 건드리는 일**이다.

```
SQLAlchemy Engine(postgresql+psycopg://) ─┬─ 읽기  conn.execute(text(...))            ← Core
                                          └─ 쓰기  conn.connection.driver_connection  → StateEngine(psycopg)
```
🔴 **이 그림은 미검증이다** — `StateEngine.handle` 의 `conn.transaction()` 이 SQLAlchemy 트랜잭션 안에서
세이브포인트로 동작하는지 실제로 돌려보지 않았다. 검증 절차 = `20260916_open_questions.md` A9.

⇒ **맞추는 것은 "읽기의 같은 라이브러리·같은 수명주기" 까지이고, 쓰기와 모델은 아니다.**

## 1-5. ⭐ 이 결정이 D2 를 확정시킨다

스키마 조사 §5 의 미결과 `20260914_coexistence_plan.md` §3-4 는 **"PostgreSQL 을 어디에 두나"** 를 열어뒀다.

> §3-4 — *"PG 가 **공장 PC** 면 프로세스 하나. 6000 등 다른 머신이면 **둘로 강제**된다"*

**A 를 택하면 그 분기가 닫힌다.**

- v2 라우터가 web-api 안에 있다 ⇒ web-api 프로세스가 PG 에 직접 커넥션을 연다
- web-api 는 **공장 PC 에서 돈다**(프린터 제어와 같은 프로세스, `main.py` 통합 런처)
- ⇒ **PG 는 공장 PC 에 두는 것이 자연스럽다.** 다른 머신에 두면 공장 PC 에서 나가는 DB 커넥션이
  인터넷 구간을 건너고, 끊기면 **관측이 아니라 제어 프로세스가 느려진다**

📌 **명세에 남기는 문장** — *"이 API 를 web-api 에 붙이는 결정은 PostgreSQL 을 공장 PC 에 두는 결정과 한 몸이다.
PG 를 다른 머신에 두기로 하면 A 는 재검토 대상이 된다."*
🔴 **PG 위치 자체는 아직 결정 사항이다** → §9-1

---

# 2. 화면 → 필요한 것 → 엔드포인트 (역방향)

🥇 **A1 의 근거가 되는 표다.** 왼쪽에서 오른쪽으로만 읽는다 — 화면이 없는 엔드포인트는 여기 나타날 수 없다.
확정 와이어프레임 = `20260916_fe_merged.html` 의 **신규 2탭**(라인 모니터링 · 공정 제어).

## S1. 라인 모니터링 › 설비 · 반송

| | |
| --- | --- |
| **필요한 것** | 요약 타일 4 · 반송 자원 상태/큐 · 공정 순서대로 늘어선 랙(칸별 점유·다음 반출)과 설비(베이별 개체·상태·진행률·대기 큐) · 구간별 반송 담당 |
| **데이터원** | `v_node_status` · `v_node_order` · `v_rack_slot` · `v_transporter_load` · `node.transporter_id` |
| **엔드포인트** | `GET /api/v2/lines/{line_id}/nodes`<br>`GET /api/v2/lines/{line_id}/transporters` |

⭐ 요약 타일 4개는 **별도 엔드포인트를 두지 않는다** — `nodes` 응답을 세면 나온다.
서버가 또 세면 *"뷰에 있는 계산을 API 에서 다시"* 가 된다.

## S2. 라인 모니터링 › 플레이트 파이프라인

| | |
| --- | --- |
| **필요한 것** | 행 = 재공 1건(배치·묶음·박스), 열 = 공정(`group_label`), 셀 = 완료 / 현재(대기·진행) / 미도달 |
| **데이터원** | 🆕 **`v_wip`** (없다 → §5-1) · `v_control_menu`(열 정의) |
| **엔드포인트** | `GET /api/v2/lines/{line_id}/wip`<br>`GET /api/v2/lines/{line_id}/control-menu` (열) |

## S3. 공정 제어 › 공통 (서브 탭 · 노드 선택)

| | |
| --- | --- |
| **필요한 것** | 서브 탭 목록(라벨 · 노드 수 · 화면 종류) — **하드코딩 금지**, 노드를 늘리면 탭이 는다 |
| **데이터원** | **`v_control_menu`** |
| **엔드포인트** | `GET /api/v2/lines/{line_id}/control-menu` |

## S4. 공정 제어 › MONITOR (출력·세척 / 경화기 / 빔피킹)

| | |
| --- | --- |
| **필요한 것** | ①투입 대기 큐(FIFO · 출처 · 수량 · 지금 넣을 수 있나) ②설비 블록(적재 개체 · 상태 · 경과/표준 · 진행률 · 대기 건수) ③투입 / 시작 · 중지 · 완료 |
| **데이터원** | 🆕 **`v_inbound_queue`**(§5-2) · `v_node_status` |
| **엔드포인트** | `GET /api/v2/lines/{line_id}/nodes` (재사용)<br>`GET /api/v2/nodes/{node_id}/inbound`<br>`POST /api/v2/moves` (투입)<br>`POST /api/v2/nodes/{node_id}/state` (시작·완료) |

🔴 **중지**는 유보 → §9-3. 🔴 **가동 시간 입력**도 유보 → §9-4.

## S5. 공정 제어 › BATCH_SPLIT (부품 분리)

| | |
| --- | --- |
| **필요한 것** | ①직전 랙 목록(적재/칸 수) ②칸 목록(사용/용량 · 내용물) ③배치 FIFO 대기열(순번 · 표시명 · 종수 · 파트별 수량 · 지금 작업 가능) ④파트별 OK/NG + NG 사유 ⑤묶음(누적 수 · 정원 · 출처 배치별 구성 · 넘길 다음 노드) |
| **데이터원** | 🆕 `v_node_prev`(§5-3) · `v_rack_slot` · `v_slot_map` + `v_retrievable` + `v_unit_summary` + `unit_content`·`part` · 🆕 `v_group_at_node`(§5-5) |
| **엔드포인트** | `GET /api/v2/nodes/{node_id}/source-racks`<br>`GET /api/v2/racks/{node_id}/slots`<br>`GET /api/v2/racks/{node_id}/slots/{slot_no}/queue`<br>`GET /api/v2/nodes/{node_id}/groups`<br>`POST /api/v2/units/{unit_id}/split`<br>`POST /api/v2/moves` (묶음 넘기기) |

## S6. 공정 제어 › PART_JUDGE (서포트 제거 · 치수검사)

| | |
| --- | --- |
| **필요한 것** | ①대기 묶음 ②부품별 행(표시명 · 파트넘버/이름 · 최신 판정 · 측정값 입력 + 공차) ③OK/NG · 일괄 OK ④박스 적재(담긴 수 / 정원 · 수동 마감) |
| **데이터원** | 🆕 `v_group_at_node` · 🆕 `v_node_parts`(§5-4, `v_latest_judgement`·`part.attrs` 포함) |
| **엔드포인트** | `GET /api/v2/nodes/{node_id}/groups`<br>`GET /api/v2/nodes/{node_id}/parts`<br>`POST /api/v2/judgements`<br>`POST /api/v2/moves` (OK → 박스 합류 `join_group`)<br>`POST /api/v2/commands` (박스 수동 마감) |

🔴 **측정 스펙**(어느 노드가 측정값을 받나)은 스키마에 자리가 없다 → §9-5.
🔴 **박스 마감**도 자리가 없다 → §9-6.

## S8. 공정 제어 › 로봇암 수동제어 (TRANSPORT) — 🆕 2026-09-21

| | |
| --- | --- |
| **필요한 것** | ①**반송 자원** 목록 + 담당 구간 + 연결 상태 ②**명령 카탈로그**(라벨 · 무엇을 보내나 · 값의 출처 · 검증 여부) ③고른 명령의 **보낼 값 미리보기** ④실행 ⑤실행 로그 |
| **데이터원** | `v_transporter_load`(①) · **`v_node_status.transporter_id`**(① 담당 구간 — R1 재사용) · **`transporter.attrs->'commands'`**(②③) · `command_log`(⑤) |
| **엔드포인트** | `GET /api/v2/transporters/{transporter_id}/commands`<br>`POST /api/v2/transporters/{transporter_id}/commands/{command_id}`<br>`GET /api/v2/lines/{line_id}/transporters` (R2 재사용) |

🥇 **이 화면의 요점 = 작업자가 청크를 타이핑하지 않는다.**
기존 「자동화 수동제어」는 **IP·포트와 Modbus 주소·값을 직접 넣어 Write** 한다
(`AutomationManualPage.tsx:367` `Robot IP` · `:404` `Address`/`Value`).
여기서는 **동작 명령만 고르고**, 어느 레지스터에 무엇을 쓰는지는 서버가 안다.

⇒ 🚨 **그래서 명령 목록을 화면이나 API 코드에 하드코딩하면 안 된다** — `v_control_menu` 와 같은 이유다.
줄을 더하면 버튼이 늘어야 하고 화면 코드는 안 바뀌어야 한다.

🔴 **검증 안 된 명령은 서버가 `verified: false` 로 내려보내고 화면이 잠근다.**
지금 실물로 확인된 것은 **이송 핸드셰이크 4개**(`config.py` 레지스터 상수)와
**그리퍼 열기 2단계 = 약 84mm**(9/9 실측) **뿐**이다.
나머지 그리퍼 단계·스핀들·빈피킹 자세는 미확인이고, 특히 스핀들은
`rodi_pick_sequence.js` 가 **`SPINDLE_API='none'`(호출하지 않고 로그만)** 으로 두고 있다.
**추측한 함수로 스핀들을 돌리지 않는다** 는 그 판단을 API 가 그대로 물려받는다.

### 🚨 세 가지가 이 화면의 전제다 (2026-09-21 태민님 정정 반영)

**① 반송 자원은 하드코딩하지 않는다 — `topology.yaml` `transporters:` 가 정본**

| id | kind | 담당 | 명령 |
| --- | --- | --- | --- |
| `ARM-A` | ROBOT_ARM | 프린터 대기 랙 · 프린터 4 · 프린터 완료 랙 · 세척기 2 (**8곳**) | 이송 핸드셰이크 |
| `OP-CURE` | OPERATOR | 세척기 완료 랙 · 부품 분리대 · 서포트 제거대 · 경화기 2 · 치수검사 · 빔피킹 대기 랙 (**7곳**) | **없음**(빈 배열) |
| `ARM-B` | ROBOT_ARM | 빔피킹/드릴링/트림 (**1곳**) | 그리퍼 4 · 빔피킹 2 · 스핀들 1 |

⇒ ⭐ **자원 수도, 담당 구간도, 어떤 명령을 갖는지도 전부 데이터에서 나온다.**
🚨 **작업자(OPERATOR)도 반송 자원이다** — 화면에서 빼지 않고 **"보낼 명령 없음"** 으로 보인다
(`endpoint` 가 없으면 `auto_dispatch = false`). 빼버리면 라인에 사람이 있다는 사실이 화면에서 사라진다.

**② 그리퍼는 상태 하나에 신호 하나다 — 동작 명령이 아니다**


`rodi_pick_sequence.js` 의 `D_GEN_OUT_0~3` 4비트 조합이 **정해진 상태마다 하나씩** 붙어 있다.
그래서 카탈로그에 실리는 것은 *"열어라 / 닫아라 / 벌려라"* 가 아니라 **갈 상태**다:

| 라벨 | 4비트 | 벌림 |
| --- | --- | --- |
| 열기 1단계 | `1,0,0,0` | 40mm 🔴 **임의값** |
| **열기 2단계** | `0,1,0,0` | **84mm** 🟢 9/9 실측 |
| 열기 3단계 | `1,1,0,0` | 60mm 🔴 **임의값** |
| 열기 4단계 | `1,1,1,0` | 20mm 🔴 **임의값** |

🥇 **이산 단계다** — 임의 폭을 지정하는 입력칸이 없다. 값은 `topology.yaml` 의 `span_mm` 에서 온다.
🚨 **임의값을 실측값처럼 보여주면 안 된다** — 셋 다 `verified: false` 라 화면이 **실행을 잠그고
`(임의값)` 꼬리표**를 붙인다. 실측하면 **YAML 한 줄만** 고친다.
⚠️ 1단계에 40 을 넣은 것은 근거가 하나 있어서다 — 9/9 에 **45mm 부품을 못 물었으므로 45 미만**이다.
나머지 둘은 근거가 없다.

**③ 명령은 자원마다 다르다** — 담당 구간이 다르면 할 수 있는 일이 다르다.
`ARM-A` 에 그리퍼 단계가 뜨거나 `ARM-B` 에 세척기 이송이 뜨면 **그 자체가 버그**다.

### ✅ 2026-09-21 확정 4건

| # | 결정 | 비용 |
| --- | --- | --- |
| 1 | 카탈로그 = **`topology.yaml`** `transporters[].attrs.commands` | `transporter.attrs jsonb` 컬럼 1개 |
| 2 | S8 담당 구간 = **화면이 R1 을 `transporter_id` 로 필터** | 🥇 **0** — `v_node_status` 가 이미 그 컬럼을 낸다 |
| 3 | 그리퍼 폭 = **임의값 + `verified:false`**, 실측하면 YAML 수정 | 0 |
| 4 | W6 실행 = **기존 어댑터에 위임** (v2 는 Modbus·DO 를 직접 치지 않는다) | 0 |

🥇 **4번이 가장 중요하다** — v2 가 직접 치면 로봇 제어 경로가 둘이 되고,
한화 매뉴얼이 *"하나의 프로세스만이 제어권을 가진다"* 라 **어느 쪽이 쥐었는지 모르는 상태**가 된다.
⇒ W6 = ①`command_log` 기록 ②어댑터 호출 ③결과 반환. `send` 의 해석은 **어댑터 몫**이다.

🟢 **배선 확인** = `topology.yaml` 의 라벨을 고치면 와이어프레임 HTML 이 따라 바뀐다(그물 찢어 확인).

## S7. 🔴 화면이 없어서 만들지 않는 것 — 원칙 1 적용

| 만들지 않는 것 | 사유 |
| --- | --- |
| **`POST /api/v2/spawns`**(신규 배치 투입) | 투입은 **작업 지시** 화면의 일인데 그 화면은 **설계 전 스텁**이다. coexistence §4-1 도 *"`Spawn` 을 발행할 주체도, 주문을 만들 경로도 없다"* 로 같은 결론 |
| ~~**반송 지시 · 큐 순서변경 · 취소**~~ | 🚨 **[2026-09-21 일부 철회]** — 와이어프레임에 **로봇암 수동제어(S8)가 들어왔다.** 내가 trim 때 뺀 것을 근거로 *"화면이 없다"* 고 적었는데 **화면이 생겼으므로 그 근거는 소멸**한다. ⇒ **S8 이 요구하는 것만 설계한다**(아래). 🔴 **여전히 안 만드는 것 = 큐 순서변경·취소·예약** — 그건 M3b 데이터이고 화면에도 없다(P5) |
| **주문 보드 · 납기(`v_order_progress`)** | 뷰는 있으나 **확정 와이어프레임에 주문 화면이 없다.** 작업 지시 탭이 설계되면 그때 |
| **폐기 집계 · 계보 · 파트별 진척**(`v_scrap_summary`·`v_unit_lineage`·`v_part_progress`) | 같은 이유. 화면이 생기면 **뷰가 이미 있으므로 엔드포인트만 얹으면 된다** |
| **인터록 조회** | 🔴 데이터원이 DB 에 없다 → §9-7 |
| **`GET /api/v2/health`** | 🥇 **초안에 있었으나 뺐다.** 부르는 화면이 없었다 — 셸이 필요한 것은 *"v2 탭을 띄우나"* 이고 그 답은 **R4 의 404/503** 이 준다. §8 자가검증이 잡은 항목이다 |

⭐ **이 표가 이 설계에서 제일 중요하다.** 조사가 찾은 죽은 27개는 전부 이 칸이 비어 있던 것들이다.

---

# 3. 엔드포인트 명세

공통 — **prefix `/api/v2`**, 전부 **JWT 보호**(§7), 전부 **`response_model` 선언**(예외 0).
응답 모델은 `web-api/app/line/schemas.py`(신규)에 둔다. 시각은 전부 ISO8601 UTC.

## 3-1. 읽기 11개

| # | 메서드 · 경로 | 요청 | `response_model` | 사용 뷰 | 호출 화면 |
| --- | --- | --- | --- | --- | --- |
| R1 | `GET /lines/{line_id}/nodes` | q: `kind`(STATION\|RACK, 선택) | `NodeListResponse` | `v_node_status` + `v_node_order` + `v_rack_slot`(랙이면 `slots[]` 동봉) | S1 흐름 · S4 설비 블록 |
| R2 | `GET /lines/{line_id}/transporters` | – | `TransporterListResponse` | `v_transporter_load` | S1 반송 |
| R3 | `GET /lines/{line_id}/wip` | q: `page` `page_size` | `WipListResponse` | 🆕 `v_wip` | S2 파이프라인 |
| R4 | `GET /lines/{line_id}/control-menu` | – | `ControlMenuResponse` | **`v_control_menu`** | S3 서브 탭 · S2 열 |
| R5 | `GET /nodes/{node_id}/inbound` | – | `InboundQueueResponse` | 🆕 `v_inbound_queue` | S4 투입 대기 큐 |
| R6 | `GET /nodes/{node_id}/source-racks` | – | `RackListResponse` | 🆕 `v_node_prev` + `v_rack_load` | S5 ① 랙 선택 |
| R7 | `GET /racks/{node_id}/slots` | – | `SlotListResponse` | `v_rack_slot` | S5 ② 칸 선택 |
| R8 | `GET /racks/{node_id}/slots/{slot_no}/queue` | – | `SlotQueueResponse` | `v_slot_map` + `v_retrievable` + `v_unit_summary` + `unit_content`·`part` | S5 ③ 배치 대기열 |
| R9 | `GET /nodes/{node_id}/groups` | – | `GroupListResponse` | 🆕 `v_group_at_node` | S5 ⑤ 묶음 · S6 ① 대기 묶음 · S6 ④ 박스 |
| R10 | `GET /nodes/{node_id}/parts` | – | `PartJudgeListResponse` | 🆕 `v_node_parts` (`v_latest_judgement` 포함) | S6 ② 부품별 판정 |
| R11 | `GET /transporters/{transporter_id}/commands` | – | `RobotCommandListResponse` | `transporter.attrs->'commands'` (🆕 컬럼) | S8 ② 동작 명령 |

⭐ **R1 을 S1 과 S4 가 같이 쓴다** — 같은 질문(*"설비가 지금 어떤가"*)이라 엔드포인트를 나누지 않는다.
🚨 **R8 이 4개를 조인하지만 계산은 없다** — `retrievable` 는 `v_retrievable` 에 있는 행인지 여부(LEFT JOIN),
파트 구성은 `unit_content` 원본 행이다. **판정 로직을 API 가 다시 쓰지 않는다.**

### 응답 모델 골자 (필드는 전부 뷰 컬럼에서 온다)

```
NodeListResponse   { line_id, nodes: [ NodeRow ] }
NodeRow            { node_id, label, node_kind, node_type, ui_kind, group_label,
                     step_order, capacity, occupancy, status, display_id, display_ids,
                     part_label, part_qty, elapsed_s, std_cycle_s, progress_pct,
                     settle_left_s, transport_wait_s, transporter_id,
                     slots: [ SlotRow ] | null }          # 랙일 때만
SlotRow            { slot_no, capacity, used, free, contents }
TransporterRow     { transporter_id, label, kind, auto_dispatch, status,
                     queued, avg_wait_s, max_wait_s }
WipRow             { ref_kind: UNIT|GROUP, ref, display_id, part_label, part_qty,
                     node_id, node_label, step_order, display_status, waiting }
ControlMenuRow     { menu_label, ui_kind, step_order, node_count, node_ids }
InboundRow         { key, ref_kind: UNIT|GROUP, ref, label, qty,
                     from_node, from_label, ready, waiting_s }
SlotQueueRow       { unit_id, display_id, pos_no, retrievable, total_qty, kinds,
                     contents: [ {part_no, part_name, qty, qty_scrapped} ] }
GroupRow           { group_id, node_id, unit_qty, capacity,
                     sources: [ {parent_display_id, parts: {part_no: qty}} ] }
PartJudgeRow       { unit_id, display_id, group_id, part_no, part_name,
                     nominal, tol, verdict, value, judged_at }
RobotCommandRow    { command_id, group, label, hint,
                     send: { kind: DO|MODBUS|SOCKET, … },   # 화면은 그대로 찍어 보여준다
                     source, verified, risk }               # source = 이 값이 어디서 왔나
```

🚨 **`display_status` 는 API 가 만들지 않는다** — `v_product_display` 의 `SETTLING` 파생을 그대로 싣는다.
`settle_left_s`(못 꺼냄) 와 `transport_wait_s`(안 옮겨감) 를 **둘 다** 내려보낸다. 화면이 구분해야 한다.

## 3-2. 쓰기 6개

| # | 메서드 · 경로 | 요청 | `response_model` | 번역되는 것 | 호출 화면 |
| --- | --- | --- | --- | --- | --- |
| W1 | `POST /units/{unit_id}/split` | `SplitRequest` | `WriteResult` | **`Split`** + `part_scrap` INSERT(NG) | S5 배치 완료 등록 |
| W2 | `POST /moves` | `MoveRequest` | `WriteResult` | **`Moved`** | S4 투입 · S5 묶음 넘기기 · S6 박스 합류 |
| W3 | `POST /nodes/{node_id}/state` | `StateRequest` | `WriteResult` | **`State`** | S4 시작 · 완료 |
| W4 | `POST /judgements` | `JudgementRequest` | `WriteResult` | `judgement` INSERT (+NG 면 **`Moved`**→EXIT) | S6 OK/NG |
| W5 | `POST /commands` | `CommandRequest` | `WriteResult` | `command_log` INSERT | S6 박스 수동 마감 · 기타 조작 기록 |
| W6 | `POST /transporters/{transporter_id}/commands/{command_id}` | `RobotRunRequest`(`actor`) | `WriteResult` | `command_log(kind='DEVICE')` INSERT **+ 어댑터 호출** | S8 ④ 실행 |

```
WriteResult { ok, event_ids: [int], unit_ids: [uuid], group_id, message, warnings: [str] }
```

**요청 골자**
```
SplitRequest     { node_id, outputs: [{part_no, qty}], scraps: [{part_no, qty, reason}],
                   group_id: str|null, actor }
MoveRequest      { unit_id | group_id,           # 정확히 하나 (contract.py Moved 규칙)
                   from_node, to_node, transporter_id, slot_no|null,
                   join_group: str|null, actor }
StateRequest     { status: RUN|DONE|ERROR, confidence: float|null, actor }
JudgementRequest { unit_id, node_id, verdict: OK|NG|RETEST, value: jsonb|null, note, actor }
CommandRequest   { kind, target, payload: jsonb, actor }
```

🚨 **`source` 는 요청 필드가 아니다** — 이 API 를 통과한 쓰기는 **서버가 `MANUAL` 로 고정**한다.
클라이언트가 `CAMERA`·`ROBOT` 을 사칭할 수 있으면 *"어디가 아직 수동인가"* 를 세는 지표가 무너진다.

🚨 **`actor` 는 필수다.** JWT 가 단일 계정(`admin`)이라 **토큰으로는 누가 했는지 알 수 없다**.
`command_log.actor` 가 그 자리이므로 요청에서 받는다. §7 참조.

## 3-3. 거부 규약

상태 엔진이 `ValueError` 로 거부하는 것(용량 초과 · FIFO 위반 · 토폴로지에 없는 이동 · 플레이트 소진 …
`state_engine.py:40,61,96,101,219,237,239,243,249`)은 **그대로 사용자에게 보여야 한다.**

| 상황 | HTTP | 본문 |
| --- | --- | --- |
| 상태 엔진 거부 | **409 Conflict** | `{detail: "<엔진 메시지 원문>", code: "ENGINE_REJECT"}` |
| 없는 노드·개체 | 404 | |
| 요청 형식 오류 | 422 (FastAPI 기본) | |
| PG 미연결 | 503 | §1-4 |

🚨 **400 으로 뭉개지 않는다** — *"경화기 빈 자리 없음"* 과 *"필드 누락"* 은 작업자가 할 일이 다르다.
⭐ 엔진 메시지는 이미 한국어 완성문이다(*"RK-CUR-WAIT-01 빈 자리 없음 — 투입 거부"*). **다시 쓰지 않는다.**

---

# 4. 쓰기 매핑 — 화면 액션 → 이벤트 4개

🔴 **`product_state` 를 직접 UPDATE 하는 경로는 0건이다.** 전부 아래를 거친다.

| 화면 액션 | 엔드포인트 | 이벤트 / 테이블 | 비고 |
| --- | --- | --- | --- |
| **배치 완료 등록**(파트별 OK/NG 확정) | W1 | **`Split`** + `part_scrap` INSERT | 🚨 **NG 는 `outputs` 에 넣지 않는다.** `Split` 은 OK 수량만 — 부품 unit 이 생기지 않아야 한다 |
| 서포트 제거대로 **넘기기**(묶음) | W2 | **`Moved(group_id=…)`** | 묶음째 **1건**. 부품 N 건이 아니다 |
| **경화기 투입**(작업자가 고른 노드) | W2 | **`Moved(group_id, to_node)`** | 🚨 경화기 개수 하드코딩 금지 — 목적지 후보는 R1 의 다음 MAIN 노드에서 온다 |
| 랙 → 설비 **투입**(배치) | W2 | **`Moved(unit_id, to_node)`** | FIFO 위반은 엔진이 거부(409) |
| 부품 **OK** | W4 | `judgement` INSERT | 다음 랙이 `count_by_group` 이면 **이어서 W2 `Moved(unit_id, join_group=BOX-…)`** |
| 부품 **NG** | W4 | `judgement` INSERT + **`Moved(→EXIT-SCRAP)`** | 🚨 두 번 호출하게 하지 않는다 — **W4 안에서 한 트랜잭션** |
| 설비 **시작 · 완료** | W3 | **`State(RUN\|DONE)`** | `ready_at` 은 엔진이 `post_delay_s` 로 계산 |
| 설비 **중지** | 🔴 **유보** | – | §9-3 — `State` 에 `HOLD` 가 없다 |
| **박스 수동 마감** | W5 | `command_log(kind='BOX_CLOSE')` | ✅ §9-6 해결 — `group_close` 로 조회 뷰가 본다 |
| **로봇암 동작 명령**(그리퍼·이송·스핀들) | W6 | `command_log(kind='DEVICE')` **+ 어댑터** | 🥇 **이벤트가 아니다** — 위치를 바꾸지 않는다. 위치는 로봇이 끝낸 뒤 `Moved` 로 온다. 🔴 `verified:false` 면 서버가 **거부**(409) |
| **인터록 토글** | 🔴 **유보** | – | §9-7 — 지금 화면의 체크박스는 목업 |
| 집진 ON/OFF · 그리퍼 · 원점 복귀 | **범위 밖** | (어댑터) `command_log` 에 결과만 | 확정 와이어프레임에서 **제거함** |

## 4-1. 🥇 경계 — 무엇이 이벤트가 아닌가

> **`judgement` 와 `command_log` 는 이벤트가 아니라 직접 INSERT 다. 위치를 바꾸지 않기 때문이다.**

| | 이벤트(4개) | 직접 INSERT |
| --- | --- | --- |
| 무엇 | `Spawn` `State` `Moved` `Split` | `judgement` · `command_log` |
| 바꾸는 것 | **`product_state`**(위치·상태·채번·용량) | 아무것도 안 바꾼다 — 기록만 |
| 검증 | 상태 엔진이 한다 | FK 와 CHECK 뿐 |
| 왜 | 검증이 두 벌이 되면 규칙이 갈라진다 | 엔진을 태우면 **"판정했다"가 "옮겼다"로 오해**된다 |

🚨 **NG 판정만은 둘이 붙어 있다** — 판정은 기록이고 폐기함으로 가는 것은 이동이다.
그래서 W4 가 **`judgement` INSERT + `Moved`** 를 **한 트랜잭션**으로 처리한다.
나눠서 클라이언트가 두 번 부르게 하면 **중간에 실패했을 때 판정만 남고 부품이 라인에 남는다.**

## 4-2. 트랜잭션 경계

```
W1  BEGIN → Split(엔진) → part_scrap INSERT × N → COMMIT
W4  BEGIN → judgement INSERT → (NG면) Moved(엔진) → COMMIT
그 외 단건
```
⭐ **엔진과 같은 커넥션을 쓴다.** `state_engine.StateEngine(conn)` 이 커넥션을 받는 구조라 그대로 된다.

---

# 5. ~~추가가 필요한~~ **추가한** 뷰 5개

✅ **2026-09-16 반영 완료** — `schema.sql` 에 들어갔고 실제 데이터로 확인했다
(뷰 19 → **24**, 행 곱하기 없음: `v_wip` 16 · `v_inbound_queue` 13 · `v_node_parts` 40 ·
`v_group_at_node` 10 · `v_node_prev` 36). 🆕 `v_group_at_node` 는 `group_close` 를 LEFT JOIN 해
`closed` 를 함께 낸다.

**판정 기준** — API 가 *계산*해야 하면 뷰를 추가한다. 단순 조인·필터면 추가하지 않는다.
(그래서 R8 은 4개를 조인하지만 새 뷰를 만들지 않았다)

| # | 뷰 | 왜 필요한가 | 재료 |
| --- | --- | --- | --- |
| 5-1 | **`v_wip`** | 파이프라인 행 = 재공 1건. **배치는 개체 단위, 부품은 묶음 단위**로 접어야 하는데 이 접기가 집계다. API 가 하면 화면마다 기준이 갈라진다 | `v_unit_summary` × `v_product_display` × `v_node_order` × `node` |
| 5-2 | **`v_inbound_queue`** | *"이 노드에 들어올 차례"* = `v_waiting_for` 는 **부품 단위**인데 화면은 **묶음 1줄**로 본다. 묶음 집계 + 출처별 맨 앞(FIFO) 판정이 계산이다 | `v_waiting_for` × `v_retrievable` × `v_unit_summary` |
| 5-3 | **`v_node_prev`** | *"직전 MAIN 노드"* 는 `route` 필터지만 **조건 3개**(MAIN · 활성 · 같은 라인)가 여러 화면에 흩어지면 갈라진다. `v_node_order` 가 이미 같은 조건을 쓴다 | `route`(MAIN) × `node`(is_active) |
| 5-4 | **`v_node_parts`** | 부품 행 하나에 **최신 판정 + 공차**가 붙어야 한다. 최신 판정은 `v_latest_judgement` 가 있으나 공차는 `part.attrs` jsonb 에서 꺼내야 하고, 그 키 이름을 API 가 알면 **8/7 "게이트 키 추측" 과 같은 계열**이 된다 | `product_state` × `v_unit_summary` × `part` × `v_latest_judgement` |
| 5-5 | **`v_group_at_node`** | 묶음 = `group_id` 꼬리표뿐이라 **"몇 개 담겼고 어디서 왔나"** 가 전부 집계다. 🥇 **작업대의 묶음과 랙의 박스가 같은 모양**이라 뷰 하나로 둘 다 덮는다 | `product_state` × `unit`(parent) × `node`(capacity·`count_by_group`) |

⚠️ **전부 `line_id` 로 묶는다.** M4 문서 경고 — *"노드가 두 라인에 속하므로 안 걸면 행이 곱해진다"*.
`topology.yaml` 에 `RESIN-1-ASIS` 와 `RESIN-1` 이 **둘 다 active** 라 실제로 곱해진다.

🔴 **5-5 는 "마감된 박스"를 표현할 수 없다** → §9-6.

---

# 6. 실시간 — 폴링 vs 푸시

## 6-1. 판정 = **WebSocket 을 만들지 않는다** (A8)

근거 넷.

1. **선례가 나쁘다.** 조사 §7 — WS 3개 중 **2개가 구독자 0**이고, 유일하게 쓰이는 `/api/v1/ws` 는
   `useWebSocket.ts:58` 이 **`?token=` 을 안 붙여 loopback 이 아니면 close 4401** 이다.
   15초 폴링 폴백이 **그 고장을 가리고 있다.**
2. **요구 주기가 1초 미만이 아니다.** 아래 표의 최단이 3초다. 폴링으로 충분하다.
3. **조작 직후 갱신은 응답이 해결한다.** 쓰기 6개가 전부 `WriteResult` 를 주므로
   화면은 **응답을 받고 해당 조회를 한 번 다시 부르면 된다.** 푸시가 필요 없다.
4. **푸시가 필요해지는 것은 P5 다** — 작업자 반송 *지시*(누가 언제 가져가라)가 생기면 그때가 처음이다.
   그 화면은 지금 없다(§2 S7).

## 6-2. 화면별 갱신 방식

| 화면 | 엔드포인트 | 주기 | 근거 |
| --- | --- | --- | --- |
| S1 흐름 | R1 · R2 | **5초** | 설비 진행률은 초 단위로 안 바뀐다. `progress_pct` 는 `std_cycle_s` 기준 파생 |
| S2 파이프라인 | R3 | **15초** | 재공이 공정을 옮기는 빈도 |
| S3 서브 탭 | R4 | **진입 시 1회** | 토폴로지는 `topo_sync` 때만 바뀐다 |
| S4 MONITOR | R1 · R5 | **3초** | 🥇 가장 짧다 — 투입 가능 여부가 남의 조작으로 바뀐다 |
| S5 BATCH_SPLIT | R6~R9 | **조작 직후 + 10초** | 한 사람이 붙잡고 하는 화면이라 경쟁이 적다 |
| S6 PART_JUDGE | R9 · R10 | **조작 직후 + 10초** | 〃 |

## 6-3. 폴링 비용을 줄이는 법 — 새 프로토콜 없이

- 조회 응답에 **`ETag`**(뷰 결과의 해시) 를 달고 `If-None-Match` 면 **304**.
  `product_state.updated_at` 의 `max()` 하나로 만들 수 있다.
- 🚨 **폴백이 에러를 삼키지 않게 한다**(원칙 3) — 조회 실패는 화면에 **표시**한다.
  지금 `useDashboard` 는 WS 가 닫혀도 아무 표시가 없다. v2 화면은 **마지막 갱신 시각과 실패 배지**를 띄운다.

## 6-4. 🔴 만들게 되면 (미래)

`WS /api/v2/ws?token=<JWT>` — **쿼리 토큰 필수**(미들웨어 `jwt_middleware.py:53-64` 가 이미 지원한다).
실패 시 `close 4401` 이고, **클라이언트는 그것을 화면에 표시한 뒤** 폴링으로 내려간다.
🚨 **지금 프론트처럼 조용히 폴백하지 않는다.**

---

# 7. 인증 — 경로별 보호 · loopback 면제 판단

## 7-1. 경로별

| 경로 | 보호 | 근거 |
| --- | --- | --- |
| `/api/v2/**` 전부 (R1~R10 · W1~W5) | 🔒 **JWT** | `_is_protected_path` 가 **`/api/` 로 시작하면 전부 보호**(`jwt_middleware.py:37-43`). 새 경로도 자동 |
| 공개 예외 | **0개** | v1 의 `/api/v1/auth/login` 하나뿐인 구조를 유지. v2 는 로그인 창구가 없다 |
| 헬스체크 | **없음** | 🚨 v1 의 `/health` 는 인증 없이 열려 있고 **SPA 폴백에 가려 HTML 을 반환**한다(조사 §2-2). v2 는 그 경로를 따라가지 않는다 — §1-4 참조 |

## 7-2. 🔴 loopback 면제 — 판단과 근거

**사실** — `jwt_middleware.py:105-110` 이 client host ∈ {127.0.0.1, ::1, localhost} 면 **토큰 없이 통과**시킨다.
v2 가 같은 미들웨어를 타므로 **면제를 그대로 물려받는다.**

**필요한가?** 갈린다.

| | 필요 | 근거 |
| --- | --- | --- |
| 읽기 R1~R11 | 🔴 **아니다** | 호출자는 브라우저뿐이고 브라우저는 토큰이 있다 |
| 쓰기 W1~W6 | 🔴 **아니다** | 〃 |
| v1 의 4경로 | 🟢 **필요** | `sequence_service/app/cell/printer_interface.py:41,70,79,86` 이 토큰 없이 부른다(5/29 회귀 fix 의 대상) |

⇒ ⭐ **v2 는 면제가 필요 없다.** 그런데 미들웨어는 경로를 가리지 않으므로 **끄려면 미들웨어를 고쳐야** 하고,
그건 v1 4경로에 영향을 준다.

**권고** — `LOOPBACK_EXEMPT_PREFIXES = ("/api/v1/",)` 한 줄로 **접두 제한**을 건다.
v1 동작은 그대로이고 v2 만 빠진다. 🟡 **"기존을 건드리지 않는다"를 1줄 어기는 것**이라 결정으로 올린다 → §9-2.

**판정 못 하는 것** 🔴 — 조사 §3-2 *"터널 경유 요청이 loopback 으로 보이나"* 가 **미확인**이다.
- **참이면** 면제가 외부 전부에 적용된다 ⇒ 위 한 줄이 **v2 를 지키는 유일한 장치**가 된다
- **거짓이면** 한 줄은 정리 차원이다

🚨 **어느 쪽이든 v2 쓰기가 외부에 열리는 위험은 §3-2 가 닫힐 때까지 남는다.**
⇒ **완화** = `actor` 필수(§3-2 쓰기 골자) + 모든 쓰기를 `command_log`/`product_event` 에 남긴다.
**막지는 못해도 누가 무엇을 했는지는 남는다.**

📮 **확인 방법**(조사 §3-2 그대로) — 공장 PC 에서 `cloudflared` ingress 의 `service:` 주소를 보고,
외부 망에서 토큰 없이 `GET /api/v2/lines/{line_id}/nodes` 가 **401 인지** 확인한다.

## 7-3. 🟡 곁가지 — `/docs` 가 v2 스키마도 공개한다

조사 §3-1 — `/docs` `/openapi.json` 은 `/api/` 로 시작하지 않아 **인증 없이 열린다.**
v2 를 추가하면 **신규 쓰기 엔드포인트의 스키마 전문이 그대로 공개**된다.
🔴 **이번 범위 밖**(기존 설정)이지만 **v2 가 그 노출 면적을 늘린다는 사실은 적어둔다.**

---

# 8. 수락 기준 자가 점검

| # | 확인 | 결과 | 근거 |
| --- | --- | --- | --- |
| **A1** | 엔드포인트 ↔ 화면 대조 | 🟢 **빈 칸 0** | §3 의 "호출 화면" 열 — R1~R11 · W1~W6 **17개 전부** S1~S6·S8 중 하나가 부른다. 🥇 **초안의 R11(`/health`) 은 이 검증에 걸려 삭제**했다. 화면이 없어 만들지 않은 것 **6종**을 §2 S7 에 명시 |
| **A2** | `response_model` | 🟢 **100% (17/17)** | §3-1 · §3-2 표. 🚨 v1 은 31/80 이다 |
| **A3** | 쓰기 경로 | 🟢 **`product_state` 직접 쓰기 0** | §4 표 — 전부 `Split`·`Moved`·`State` 또는 `judgement`/`command_log`. `Spawn` 은 화면이 없어 미설계 |
| **A4** | 뷰 활용 | 🟢 | §3-1 "사용 뷰" 열에 전부 기재. 🆕 신규 뷰 **5개를 §5 로 분리** |
| **A5** | 서브 메뉴 | 🟢 | R4 가 **`v_control_menu`** 만 읽는다. 노드를 늘리면 `node_count` 와 `node_ids` 가 자동으로 는다. **개수·라벨 하드코딩 0** |
| **A6** | 경로 충돌 | 🟢 | §1-3 실측 — `/api/v2` 충돌 0, SPA 폴백이 `api/` 제외. **include 를 폴백보다 먼저** 조건 명시 |
| **A7** | 인증 | 🟢 판단함 | §7 — 전 경로 🔒, 공개 0. **loopback 면제는 "v2 에 불필요" 로 판정**하고 접두 제한 1줄을 권고. 🔴 §3-2 미확인은 위험으로 명시 |
| **A8** | WS | 🟢 **만들지 않는다** | §6-1 사유 4가지. 만들 때의 토큰 경로는 §6-4 에 미리 적음 |

🚨 **A1 에 붙이는 단서** — 위 "빈 칸 0" 은 **확정 와이어프레임 기준**이다.
§9 의 유보 5건이 풀리면 엔드포인트가 **늘어난다**(중지 · 가동 시간 · 측정 스펙 · 박스 마감 · 인터록).
**그때도 화면부터 확인한다.**

---

# 9. 🔴 결정이 필요한 것

| # | 항목 | 지금 상태 | 안 정하면 | 누가 |
| --- | --- | --- | --- | --- |
| **9-1** | **PostgreSQL 위치** | 🔴 미결(coexistence §3-4) | §1 권고 A 의 전제가 흔들린다. 공장 PC 밖이면 **제어 프로세스가 DB 지연을 탄다** | 태민님 |
| **9-1b** | **v1 SQLite → PostgreSQL 이식** | 🔴 미결 → §1-6 ② | web-api 가 **DBMS 3개**를 계속 본다. 백업·모니터링이 3벌 | P5. 카카오·6000 인스턴스 처리가 본 안건 |
| **9-2** | loopback 면제 접두 제한 1줄 | 🔴 미결 | v2 쓰기가 외부에 열릴 수 있다(§3-2 참일 때) | 태민님 |
| **9-3** | **설비 "중지"** | ✅ **닫힘 (2026-09-16 반영)** — `State.status` 에 `HOLD` 추가. 🥇 이유는 화면 버튼이 아니라 **M2c 설계(`모듈 상세 설계.md:346`)가 이미 요구하던 값이 계약에 없었던 것**. `_state()` 가 `ready_at`·`eta` 를 지운다(멈춘 것은 꺼낼 수 없다) | – | – |
| **9-4** | **가동 시간 입력** | ✅ **닫힘 (2026-09-16 반영)** — `State.duration_s` 추가. 기존 `print_command.washing_time`(초·작업별·실제 동작)과 같은 성격. 없으면 `std_cycle_s` | – | – |
| **9-5** | **측정 스펙 자리** | ✅ **닫힘 (2026-09-16 반영)** — **`node.attrs jsonb`** 신설. 화면은 `attrs.measure` 가 있으면 입력란을 띄운다(`ui_kind` 분기 아님). 공차는 `part.attrs` 유지 | – | – |
| **9-6** | **박스 마감 상태** | ✅ **닫힘 (2026-09-16 반영)** — **`group_close` 테이블** 신설. 🔴 `group_id` 문자열 규약은 **기각**(조인 키라 이력이 끊긴다) | – | – |
| **9-6b** | **외부 식별자 자리** | ✅ **닫힘 (2026-09-16 반영)** — **`node.external_ref jsonb`** + GIN 인덱스. 매핑 테이블은 선례 0건이라 기각 | – | – |
| ~~9-6c~~ | ~~로봇 동작 명령 카탈로그의 자리~~ | ✅ **2026-09-21 닫힘** — `transporter.attrs jsonb` 신설 + `topology.yaml` `transporters[].attrs.commands` + `topo_sync` 적재. 흩어져 있던 값(`config.py` 레지스터 · `rodi_pick_sequence.js` 4비트 조합)을 **한 자리로 모았다** | – | 적재 확인 ARM-A 4 / ARM-B 7 / OP-CURE 0 |
| **9-7** | **인터록 데이터원** | 🔴 M4 문서 — *"인터록은 DB 밖, 어댑터 라이브 상태"*. **어댑터가 아직 없다** | 화면의 체크박스가 **영원히 목업**이다 | 어댑터 착수 시점 |
| **9-8** | **화면이 보는 `line_id`** | 🔴 `topology.yaml` 에 `RESIN-1-ASIS`·`RESIN-1` **둘 다 active**. 와이어프레임에서 **라인 선택을 제거**했다 | 뷰가 행을 곱하거나(§5 경고) 화면이 엉뚱한 라인을 본다 | 화면 고정 vs 선택 복원 |
| **9-9** | 리모트 I/O = MQTT vs Modbus | 🔴 미결(M4 문서) | **`State` 를 누가 발행하나**가 안 정해진다. W3(수동 입력)이 임시로 그 자리를 메우는 중 | P4 이전 |
| **9-10** | 부품 ID 표기 | 🔴 미결 — 와이어프레임 `PT-2026-0412-01`(주문 기반) vs `display_id`(공정 기반) | R8·R10 의 `display_id` 가 작업자가 보는 번호와 다를 수 있다 | 작업자 확인 |

## 9-11. ⚠️ 와이어프레임이 아직 확정 아닌 것

명세를 **유보한 것이 아니라**, 확정되면 **요청/응답 필드가 바뀔 수 있는** 자리다.

| 항목 | 지금 명세 | 흔들리면 |
| --- | --- | --- |
| **부품 분리 화면의 혼재 반영** | R8 이 파트별 행을 내려보내고 W1 이 파트별 `outputs` 를 받는다 | 🟢 **혼재가 기본**이라는 전제는 `unit_content` 와 일치. 바뀔 여지 작음 |
| **묶음 누적 기본 동작** | W1 의 `group_id` 가 `null` 이면 **새 묶음**, 값이 있으면 **이어 담기**. 정원 초과 시 새 묶음은 **화면이 판단** | 🔴 *"기본이 이어 담기냐 새로 따기냐"* 가 확정 안 됨. **서버 기본값을 정하면 화면이 못 바꾼다** ⇒ 지금은 **명시 전달**로 둔다 |
| 박스 정원 12 | `node.capacity`(또는 `count_by_group` 랙의 정원)에서 온다 | 🟢 하드코딩 아님 |

---

# 부록 — 이 명세가 스스로 지킨 규칙

조사가 짚은 5가지에 대한 대응을 한 줄씩.

| 원칙 | 이 명세에서 |
| --- | --- |
| 1. 화면이 안 부르면 만들지 않는다 | §2 S7 — **만들지 않은 것 5종을 사유와 함께 명시**. `Spawn`·반송 지시·주문 보드 포함 |
| 2. `response_model` 전부 | §3 — **17/17**. 모델 골자까지 적음 |
| 3. WS 토큰 | §6 — **WS 를 안 만든다**. 만들면 `?token=` 필수(§6-4) + **폴백이 에러를 삼키지 않게**(§6-3) |
| 4. 경로 등록 순서 | §1-3 — 등록표 **덤프 실측** + include 를 SPA 폴백보다 앞에 |
| 5. loopback 면제 | §7-2 — **"v2 에 불필요" 로 판정**, 접두 제한 1줄 권고, §3-2 미확인은 🔴 로 남김 |
