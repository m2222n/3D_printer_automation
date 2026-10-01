작성 2026-09-16 (화) KST · 대상 = `20260916_api_design.md` §9 미결 **11건**
🔒 **코드 변경 0건.**

📌 읽은 것 = 설계서 §9 · `20260909_api_survey.md` · `20260914_coexistence_plan.md` ·
`schema.sql` · `contract.py` · `state_engine.py` · `sequence_service/` 전수 · `web-api/` 전수 ·
`docs/juhee/03_MES_v2_설계/모듈 상세 설계.md`

---

# 0. 한 줄 결론

> **전제가 맞았다.** 신규가 *"자리가 없다"* 고 적은 5건 중 **4건은 기존이 이미 풀어놨고**,
> 그 방식을 보고 나니 판정이 나왔다. **11건 중 5건이 닫히고 2건이 좁혀졌다.**

🥇 **덤으로 찾은 것** — 화면과 무관하게 **이미 존재하던 계약 불일치 1건**:
`모듈 상세 설계.md:346` 이 프린터 어댑터에게 **`HOLD` 를 발행하라**고 적었는데
`contract.py` 의 `State.status` 에 **`HOLD` 가 없다.** §9-3 은 "화면 버튼" 문제가 아니라 이것이었다.

---

# 1. A1~A10 — 실측과 판정

## A1. 설비 "중지" (§9-3) → 🟢 **판정: `State.status` 에 `HOLD` 를 더한다**

### 실측

| 질문 | 답 | 근거 |
| --- | --- | --- |
| 작업 단위인가 셀 전체인가 | 🔴 **셀 전체** | `cell_state` **단일 행 `id=1`** 의 `running`·`paused`. `automation_db.py:300-350` |
| 받는 action | `start` `stop` `pause` `resume` 4개 | `local/routes.py:1251-1258` |
| 중지 뒤 재개하면 | 🚨 **STOP 은 재개가 아니라 취소다** — `cancel_inflight_commands(reason='CANCELED by STOP(DB sync)')` | `runtime.py:170` → `repository.py:445` |
| PAUSE 는 | **새 작업만 안 집는다. 진행 중인 것은 끝까지 간다**(drain) | `sequences/robot.py:423` `if self.ctx.paused or self._current_task is not None: return` |
| 작업 상태에 PAUSED 가 있나 | 🔴 **없다** — `CmdStatus` = UPLOADING·QUEUED·CLAIMED·PRINTING·PRINT_FINISHED·POST_PROCESSING·DONE·**CANCELED**·ERROR | `cell/enums.py:6-16` |

### 🥇 그런데 진짜 문제는 화면이 아니었다

```
docs/juhee/03_MES_v2_설계/모듈 상세 설계.md:346   M2c 프린터 어댑터 상태 매핑
  | `PAUSED` / `PAUSING` / `ABORTING` | `HOLD` |

contract.py:71                          State.status
  status: Literal["RUN", "DONE", "ERROR"]        ← HOLD 가 없다
```

⇒ **M2c 를 설계대로 구현하면 발행할 수 없는 값을 발행하게 된다.**
`schema.sql:197` 과 `스키마.md:169` 는 `HOLD` 를 허용하고, `product_state` 에 자리도 있다.
**빠진 곳은 계약 한 곳뿐이다.**

### 판정

1. **`State.status` 에 `HOLD` 추가** — Literal 1줄. 화면과 무관하게 **M2c 를 위해 필요**하다.
2. 화면의 [중지] 는 그 위에 **얹히기만 한다** — `State(HOLD, source='MANUAL')`. 별도 자리 불필요.
3. 🚨 **기존 `cell_state` 와 같은 것으로 보지 말 것** — 기존은 **셀 전체 운전 모드**, 신규 `HOLD` 는
   **개체 하나의 상태**다. 둘은 층이 다르고 합치면 안 된다.
4. 🔴 **물리적으로 설비를 멈추는 것은 이 API 범위 밖**이다(어댑터). 지금 화면은 **DB 기록만**.

⚠️ 계약 변경이므로 **C4** 로 올린다(M2·M3a·시뮬 동시 수정 범위는 그 표에).

---

## A2. 가동 시간 입력 (§9-4) → 🟢 **판정: 기존 방식이 명확하다. `State` 에 `duration_s` 를 더한다**

### 실측

| 질문 | 답 | 근거 |
| --- | --- | --- |
| 어디 있나 | **`print_command.washing_time` · `curing_time`** | `sequence_service/app/db/models.py:21-22` |
| 단위 | 🥇 **초** | `ctx.py:17` 주석 *"stage durations used by washing/curing sequences (seconds)"* |
| 기본값 | 코드 `6` / `120`, 프론트 폼 **`360` / `120`** | `ctx.py:17-18` · `AutomationPage.tsx:104-105` |
| 누가 채우나 | 🥇 **작업자가 자동화 탭에서 CMD 등록할 때 입력** (검증 `ge=1,le=86400`/`le=7200`) | `AutomationPage.tsx:199-213` → `routes.py:1144-1145,1209` |
| 실제로 그대로 도나 | 🟢 **돈다** — 기록만이 아니다 | `washing.py:57` `_end_ts = time.time() + int(job.washing_time)` · `curing.py:132` `cure_seconds = job.curing_time or CURE_SIM_SECONDS` |
| `std_cycle_s` 와 무엇이 다른가 | **노드 속성(표준) vs 작업별 지시값** — 배치마다 다르게 준다 | 위 두 곳이 `job.*` 을 읽는다 |

🐛 **곁가지** — `wash_minutes`(= `ceil(washing_time/60)`, `automation_db.py:202`)는
**INSERT·SELECT 에만 나오고 읽는 코드가 0건**이다(`grep -rn wash_minutes --include=*.py .` → `automation_db.py` 3줄뿐). **같은 값을 초·분 두 벌로 저장**하고 한쪽은 안 쓴다.

### 판정

**가동 시간은 "노드 속성" 이 아니라 "작업에 실리는 지시값" 이다** — 기존이 그렇게 풀었고 실제로 그 값대로 돈다.
⇒ 신규에서도 **개체 쪽**에 실어야 하고, 개체 상태를 바꾸는 유일한 경로가 `State` 다.
⇒ **`State` 에 `duration_s: Optional[int]` 추가.** 엔진이 `product_state.eta = now + duration_s` 로 쓴다.

🚨 **단 입력 *시점*이 다르다** — 기존은 **작업 등록 시**(CMD 생성), 와이어프레임은 **[시작] 버튼 누를 때**다.
어느 쪽이든 값의 성격은 같지만, 등록 시점을 택하면 **작업 지시 화면(설계 전)** 이 선행조건이 된다.
⇒ 📌 **와이어프레임대로 [시작] 시점을 권고**한다 — 화면이 이미 있고, 기존 값의 성격도 보존된다.

⚠️ 계약 변경 ⇒ **C4**.

---

## A3. 측정 스펙과 공차 (§9-5) → 🟢 **판정: 공차는 `part.attrs`, "측정하는 노드" 는 `node.attrs` 신설**

### 실측

**① 공차를 다루는 운영 코드가 없다.**
```bash
grep -rniE "\btol\b|tolerance|공차" --include=*.py --include=*.ts --include=*.yaml --include=*.sql .
```
히트 전부가 **빈피킹의 ICP·크기필터 허용오차**(`SizeFilter(tolerance=0.5)` · `RMSE_REJECT = 0.003`)이고
**치수 공차가 아니다.** `schema.sql:249` 의 `{"measured": 12.03, "tol": 0.15}` 는 **주석 예시**다.
`presets` 10컬럼(`id name part_type description printer_serial settings stl_filename print_count created_at updated_at`)에도 없다.

**② 판정 임계값의 선례 = 코드 상수 + 호출 시 주입.**
```
bin_picking/src/pipeline/input_gate.py:141   VALID_RATIO_TRAIN_MIN = 2.0
                                      :142   VALID_RATIO_TRAIN_MAX = 25.0
                                      :145   VALID_RATIO_WARN      = 10.0
                                      :163   def …(ratio_min=VALID_RATIO_TRAIN_MIN, …)   ← 인자로 덮어쓸 수 있다
```
⇒ **DB 도 설정파일도 아니다.** 기존은 임계값을 DB 에 둔 적이 없다.

### 판정

- **공차 = 파트 속성이 맞다** → `part.attrs` 로 충분하다. 도면에서 오는 값이고 설비가 바뀌어도 안 바뀐다.
- **"이 노드가 측정을 한다" 는 노드 속성이다** → 🚨 `ui_kind` 로 분기하면 **공정 타입 분기 금지 위반**이다.
  ⇒ **`node.attrs jsonb` 1컬럼 추가**를 권고한다. `topology.yaml` 에
  `attrs: {measure: {key: height_mm, label: 높이, unit: mm}}` 로 적고 `topo_sync` 가 넣는다.
  **화면은 `attrs.measure` 가 있으면 입력란을 띄운다** — 공정 타입을 모른 채로 동작한다.
- ⭐ **M1 원칙과 정합** — *"토폴로지는 데이터다 — 설비 개수/구성이 코드에 없다"*.

🔴 **선행 작업 2곳** — `topology.yaml` 과 `topo_sync.py` 에 `attrs`·`measure` grep **0건**이다.
스키마 1컬럼 + YAML 스키마 + 동기화 코드 **셋 다** 손대야 한다.

---

## A4. 인터록의 데이터원 (§9-7) → 🔴 **판정: 지금 조회할 수 있는 인터록은 없다. 목업이 맞다**

### 실측 — "설비가 준비됐나" 를 아는 코드가 있나

| 있는 것 | 실체 | DB 에 남나 | 갱신 |
| --- | --- | --- | --- |
| `GET /automation/manual/robot-status` | 🟡 **TCP 포트 probe** — `probe_tcp(host, port, timeout)` | 🔴 **안 남는다** | 호출할 때마다 소켓 연결 시도 |
| `GET /automation/manual/vision-status` | 〃 | 🔴 | 〃 |
| `vision_cameras.is_online` | MQTT 수신 시 `1`, **타임아웃 스캔으로 `0`** | 🟢 **남는다** | `camera_manager.py:83-92,139` |
| `GET /automation/manual/io/state` | 🥇 **아진 IO 보드 비트 + `IO.csv` 라벨** — 인터록에 가장 가까운 형태 | 🔴 안 남는다 | 호출 시 읽음 |

🚨 **IO 경로는 지금 쓸 수 없다** — `AJIN_SIMULATION: bool = True`(`web-api/app/core/config.py:167`) 가 기본이고,
`IO.csv` 는 `sequence_service/app/io/IO.csv` 인데 **스키마 조사에서 "우리 공장 것이 아니다"(컨베이어·리프트 물류라인 청사진)로 판명**됐다.

### 판정

와이어프레임의 인터록 4항목(**집진 가동 중 · 작업자 로그인 · 스캐너 원점 · 캘리브 24h 이내**)에
대응하는 코드는 **0건**이다. `robot-status` 는 *"TCP 가 열렸나"* 이지 *"설비가 준비됐나"* 가 아니다.

⇒ **인터록 조회 엔드포인트를 만들지 않는다**(설계서 §2 S7 유지).
⇒ 🥇 **가장 가까운 미래 경로는 리모트 I/O(PET-2255U) DI 채널**이고, 그것은 **B2 가 닫아야 한다.**
   B2 의 답이 *"완료 접점 하나"* 면 인터록은 계속 없고, *"RUN/DONE/ERROR + 집진 접점"* 이면 그때 생긴다.

---

## A5. 박스·묶음 마감 (§9-6) → 🟢 **판정: `group_id` 문자열 규약은 쓰지 않는다**

### 실측

기존에 "묶음 / 박스 / 트레이" 개념 **0건**.
```bash
grep -rniE "group_id|join_group|묶음|박스|tray" web-api/app sequence_service/app bin_picking/src
# 히트 전부 "바운딩 박스"(무관)
```

🥇 **그러나 선례는 있다 — 상태를 jsonb 자유 키에 담는다.**
`print_command.allocated_data` 에 실제로 쓰이는 키 **21개**:
```
abort_reason cure_id error fw_started_cure last_logged_printer_status local_print_job_id
local_print_status parking_printer_id plate_in_printer plate_state printer_id printer_serial
printer_server_simul printer_status print_settings scene_id seen_printing simul_mode
uploaded_filename wash_id
```
⇒ **기존은 "컬럼을 늘리지 않고 jsonb 에 넣는다".** `plate_state='CURING_WITH_PLATE'` 가 그 예다.

### 판정

🔴 **`group_id` 를 `BOX-0041-CLOSED` 같은 문자열로 바꾸는 안은 권하지 않는다.** 이유 둘.
1. `group_id` 는 **조인 키**다 — `product_state_group_idx`(`schema.sql:204`)와 `Moved.join_group` 이
   같은 값을 참조한다. 값이 바뀌면 **마감 전후의 이력이 끊긴다.**
2. 기존 선례(jsonb)와도 다르다 — 기존은 **식별자를 바꾸지 않고 옆에 상태를 적는다**.

⇒ **권고 = 작은 테이블 하나** `group_close(group_id text PK, node_id text, closed_at timestamptz, actor text)`.
`v_group_at_node` 가 LEFT JOIN 해서 `closed` 를 내려보낸다. 컬럼 추가 0, 기존 인덱스 영향 0.
⚠️ **정원이 차서 자동 마감되는 경우는 이 테이블이 필요 없다** — 수량으로 알 수 있다.
**수동 마감(정원 미달인데 닫는다)에만** 행이 생긴다.

---

## A6. 외부 식별자 매핑 → 🟢 **판정: `node.external_ref jsonb`. 매핑 테이블은 선례가 없다**

### 실측 — "1호기 = Form4-CapableGecko" 를 어디가 아나

| 설비 | 어디에 | 형태 |
| --- | --- | --- |
| **프린터** ① | `sequence_service/app/core/config.py:76-81` **`PRINTER_SERIAL_MAP`** | 🚨 **코드 상수 dict** — 실 시리얼이 코드에 박혀 있다 |
| **프린터** ② | `web-api/app/core/config.py:64` **`PRINTER_SERIALS`** | **env 리스트**(`.env.example:38`), 기본값은 자리표시자 |
| 세척기·경화기 | `wash_id` · `cure_id` **정수 1,2** | 매핑 없음 — 설비가 곧 번호 |
| 카메라 | `web-api/app/vision/camera_manager.py:28-33` **`DEFAULT_CAMERAS`** | **코드 상수 dict** (`wash_1 → (wash, 1)`) |
| 실행 중 배정 결과 | `print_command.allocated_data` | jsonb 에 `printer_serial`·`wash_id`·`cure_id` 기록 |

🚨 **같은 사실이 두 곳에 다른 형태로 있다** — 프린터를 교체하면 **`config.py` 코드와 `.env` 를 둘 다** 고쳐야 한다.
**DB 매핑 테이블은 한 번도 쓴 적이 없다.**

### 판정

**`node.external_ref jsonb` 컬럼** — coexistence §1-4② 안 그대로. 매핑 테이블(`node_external_id`)은
- 선례가 **0건**이고
- 조회마다 조인이 하나 늘며
- 지금 문제(**두 곳에 흩어짐**)를 해결하지 못한다(세 곳이 된다)

⇒ **`topology.yaml` 에 적고 `topo_sync` 가 `node.external_ref` 로 넣는다.**
⭐ **부수 이득** — 흩어진 시리얼을 **토폴로지 한 곳**으로 모으는 길이 열린다(기존 두 곳을 지금 고치라는 뜻은 아니다).

---

## A7. 세 인스턴스가 각자 SQLite 를 갖는 것 → 🟡 **사실 확인 완료 · 의도는 🔴 기록 없음**

### 실측

| 확인 | 결과 |
| --- | --- |
| `presets.db` 가 git 에 있나 | 🔴 **없다** — `.gitignore:219` `*.db` |
| 배포가 DB 를 복사하나 | 🔴 **안 한다** — `scripts/deploy_servers.sh`·`deploy.bat` 에 `.db`·`sqlite` grep **0건** |
| 각 인스턴스 용도가 적혀 있나 | 🟡 역할만 — 공장 PC=실제 제어 · 카카오 VM=모니터링/SaaS · 6000=개발+모니터링 (CLAUDE.md 운영 인프라) |
| "격리가 의도" 라는 기술 | 🔴 **0건** |

⇒ **의도된 격리가 아니라 "각자 `create_all` 로 스스로 만든다" 는 기본 동작의 결과다.**

### 이미 사고가 있었다

> CLAUDE.md — *"`LOCAL_DATABASE_URL` 기본값이 상대 경로라 `web-api/` 에서 pytest 를 돌리면
> **6000 운영 DB 파일을 그대로 쓴다**. 검증 중 테스트 행 24건이 실제로 운영 DB 에 들어갔다."*

### 판정

- **지금 실해는 작다** — 프린터 제어가 공장 PC 에서만 되므로 프리셋·작업이 다른 서버에서 의미가 없다.
- 🚨 **그러나 사용자는 셋 다 같은 로그인·같은 UI 를 본다** — 어느 서버에 접속했느냐에 따라
  프리셋·메모·알림이 **다르게 보인다**. 이것이 의도라는 근거는 없다.
- ⇒ **C2 에 미치는 영향** — 격리가 의도가 아니므로 v1→PG 때 **PG 를 3벌 두는 것은 같은 문제를 옮기는 것**이다.
  한 벌로 합치는 것이 맞고, 그러면 **카카오·6000 이 공장 PC 의 PG 를 네트워크로 봐야 한다** — 그게 C2 의 진짜 난점이다.

---

## A8. alembic 과 뷰·함수·트리거 → 🟢 **판정: 테이블만 alembic, 뷰·함수는 `schema.sql` 이 원본**

### 실측 — 뷰 의존 그래프

```
v_unit_summary      ← v_unit_content
v_node_status       ← v_node_order, v_product_display, v_unit_summary
v_rack_load         ← v_rack_slot, v_unit_summary
v_transporter_load  ← v_retrievable
v_part_progress     ← v_node_order, v_product_display
v_output            ← v_unit_content
v_waiting_for       ← v_retrievable
v_control_menu      ← v_node_status
```
**의존 있는 뷰 8 / 없는 뷰 11.** 최장 사슬 = `v_unit_content → v_unit_summary → v_node_status → v_control_menu` **3단**.

⚠️ PostgreSQL 규칙 — `CREATE OR REPLACE VIEW` 는 **뒤에 컬럼 추가만** 된다.
이름·순서·타입을 바꾸면 **`DROP VIEW … CASCADE` 후 의존 뷰를 전부 재생성**해야 한다.
⇒ `v_unit_content` 의 컬럼 하나를 고치면 **뷰 4개가 같이 떨어진다.**

### 판정

| 대상 | 관리 | 이유 |
| --- | --- | --- |
| **테이블 · 인덱스 · 제약** | **alembic 리비전** | 데이터가 있어 되돌릴 수 없다. 버전 관리가 필요한 자리 |
| **뷰 19 · 함수 2 · 트리거 1** | 🥇 **`schema.sql` 이 원본. 매 배포에 전량 재적용** | 데이터가 없어 **DROP+CREATE 가 안전**하고, 의존 순서는 **파일 순서가 보장**한다 |

⇒ **두 벌이 안 생긴다** — alembic 은 테이블만 알고, 뷰는 파일 하나가 원본이다.
초기 마이그레이션도 `op.execute(schema.sql 전문)` 이 아니라 **테이블 부분만** 담는다.
📌 이 분리를 안 하면 *"`schema.sql` 과 alembic 버전 두 벌"* 이 되고, **오늘까지 문서-코드 불일치 4건**과 같은 형태가 된다.

---

## A9. SQLAlchemy Core 와 `StateEngine` 의 경계 → 🔴 **판정 불가 — 검증 환경이 없다**

### 실측

| | v1 | `StateEngine` |
| --- | --- | --- |
| 라이브러리 | **SQLAlchemy ORM** `create_engine` + `sessionmaker` + `Depends` (`local/database.py:19-26`) | 🚨 **psycopg3 직접** |
| 근거 | — | `state_engine.py:27` `with self.conn.transaction():` · **`%s` 자리표시자 83회** · `conn.execute(sql, (…,)).fetchone()` |

🔴 **`psycopg` 도 `alembic` 도 설치돼 있지 않고 PostgreSQL 서버도 없다**(psql 클라이언트만).
```
psycopg 없음 · psycopg2 없음 · sqlalchemy 2.0.52 설치됨 · alembic 없음
```
⇒ **실제로 돌려볼 수 없어 판정하지 않는다.**

### 🚨 설계서 §1-6 의 문장을 정정해야 한다

*"v2 도 SQLAlchemy Core. `psycopg` 를 직접 쓰지 않는다"* 는 **읽기에만 참**이다.
쓰기는 `StateEngine` 이 psycopg3 API 를 쓰므로 그대로 둘 수밖에 없고,
**엔진을 SQLAlchemy 로 고치는 것은 유일한 검증 지점을 건드리는 일**이다(`%s` 83곳).

### 그릴 수 있는 한 줄 (🔴 **미검증**)

```
SQLAlchemy Engine(postgresql+psycopg://) ─┬─ 읽기  conn.execute(text(...))        ← Core
                                          └─ 쓰기  conn.connection.driver_connection → StateEngine(psycopg)
                                                   같은 물리 커넥션 ⇒ W1·W4 가 한 트랜잭션
```
**검증해야 할 것** — `StateEngine.handle` 안의 `conn.transaction()` 이
SQLAlchemy 가 이미 연 트랜잭션 **안에서 중첩될 때** 세이브포인트로 동작하는가.
📮 **절차** = PG 를 띄우고 `schema.sql` 적용 → `engine.begin()` 안에서 `StateEngine(raw).handle(Spawn(...))`
→ 같은 트랜잭션에서 `SELECT` 로 보이는지 · 롤백 시 같이 사라지는지.

⇒ 이것이 안 되면 **읽기/쓰기를 같은 트랜잭션에 못 담고**, W1·W4 의 트랜잭션 경계(설계서 §4-2)를 다시 잡아야 한다.

---

## A10. 화면이 보는 `line_id` (§9-8) → 🟡 **권고는 있으나 사람이 정할 것**

### 실측

| 확인 | 결과 |
| --- | --- |
| `topology.yaml` | `RESIN-1-ASIS`(현행) · `RESIN-1`(재배치 후) **둘 다 `active: true`** |
| 시뮬레이터 기본값 | **`RESIN-1`** (`simulator.py:261` `ap.add_argument("--line", default="RESIN-1")`) |
| 현행 라인으로 도는 재공 | 🔴 **없다 — PostgreSQL 자체가 아직 없다.** `product_state` 는 0행이 아니라 **테이블이 없다** |
| YAML 주석 | *"목표 라인 — 10월 재배치 후. **신규 unit 만 이쪽으로 발급한다**"* |

### 판정

- **화면 고정값 = `RESIN-1`** 을 권고한다. 근거 = 시뮬 기본값 + YAML 주석의 발급 규칙.
- 🚨 **하드코딩 금지 · 설정값으로** — `LINE_ID` 환경변수. 두 라인이 다 active 이므로
  뷰가 행을 곱하지 않도록 **모든 조회에 `line_id` 를 건다**(설계서 §5 경고).
- 🔴 **사람이 정할 것** — 10월 재배치 **전**에 관측을 시작하면 실물은 ASIS 인데 화면은 목표 라인을 본다.
  *"재배치 전까지는 관측을 안 켠다"* 인지 *"ASIS 로 켜뒀다가 바꾼다"* 인지는 일정 판단이다.

---

# 2. B1~B5 — 확인 절차

🔒 **여기서는 판정하지 않는다.** 그대로 따라 할 수 있는 절차와 **판정 기준**만 적는다.

## B1. 🚨 터널 경유 요청이 loopback 으로 보이나 — **제일 급하다**

참이면 **JWT 가 외부에 무력**이고 v2 쓰기가 그대로 열린다.

**누가** 태민님 · **어디서** 공장 PC 관리자 창 + 외부 망(휴대폰 테더링) · **얼마나** 5분

### ① 공장 PC — ingress 주소 확인
```powershell
cloudflared tunnel ingress url http://127.0.0.1:8085
type %USERPROFILE%\.cloudflared\config.yml
```
`service:` 값을 본다.

| 보이는 값 | 뜻 |
| --- | --- |
| `http://127.0.0.1:8085` · `http://localhost:8085` | 🔴 **uvicorn 이 보는 client host 가 loopback** ⇒ 면제가 외부 전부에 걸린다 |
| `http://192.168.x.x:8085` 등 LAN IP | 🟢 면제 안 걸림 (현행 주석의 전제) |

### ② 외부 망 — 토큰 없이 호출 (**이게 최종 판정**)
휴대폰 테더링으로 **회사 망을 벗어난 뒤**:
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://<도메인>/api/v1/dashboard
```

| 결과 | 판정 | 할 일 |
| --- | --- | --- |
| **401** | 🟢 현행 주석이 맞다 | C1 을 "정리 차원" 으로 낮춘다 |
| **200** | 🔴 **JWT 가 외부에 무력** | 즉시 아래 완화 |

### ③ 200 일 때 즉시 할 수 있는 완화 (셋 중 택1, 위가 빠르다)

| 방법 | 내용 | 대가 |
| --- | --- | --- |
| **ingress 주소 변경** | `service:` 를 LAN IP 로 | cloudflared 재시작 1회. **코드 0줄** |
| **접두 제한 1줄** | `jwt_middleware.py` 의 loopback 면제를 `/api/v1/` 로 한정 | v1 4경로는 유지, v2 만 보호 → C1 |
| uvicorn 옵션 | `--proxy-headers --forwarded-allow-ips` | 🚨 신뢰 프록시 설정을 잘못하면 **헤더 위조로 더 나빠진다** |

🚨 **②를 하기 전에는 어느 쪽도 사실로 적지 않는다.**

---

## B2. PET-2255U 채널 배정

**누가** 태민님 → 예승님/설치 담당 · **왜** 무엇에 썼는지 모르면 **`State` 로 무엇을 발행할 수 있는지도 모른다**

**물어볼 것**

| # | 질문 | 왜 |
| --- | --- | --- |
| 1 | 세척기 **1대당 몇 채널**을 무엇에 배정했나 — **완료 접점 하나**인가 **RUN/DONE/ERROR 를 다 받나** | `State` 발행 범위가 갈린다. 완료 하나면 `DONE` 만, 셋이면 `RUN`·`ERROR` 까지 |
| 2 | 🥇 **DO 8채널을 우리가 쓰나** | 쓰면 **관측이 아니라 제어**다. coexistence §3-5 의 경계(`cell/` 소유)가 걸린다 |
| 3 | I/O **Pair-Connection 으로 세척 완료 → 로봇 기동이 이미 결선돼 있나** | 🔴 결선돼 있으면 **P5 `route` 이관의 전제가 흔들린다** — 우리가 끼어들 자리가 없다 |
| 4 | **집진기·안전 접점**이 DI 에 들어와 있나 | 🥇 **A4(인터록) 의 유일한 미래 경로**가 이것이다 |
| 5 | MQTT 로 붙일지 **Modbus TCP 폴링**으로 할지 | 둘 다 기존 어댑터로 된다(모듈 신설 아님). MQTT 면 **M2a `timestamp` 버그가 선행 과제**로 올라온다 |

**판정 기준** — 1의 답이 *"완료 접점 하나"* 면 §9-9 는 **`State(DONE)` 만으로 닫힌다.**
*"RUN/DONE/ERROR"* 면 상태 전이 전체를 어댑터가 발행하므로 **W3(수동 입력)이 임시 조치에서 백업으로 내려간다.**

---

## B3. 카메라 4대의 새 용도

세척기가 리모트 I/O 로 가면 카메라 담당이 빈다(`DEFAULT_CAMERAS` = wash 2 + cure 2).

**물어볼 것** — 경화기로 재배치인가 · 다른 공정인가 · 유휴인가.

**판정 기준**

| 답 | 영향 |
| --- | --- |
| 경화기 집중 | M2a 범위 축소. `timestamp` 버그 우선순위 **유지** |
| 다른 공정(치수검사 보조 등) | M2a 범위 **재정의** 필요 |
| 유휴 | 🥇 **M2a 착수를 미룰 수 있다** — `timestamp` 버그도 같이 내려간다 |

---

## B4. 부품 ID 표기 (§9-10)

**누가 정하나** 🥇 **작업자**(손에 든 물건과 화면을 맞추는 사람). 우리가 정할 일이 아니다.

**설명한 뒤 고르게 할 것**

| 안 | 예 | 알려주는 것 | 못 알려주는 것 |
| --- | --- | --- | --- |
| ① 공정 기반 `display_id` | `P3-W2-S15-C102` | **어디까지 거쳤나** — 이름에 공정 이력이 붙는다 | 어느 주문인지 |
| ② 주문 기반 | `PT-2026-0412-01` | **어느 주문의 몇 번째** | 지금 어느 공정인지 |
| ③ **둘 다 표시** | 큰 글씨 ② / 작은 글씨 ① | 둘 다 | 화면이 좁아진다 |

🟢 **셋 다 파생 가능하다** — `unit.display_id` 와 `unit.order_id` 가 둘 다 있다(`schema.sql:155-167`).
**저장을 바꾸는 결정이 아니라 표시를 정하는 결정**이라고 설명할 것.

**판정 기준** — 작업자가 **라벨을 손으로 적거나 읽는 일이 있으면** 짧은 쪽(②),
**되돌아보며 "어디서 왔나" 를 묻는 일이 많으면** ①. 모르면 ③으로 시작해 한 달 뒤 줄인다.

---

## B5. PostgreSQL 위치 (§9-1)

**누가** 태민님 · **어디서** 공장 PC

**확인할 것**
```powershell
wmic logicaldisk get name,freespace,size      # 디스크 여유
systeminfo | findstr /C:"Total Physical"      # 메모리
```

**물어볼 것**

| # | 질문 | 판정 기준 |
| --- | --- | --- |
| 1 | 공장 PC 에 PG 를 둘 디스크 여유가 있나 | 🚨 `product_state` 비대 우려(M4 문서) — **하루 수백 행 × 부품 단위**. 최소 수 GB |
| 2 | **백업을 누가 언제** 하나 | 지금 MariaDB 백업 절차가 있나부터. 없으면 **PG 도 없을 것이다** |
| 3 | 재기동 순서에 넣을 수 있나 | 이미 **cloudflared · OrinuMain · PreFormServer · MariaDB · file_receiver** 5개가 순서대로 뜬다. **PG 가 web-api 보다 먼저** 떠야 한다 |
| 4 | 정전·재부팅 시 자동 시작 | NSSM/서비스 등록 |

🚨 **함께 전달할 것** — *"공장 PC 밖에 두면 설계서 §1 의 권고 A 가 재검토 대상이 된다.
공장 PC 에서 나가는 DB 커넥션이 인터넷을 건너고, 끊기면 관측이 아니라 **제어 프로세스가 느려진다**."*

---

# 3. C1~C4 — 선택지와 대가

## C1. loopback 면제 접두 제한 (§9-2)

| 안 | 내용 | 얻는 것 | 잃는 것 |
| --- | --- | --- | --- |
| **①** | `jwt_middleware.py` 면제를 **`/api/v1/` 로 한정** | v2 전체가 토큰 필수 | 🟡 *"기존 코드 0건"* 원칙을 **1줄** 어긴다 |
| ② | 그대로 둔다 | 변경 0 | 🔴 B1 이 200 이면 **v2 쓰기가 외부에 열린다** |
| ③ | ingress 주소를 LAN IP 로 | **코드 0줄**로 근본 해결 | cloudflared 설정 변경 · 재시작 1회 |

**v1 4경로에 미치는 영향**(①을 택할 때) — `printer_interface.py:41,70,79,86` 이
`127.0.0.1` 로 `/api/v1/*` 를 부른다 ⇒ **전부 `/api/v1/` 접두라 그대로 통과한다. 영향 0.**
📌 5/29 JWT 회귀 사고의 fix 대상이 정확히 이 4개이므로 **깨지면 바로 드러난다**(CMD 픽업 실패).

**안 하면 남는 위험** — B1 이 401 이면 위험 없음(정리 차원). **200 이면 즉시 조치 대상.**
⇒ 🥇 **B1 을 먼저 하고 C1 을 정한다.** 순서가 반대면 근거 없이 코드를 고치는 것이다.

## C2. v1 SQLite → PostgreSQL 이식 시점 (§9-1b)

| 안 | 내용 | 대가 |
| --- | --- | --- |
| **①** | **지금 안 한다**(P5 로) | DBMS **3개**를 계속 본다 — 백업·모니터링·드라이버가 3벌 |
| ② | 지금 한다 | 🔴 아래 세 가지를 동시에 받는다 |

**②의 비용 — A7 이 밝힌 것**

| 항목 | 내용 |
| --- | --- |
| 기술 | 🟢 **싸다** — v1 SQLite 쪽은 ORM 4모델·36컬럼·**FK 0·뷰 0·트리거 0**(`sqlite_master` 실측, 인덱스 18개뿐), 원시 SQL **0건**. 종속은 **두 줄** — `config.py:117` DSN 기본값 + `local/database.py:21` `connect_args={"check_same_thread": False}` |
| 🥇 **인스턴스** | **이사가 하나가 아니라 셋**이다. 그리고 A7 이 *"격리는 의도가 아니다"* 로 나왔으므로 **PG 3벌은 같은 문제를 옮기는 것** ⇒ 한 벌로 합치면 **카카오·6000 이 공장 PC PG 를 네트워크로 본다** |
| 원칙 | coexistence §1-0 *"기존 DB DDL 변경 0건 · 기존 운영 코드 변경 0건"* 의 **첫 위반** |
| 시점 | 운영 데이터가 있다(알림 282행 등). **10/31 앞에서 몇 달 돌던 것을 건드리는 위험** |

⇒ 📌 **권고 = ①**, 단 *"방향은 v1→PG 가 맞다"* 를 문서에 남긴 채로.

## C3. `schema.sql` vs alembic 원본 (A8)

| 안 | 원본 | 대가 |
| --- | --- | --- |
| ① 전부 alembic | alembic 리비전 | 🔴 뷰 19개가 **파이썬 문자열**이 된다. 의존 3단 순서를 사람이 관리 |
| ② 전부 `schema.sql` | 파일 | 🔴 **테이블 변경 이력이 없다** — 운영 DB 를 어떻게 따라가나 |
| **③ 나눈다** | **테이블=alembic · 뷰·함수·트리거=`schema.sql` 전량 재적용** | 🟡 배포 절차가 2단계 |

**두 벌 유지 비용** — ①②는 `schema.sql` 과 alembic 이 **같은 사실을 두 번 적는다**.
📌 **오늘까지 문서-코드 불일치 4건**이 이미 있다(`contract.py` 독스트링 `container_id` vs 코드 `group_id` ·
`jwt_middleware.py` 독스트링의 `/api/v1/auth/me` · M2c 의 `HOLD` · `wash_minutes` 미사용).
**같은 사실을 두 곳에 적으면 어긋난다** 는 것이 이 저장소에서 이미 확인된 사실이다.

⇒ 📌 **권고 = ③.**

## C4. 중지·가동시간을 계약에 넣을지 (A1·A2)

**변경 내용** (둘 다 `contract.py` 한 파일)
```python
State.status: Literal["RUN", "DONE", "ERROR"]            →  + "HOLD"
State.duration_s: Optional[int] = None                    ← 신설
```

**범위를 숫자로**

| 대상 | 변경 | 근거 |
| --- | --- | --- |
| `contract.py` | **2줄** | 위 |
| `state_engine.py` `_state()` | **~5줄** — `HOLD` 를 `product_state.status` 에 그대로, `duration_s` 로 `eta` 계산 | `state_engine.py:135` |
| `simulator.py` | 0~3줄 (HOLD 를 안 쓰면 0) | 시뮬은 `RUN/DONE` 만 쓴다 |
| M2a·M2b 어댑터 | **0줄** — 아직 없다 | 미착수 |
| M2c 프린터 어댑터 | **0줄, 오히려 해소** | 🥇 설계 문서가 이미 `HOLD` 를 요구한다(`모듈 상세 설계.md:346`) |
| 신규 API W3 | 0줄 (요청 모델이 Literal 을 그대로 씀) | 설계서 §3-2 |

⇒ ⭐ **"계약 변경 = M2·M3a·시뮬 동시 수정" 이라는 우려는 실측상 과했다.**
어댑터가 **아직 없어서** 지금이 가장 싼 시점이다. 나중에 M2a·M2b 가 생기면 그때는 비싸진다.

🔴 **단 `duration_s` 는 "시작 시점 입력" 이라는 화면 전제 위에 있다**(A2). 그 전제가 바뀌면 다시 본다.

---

# 4. 닫힌 것 / 열린 것

## 4-1. 숫자

> **§9 의 11건 중 — 🟢 닫힘 5 · 🟡 좁혀짐 2 · 🔴 열림 4**

| # | 항목 | 상태 | 무엇으로 |
| --- | --- | --- | --- |
| 9-3 | 설비 중지 | 🟢 **닫힘** | A1 — `State` 에 `HOLD` 추가. 화면이 아니라 **M2c 와의 불일치**가 진짜 이유 |
| 9-4 | 가동 시간 | 🟢 **닫힘** | A2 — 기존이 초 단위 작업별 값으로 풀었고 실제로 그대로 돈다 ⇒ `State.duration_s` |
| 9-5 | 측정 스펙 | 🟢 **닫힘** | A3 — 공차는 `part.attrs`, "측정하는 노드"는 **`node.attrs jsonb` 신설** |
| 9-6 | 박스 마감 | 🟢 **닫힘** | A5 — `group_id` 규약 **기각**(조인 키가 끊긴다), 작은 테이블 `group_close` 권고 |
| — | 외부 식별자 | 🟢 **닫힘** | A6 — `node.external_ref jsonb`. 매핑 테이블은 선례 0건 |
| 9-7 | 인터록 | 🟡 **좁혀짐** | A4 — 지금은 **불가로 확정**. 미래 경로는 **B2 ④** 하나뿐 |
| 9-8 | `line_id` | 🟡 **좁혀짐** | A10 — **`RESIN-1` 설정값** 권고. 남은 건 *"재배치 전에 켜나"* 라는 일정 판단 |
| 9-1 | PG 위치 | 🔴 **열림** | **B5** — 공장 PC 디스크·백업·재기동 순서 |
| 9-1b | v1→PG | 🔴 **열림** | **C2** — 단 A7 로 난점이 특정됐다(인스턴스 3대) |
| 9-2 | loopback 면제 | 🔴 **열림** | **B1** — 외부 망에서 401/200 하나만 보면 된다 |
| 9-9 | 리모트 I/O | 🔴 **열림** | **B2** — 채널 배정 답 |
| 9-10 | 부품 ID 표기 | 🔴 **열림** | **B4** — 작업자가 고를 일 |

🆕 **A9(커넥션 경계)는 §9 에 없던 항목인데 열렸다** — `psycopg`·PG 가 없어 **실측 불가**.
설계서 §1-6 의 *"v2 도 SQLAlchemy Core"* 문장이 **읽기에만 참**이므로 정정 대상이다.

## 4-2. 열린 4건 — 무엇이 있어야 닫히나

| # | 필요한 것 | 걸리는 시간 |
| --- | --- | --- |
| 9-2 | **외부 망에서 `curl` 한 번** (B1 ②) | 🥇 **5분. 가장 싸고 가장 급하다** |
| 9-9 | 예승님/설치 담당 **회신 1건** (B2) | 메일 1통 + 대기 |
| 9-10 | **작업자와 5분 대화** (B4) | 출근일 |
| 9-1 | 공장 PC **디스크·백업 확인** (B5) | 출근일 10분 |
| (A9) | **PG + psycopg 를 띄워 중첩 트랜잭션 1회 시험** | 개발 환경 구축 반나절 |

## 4-3. ⚠️ 이 조사가 답하지 않은 것

- **B1~B5 를 대신 판정하지 않았다** — 실물·사람이 있어야 하는 것들이다.
- **A9 는 추측으로 채우지 않았다** — 그릴 수 있는 한 줄은 냈으나 **[미검증]** 이다.
- `IO.csv` 가 우리 공장 것이 아니라는 판정은 **스키마 조사를 인용**한 것이고 이번에 다시 재지 않았다.

## 4-4. 🥇 이 조사에서 확인된 패턴

> **"신규에 자리가 없다" 는 대부분 "기존이 다른 이름으로 풀어놨다" 였다.**

| 신규가 없다고 한 것 | 기존이 풀어놓은 방식 | 신규가 취할 것 |
| --- | --- | --- |
| 가동 시간 | `print_command.washing_time`(초·작업별·실제 동작) | 개체에 싣는다 ⇒ `State.duration_s` |
| 설비 중지 | `cell_state.paused`(셀 전체·drain) | **같은 것이 아니다.** 층이 다르니 따로 둔다 |
| 박스 마감 | `allocated_data` jsonb 자유 키 | 식별자를 바꾸지 않고 **옆에 적는다** |
| 외부 식별자 | `PRINTER_SERIAL_MAP` 코드 상수 · `DEFAULT_CAMERAS` | 설정 한 곳 ⇒ `node.external_ref` + 토폴로지 |
| 인터록 | 🔴 **정말로 없었다** | 만들지 않는다 |

⇒ 📌 **다섯 중 넷은 기존에 있었다.** 다음 설계에서도 *"없다"* 를 적기 전에 **기존을 먼저 grep** 한다.
