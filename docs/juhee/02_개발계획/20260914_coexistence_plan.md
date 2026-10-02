작성 2026-09-14 (월) KST · 근거 = `20260911/` 계획 3종 + 소스 실측
선행 문서 = `20260911/기존 비교/계획 수정 — 기존 자산 재사용.md`(결정 6건 제기)

# 이 문서가 하는 일

신규 설계안(PostgreSQL)과 기존 운영 시스템 둘을 **병존시킬 때 생기는 충돌을 줄이는 계획**이다.

선행 문서가 **"결정이 필요한 것 6건"** 으로 열어둔 것에 답을 붙이고,
그 답이 **어느 파일을 몇 줄 바꾸는지**까지 내린다.

네 가지를 다룬다.

1. 스키마 — 이름 규칙 적용 · 다리 · 바꿔야 할 코드
2. 모듈 — M2a · M2b · M3b · M5a · M5b 의 수정 범위와 기존 로직 침범 여부
3. 폴더 — `web-api` 의 제어/통신/모니터링/API 혼재
4. **반대 방향** — 기존 코드를 읽고 **신규 모듈 계획** 쪽을 고쳐야 하는 것 4건

---

# 1. 스키마

## 1-0. 결론 먼저

> **기존 DB DDL 변경 0건 · 기존 운영 코드 변경 0건.**
> 손대는 것은 **아직 배포되지 않은 신규 스키마 5줄**뿐이다.

## 1-1. 결정 1 — 대체가 아니라 병존이다

선택지가 아니라 강제다.

| 근거 | 내용 |
| --- | --- |
| C 에 갈 곳이 없는 기존 개념 **7건** | `presets` `print_jobs` `notification_events` `print_notes` `vision_cameras` `binpick_scenes` `cell_state` |
| `print_command` 대체 = 제어 재작성 | 로봇 제어 루프를 갈아엎는 일이고 **P5(10/31 이후)** 범위다 |

⇒ **A(SQLite `presets.db`) · B(MariaDB `automation`) · C(PostgreSQL) 세 DB 병존.**

## 1-2. 이름 규칙 적용 결과

적용한 규칙 — *같은 개념이면 기존 이름을 유지한다. 단 기존 이름을 따라가면서
신규 개념이 정체성을 잃으면 신규 이름을 쓴다.*

| 개념 | 기존 (A·B) | 신규 (C) | 판정 | 근거 |
| --- | --- | --- | --- | --- |
| 🔴 **로그 행 PK** | `automation_log.id` | `command_log.cmd_id` | **신규를 고친다 → `log_id`** | 아래 1-3 |
| 작업 개체 | `print_command` | `unit` | **신규 유지** | `unit` 은 PART · FDM · 부모자식을 담는다. "command" 로 가면 정체성 상실 |
| 설비 식별 | `target_printer=1` · `Form4-…` · `wash_1` | `node_id` `PRT-01` | **신규 유지** | 토폴로지-as-데이터의 본체. 기존 값은 벤더 종속 |
| 지금 어느 공정 | `cmd_status` + `post_proc_stage` | `product_state.status` | **신규 유지** | 기존은 int 2개, 신규는 개체당 1개 — 다른 개념 |
| 공정 시간 | `washing_time` (작업별) | `node.std_cycle_s` (설비별) | **둘 다 유지** | 같은 이름을 붙이면 안 되는 서로 다른 값 |
| 이력 | `automation_log` (운영 로그) | `product_event` (개체 이력) | **둘 다 유지** | 겹치지 않는다 |
| `source` | 자유 문자열 (`robot` `system`) | `CAMERA` `ROBOT` `MANUAL` `ADAPTER` `SIM` | **이름 유지 · 값 분리** | 🚨 **두 컬럼을 조인하지 않는다** |
| 파트 | `presets.part_type` (문자열) | `part.part_no` (마스터) | **신규 유지** | 기존은 설정값, 신규는 품종 식별자 |

## 1-3. 🔴 `cmd_id` 충돌 — 유일한 실제 이름 사고

```
기존   print_command.cmd_id  = uuid, 작업 지시 하나의 정체성 (automation_log.cmd_id 가 참조)
신규   command_log.cmd_id    = bigserial, 조작 로그 행의 대리키 (정체성 없음)
```

**같은 이름 · 다른 뜻 · 같은 시스템 안.** 규칙상 정체성이 있는 기존 이름이 이긴다
⇒ **신규 쪽을 `log_id` 로 바꾼다.** 같은 스키마의 형제(`event_id` `scrap_id` `judgement_id`)와도
이 쪽이 일관된다 — 바꾸면 오히려 더 맞는다.

**비용 실측 = `schema.sql` 2줄.** 뷰 0건 · 파이썬 0건 · 데이터 0건.

📌 **지금이 공짜인 마지막 시점이다.** 데이터가 생기면 이사가 된다.

## 1-4. 다리 2개 — 신규 쪽에만 컬럼을 더한다

선행 문서의 *"가장 큰 구멍 = 식별자 다리가 없다"* 에 대한 답이다.

### ① `unit.cmd_id text UNIQUE NULL` (결정 2 · 3)

여기서는 **기존 이름 `cmd_id` 를 그대로 쓴다** — 개념이 정확히 같기 때문이다.

```
print_command  = 지시(제어)의 진실      ← sequence_service 만 쓴다
unit           = 개체(관측)의 진실      ← state_engine 만 쓴다

생성 방향      print_command INSERT → Spawn 발행 → unit 생성     (한 방향)
역방향 쓰기    없음                                              ← 5/29 계열 사고 차단
```

- 배치가 부품으로 쪼개지면 `print_command` 에 담을 개념이 없다
  ⇒ PART 는 `parent_unit_id` 로 상속. **다리는 BATCH 에만 필요하다**
- 수동 투입 · 시뮬레이터는 `cmd_id = NULL` — 정직하게 비운다

### ② `node.external_ref jsonb` (결정 4)

```json
{"printer_serial": "Form4-CapableGecko", "legacy_target_printer": 1,
 "mqtt": "wash_1", "io": "PET#1/DI2"}
```

매핑 테이블 대신 **컬럼 하나**. 근거 = 노드 18개라 어댑터 기동 시 dict 로 한 번 읽으면 끝이고,
인덱스·제약이 값을 하지 못한다.

⭐ 종류가 늘어 **역방향 조회에 제약이 필요해지면** 그때 `node_external_id` 테이블로 승급한다.
`ponytail:` 주석으로 승급 경로만 남긴다.

### ③ `source` 주석에 `IO` 추가

리모트 I/O 접점은 추정이 아니라 확정이므로 `confidence` 는 NULL 로 둔다.
`schema.sql` 에 CHECK 가 없어 **주석 1줄**이다.

## 1-5. 나머지 결정

| # | 질문 | 답 | 근거 |
| --- | --- | --- | --- |
| 5 | 빈피킹 게이트 판정 | **`binpick_scenes` 에 그대로 둔다** | 주제가 다르다 — 라인 개체가 아니라 **인식 품질**이다. 옮길 이유 0, 틀렸을 때 비용 0 |
| 6 | 카메라 건강 · 알림 · `cell_state` | **A·B 에 그대로** | 프론트 7탭이 이걸 읽고 **7탭은 존치 확정** |

⭐ 5번이 나중에 이어질 자리 — ARM-B 가 부품을 집으면 `Moved(source='ROBOT')` 이고,
`scene_id` 는 `product_event.msg` 또는 `judgement.value` 에 참조로 남기면 된다. **테이블 이관이 아니다.**

## 1-6. ⇒ 바꿔야 할 코드 · 모듈

| 대상 | 변경 |
| --- | --- |
| `schema.sql` | `cmd_id`→`log_id` **2줄** · `unit.cmd_id` **1줄** · `node.external_ref` **1줄** · `source` 주석 **1줄** |
| `schema.md` · `20260911/스키마.md` | 같은 4건 |
| `contract.py` | `Spawn` 에 `cmd_id` 필드 1개 |
| `state_engine.py` | `_spawn` 이 `cmd_id` 를 `unit` 에 넣는다 |
| `topo_sync.py` · `topology.yaml` | `external_ref` 읽기·쓰기 — **P4 전까지 미뤄도 된다** |
| 🟢 **기존 운영 코드** | **0건** |
| 🟢 **기존 DB DDL** | **0건** |

🐛 **곁가지** — `contract.py` 독스트링이 `container_id` 를 설명하는데 코드는 `group_id` 다.
물리 모방 설계의 잔재이고, 읽는 사람이 없는 필드를 찾게 된다. 같이 고친다.

---

# 2. 모듈 수정 범위

## 2-0. 한눈에

| 모듈 | 기존 파일 | 실제 수정 | 기존 로직 침범 |
| --- | --- | --- | --- |
| **M2a** MQTT | `web-api/app/vision/schemas.py:38` | 타입 넓히기 **1줄** + 어댑터 신규 | 🟢 없음 |
| **M2b** Modbus | `sequence_service/app/cell/sequences/robot.py:204` | 발행 **1줄** | 🟡 **블로킹 주의 — 2-2** |
| **M3b** 반송 | 같은 파일 같은 줄 | **M2b 와 동일 작업** (별건 아님) | 🟢 ①~⑦ 무변경 |
| **M5a** Repeat | — | **0건** | 🟢 Grafana 는 뷰만 읽는다 |
| **M5b** 라인 개요 | — | **0건** (10/31 이후) | 🟢 |

## 2-1. M2a — 기존 `except Exception` 을 믿으면 안 된다

**수정** = `vision/schemas.py:38` `timestamp: str` → `float | str`.
타입을 **넓히는** 것이라 기존 str 입력도 그대로 통과한다 — 하위 호환이다.

🚨 **발행 코드를 `mqtt_client.py:86-88` 의 `except Exception` 안에 넣지 않는다.**
그 블록이 지금 `ValidationError` 를 삼켜 **실물 메시지를 전건 버리고 있고**(vision 미가동의 원인),
같은 자리에 발행을 넣으면 **새 버그도 똑같이 조용히 사라진다.** 발행은 블록 바깥에 자체 try 로.

🚨 **`wash_1 → WSH-01` 은 개명이 아니라 매핑표다.** 네 문자열이 네 곳에 박혀 있다 —
`camera_manager.py:30-33` · `simulator.py:19-24` · `schemas.py:133` ·
`routes.py:117`(`f"{device_type}_{device_id}"` 로 키 재조립).
**하나라도 개명하면 네 곳이 동시에 깨진다.** 매핑은 새 어댑터 안에만 둔다.

## 2-2. 🚨 M2b — 진짜 위험은 "발행 실패" 가 아니라 "블로킹" 이다

계획서는 `try/except` 로 감싸라고만 한다. 그런데 `robot.py:402-631` 은 **논블로킹 스텝머신**이고,
여기서 psycopg `connect`/`INSERT` 를 하면 **예외가 안 나도 루프가 그만큼 멈춘다.** 로봇이 느려진다.

```
_complete_task  →  queue.Queue.put_nowait(Moved(...))      ← 논블로킹. 이것도 try/except
                   데몬 스레드가 소비해서 DB 에 쓴다        ← 여기서 죽어도 로봇은 안 멈춘다
```

큐가 차면 **버린다** — 관측이기 때문이다.
⭐ 이 한 가지가 *"관측이 제어를 막지 않는다"* 를 실제로 보장하는 부분이다.
`try/except` 만으로는 예외는 막아도 지연은 못 막는다.

레지스터 맵(`sequence_service/app/core/config.py:36-42`)은 **읽기만** 한다. 제어 변경 0.

## 2-3. M3b — P4 에서는 M2b 와 같은 작업이다

별도 모듈 작업처럼 보이지만 **P4 범위에서는 같은 파일 같은 한 줄**이다.
후보 산출 ①~④ · 자원 배정 ⑤~⑦ 은 **무변경**.

**P5(10/31 이후)에만** 아래가 이관 대상이 된다.

| 대상 | 지금 하는 일 |
| --- | --- |
| `robot.py:72 _select_executable_task()` | ①~④ |
| `robot.py:101/104/116 _find_free_*()` | ④ 자리 확인 |
| `robot.py:86 _priority()` | ⑦ 우선순위 |
| `mainSequence.py:20-33` | 설비 개수를 인스턴스 생성으로 고정 (경화기 2호기는 주석 처리) |
| `enums.py:19-28 PostProcStage` | 공정 순서를 IntEnum 으로 고정 |

🔴 **지금 하면 안 되는 이유** = 로봇암은 한 대인데 판단하는 코드가 두 벌이 된다.
둘이 같은 순간 다른 결론을 내고 둘 다 레지스터 `130` 에 쓴다.

📌 마이그레이션 시 `PostProcStage` **값을 `step_order` 로 쓰면 안 된다** — 세척→경화에서 `60 → 10` 으로
역행한다. 순서는 `route` 의 MAIN 엣지로 잡는다.

## 2-4. 🔴 M5a · M5b 를 "기존 코드 수정" 으로 잡은 것은 과하다

| | 보는 것 |
| --- | --- |
| 기존 `monitoring` 탭 | **프린터 대수**의 상태 |
| 신규 대시보드 | **제품 개체**의 라인 통과 현황 |

**대상이 다르므로 `frontend/` 는 변경 0건이다.**

실제로 UI 를 건드리는 모듈은 **M2m(수동 조작)** 이고, 그것도 `wireframe/` 이라는 **별도 Vite 앱**이라
지금은 역시 변경 0건이다. 프론트와 합칠지는 **M5a 가 실물 데이터로 검증된 뒤**에 정한다.

---

# 3. 폴더 — 지금 옮기지 않는다

## 3-1. 혼재는 사실이다 (실측 3건)

| # | 증거 |
| --- | --- |
| 1 | **web-api 가 제어 DB 에 직접 쓴다** — `local/automation_db.py` 안에서 `print_command` **4곳** · `cell_state` **3곳** · `automation_log` 1곳 · `automation_comm_config` 2곳 + **런타임 `CREATE TABLE` 2곳** |
| 2 | **web-api 가 DIO 하드웨어를 직접 연다** — `local/ajin_io.py`. `sequence_service/app/io/ajin_io.py` 와 **구현이 다른 두 벌**이고, 같은 AXL DLL 을 두 프로세스가 연다 |
| 3 | **프로세스 관계가 양방향** — 루트 `main.py` 도 web-api 를 띄우고 `sequence_service/app/main.py:66` 도 띄운다(`START_WEB`) |

## 3-2. 그런데 지금 옮기면 손해다

P1~P3 이 **"운영 코드 전부 무변경"** 으로 설계돼 있다.
8,700줄을 이사하면 그 전제가 깨지고 NSSM 서비스 · `deploy.bat` · 3개 서버 배포가 전부 검증 대상이 된다.
**얻는 것은 폴더 이름뿐이다.**

## 3-3. 대신 3가지

### ① 경계를 규칙으로 고정한다 — 문은 이미 좁다

제어 DB 쓰기의 **호출자를 실측하니 `local/routes.py` 하나**였다.
즉 경계는 이미 파일 한 쌍이다. 옮기는 대신 규칙으로 박는다.

> **제어 DB 쓰기는 `automation_db.py` 를 통해서만 한다.**

다른 파일에서 `print_command`/`cell_state` 에 쓰면 **실패하는 검사 하나**(~20줄)를 둔다.
`ajin_io.py` 두 벌도 여기에 `ponytail:` 로 표시만 한다 — **삭제는 안 된다.**
수동 IO 화면(`local/routes.py:47`)이 실제로 쓰고 있다.


### ② 신규 코드는 `sequence_service/app/line/` 으로 — 이것만 지금 한다

> 🔁 **2026-09-23 변경 — 신규 코드는 `sequence_service/app/line/` 이 아니라 리포 루트 패키지 `line_mes/` 로.**
> 사유 = 두 서비스의 패키지 이름이 둘 다 `app` 이다(`web-api/app` · `sequence_service/app`). web-api 프로세스에서
> `import app.line.state_engine` 은 자기 `app` 을 잡으므로 sequence_service 안의 엔진에 정상 import 로 닿을 수 없다 —
> 아래 3-3② 가 `contract.py` 에 대해 짚은 문제가 v2 쓰기 API(W1~W6 · web-api 가 `StateEngine.handle()` 직접 호출)에서는
> **엔진에도** 생긴다. 반대로 `web-api/app/line/` 에 두면 sequence_service 의 `Moved` 발행(M2b)이 `contract` 를 못 가져온다.
> 두 `app` 어디에도 속하지 않는 자리 = 루트 패키지. 설치 = 루트 `requirements.txt` `-e .`(오프라인 퇴로 = 아래 `PYTHONPATH` 2줄, 그대로 호환).
> 이 절의 원칙(의존 한 방향 · 프로세스는 하나로 시작 · 분리는 PG 위치가 정함)은 전부 유지 — 바뀐 것은 폴더만이다.
> 반영 = `20260922_API개발_전체계획.md` D5 · `20260922_API개발계획.md` §4.

관측 코드는 **제어와 같은 서비스 안에 둔다.** 프로세스도 하나로 시작한다.

| 근거 | 실측 |
| --- | --- |
| 개발 환경이 갈리지 않는다 | `sequence_service/app/__init__.py` 가 **빈 파일**이라 `app.line.simulator` 를 import 해도 Modbus·AXL 이 안 딸려온다 — Linux 개발기에서 그대로 돈다 |
| 의존성이 이미 하나다 | 루트 `requirements.txt` **하나를 두 서비스가 공유**하고, venv 도 `main.py` 가 web-api 것 하나로 해석한다 |
| 재배포도 이미 하나다 | `deploy.bat:67,84` 가 `NSSM stop/start OrinuMain` — **나눠도 따로 재시작되지 않는다** |
| 🥇 **P5 에서 제어가 결국 PG 에 붙는다** | M3b ②단계 = `route` · `ready_at` · `v_retrievable` 을 읽어 후보를 산출하는 일이다. 나눠두면 **그때 다시 합치는 꼴**이다 |
| 코드가 준다 | M2b→M3a 가 프로세스 내 호출이면 **이벤트 직렬화·전송 계층이 통째로 없어진다** |

⚠️ 남는 위험은 **관측 실패 격리** 하나이고, 그것은 폴더가 아니라 **PostgreSQL 위치**가 정한다 (3-4).

### 🔴 단 `contract.py` 하나만은 안으로 못 넣는다

**증거** — `web-api/app/local/routes.py:70` 이 이미 `sequence_service/app/cell/modbus_protocol.py` 를
**파일 경로로 로드**하고 있다 (`spec_from_file_location`, 주석 *"중복 없이 재사용"*).
두 폴더가 서로 import 할 수 없어서 나온 우회다. **`automation_db.py` 가 제어 DB 에 raw SQL 을 쓰는 것도 같은 이유**다.

M2m(수동 조작)은 web-api 에서 `Spawn`/`Moved`/`Split` 을 발행한다 ⇒ web-api 가 contract 를 import 해야 한다.
`sequence_service` 안에 두면 **경로 로드 우회를 한 번 더 하거나, PG 에 raw SQL 을 쓰거나** 둘 중 하나다
⇒ **세 번째 `automation_db.py` 가 생긴다.**

### ⇒ 배치

```
sequence_service/app/
  cell/     제어    (지금 그대로)
  line/     관측    topo_sync · state_engine · simulator · schema.sql · topology.yaml
contract.py         ← 루트. 두 서비스가 다 import 하는 유일한 파일
```

| 규칙 | 내용 |
| --- | --- |
| **의존 방향 한 방향** | `cell/` → `line/` (발행 함수 하나만). `line/` 은 `cell/` 을 모른다. 나중에 프로세스를 떼야 할 때 **그 한 줄이 경계**다 |
| **프로세스는 하나** | 분리는 PG 가 다른 머신에 있을 때만 (3-4) |
| 루트 import 경로 | `main.py` · `sequence_service/app/main.py` 가 자식 env 에 `PYTHONPATH=<repo root>` 한 줄씩. **둘 다 이미 `env` dict 를 만들고 있다** |

⚠️ web-api 를 uvicorn 으로 직접 띄우는 개발 상황에서는 `PYTHONPATH` 를 수동으로 준다.
스포너가 둘(`main.py` · `sequence_service/app/main.py`)이라 **양쪽에 넣어야 한다** — 한쪽만 넣으면
그 경로로 띄웠을 때만 import 가 깨진다.

### ③ 진짜 이사는 "어차피 그 파일을 열 때" 한다 = P4

`vision/mqtt_client.py` 와 `services/polling_service.py` 는 P4 에서 contract 를 발행하도록
**어차피 고친다.** 그때 `sequence_service/app/line/adapters/` 로 옮기면 diff 가 그 작업에 흡수된다.
그 전에 옮기면 **diff 만 크고 얻는 것이 없다.**

🚨 **이때 런타임 모델이 바뀐다** — 두 파일은 web-api 의 **asyncio** 루프에서 돌고
`sequence_service` 는 **threading** 이다. 전용 스레드에서 `asyncio.run` 으로 감싸는 일이 붙는다.
목적지가 어디든 드는 비용이지만 **P4 견적에 넣어둔다.**

## 3-4. 프로세스를 나눌지는 PostgreSQL 위치가 정한다

| PG 위치 | 프로세스 | 이유 |
| --- | --- | --- |
| **공장 PC** | 🟢 **하나** (`sequence_service` 가 제어 + 관측) | 프로세스 내 호출. P5 에서 제어가 PG 를 읽는 것도 그대로 성립 |
| 6000 등 다른 머신 | 🔴 둘로 강제 | 제어는 공장 PC 에 묶여 있고 M3a 는 PG 옆에 있어야 한다 ⇒ 공장 PC 는 **발행만**, 이벤트가 네트워크를 건넌다 |

⭐ **그래서 P1 의 "PostgreSQL 배치 결정" 이 폴더 문제의 상위 항목이다.**
`contract.py` 가 루트에 있고 의존 방향이 한 방향이면 **어느 쪽으로 결정돼도 이사가 작다** — 그것이 이 배치의 목적이다.

## 3-5. 최종 형태 (10/31 이후)

가르는 축은 **프로토콜이 아니라 방향**이다.

```
sequence_service/   cell/ = 제어    쓰는 통신(Modbus write) · 시퀀스 · MariaDB 소유
                    line/ = 관측    읽는 통신(MQTT · 폴링 · 206 구독) · M1 M3a M4 · PostgreSQL 소유
web-api/            API            HTTP · WS · 인증 · 정적. 두 DB 를 읽기만, 쓰기는 소유자 경유
contract.py         경계           M2 → M3a 이벤트 4종. 세 곳이 다 import 한다
```

⭐ `modbus_protocol.py` 는 제어와 관측을 다 하지만 **소유는 `cell/`** 이고 관측은 발행 한 줄로 얹힌다
⇒ **파일을 쪼갤 필요가 없다.**

🚨 **web-api 는 이미 제어 쪽으로 두 번 넘어가 있다** — 제어 DB 쓰기(3-1①)와
**자체 Modbus 마스터**(`local/routes.py:66` 가 `ModbusHandshakeClient` 를 직접 인스턴스화).
최종 형태로 가려면 이 둘이 `cell/` 호출로 바뀌어야 하지만 **지금은 규칙으로만 막는다**(3-1①).

---

# 4. 🔴 기존 코드가 신규 계획을 바꾸는 것

지금까지는 **신규에 맞춰 기존을 어떻게 고치나**였다. 반대 방향 — 기존 코드를 읽어보니
**신규 모듈 계획 쪽을 고쳐야 하는 것**이 4건 나왔다. 전부 P4 착수 전에 닫아야 한다.

## 4-1. 🥇 `Spawn` 을 발행할 주체도, 주문을 만들 경로도 없다

`state_engine.py:_spawn` 은 **주문이 먼저 있어야 동작한다.**

```
없는 주문이면            → raise
SHIPPED/CANCELLED 이면   → raise
order_line 이 비어 있으면 → raise
plate_count 초과면        → raise
```

그런데 **기존 운영에 주문 개념이 0건이다.** `print_command` 만 있고
`customer_order` · `order_line` 을 채우는 경로가 **어느 모듈에도 없다.**
스키마 문서는 *"영업·수주(외부 입력)"* 이라고만 적었고 **그 입력이 모듈 계획에 없다.**

⇒ **계획에 빠진 칸이다.** P2 는 시뮬레이터가 주문을 만들어 성립했지만, P4 실물에서는 만들 사람이 없다.

| 안 | 내용 | 판정 |
| --- | --- | --- |
| A | M2m 에 주문 등록 화면을 넣는다 | 🔴 P4 범위가 커진다 |
| B | `print_command` 1건 = 주문 1건 자동 생성 | 🟡 주문 개념이 실제로 들어오면 다시 갈아야 한다 |
| **C** | **기본 주문 하나**(`ORD-<일자>`)에 전부 묶고, 주문 UI 가 생기면 교체 | 🟢 **권고** — 가장 작고, `unit.cmd_id` 다리가 이미 진짜 이음매다 |

⚠️ C 를 택하면 `v_order_progress` 가 당분간 의미 없는 값을 낸다. **주문 데이터가 없으니 원래 의미가 없다** —
없는 값을 있는 것처럼 보이게 하지만 않으면 된다.

## 4-2. 🥇 `Spawn` 의 `plate_count` 거부를 P4 에서는 경고로 낮춘다

투입을 막는 곳이 **두 곳**이 된다 — 기존 제어(`_select_executable_task` 의 프린터 빈자리 판정)와
신규 `_spawn` 의 `plate_count` 상한.

제어가 이미 투입을 결정한 뒤에 `_spawn` 이 `raise` 하면, 발행부가 예외를 삼키므로 **라인은 안 멈추지만
`unit` 이 안 생긴다** ⇒ **그 배치가 대시보드에서 영영 안 보인다.** 조용히 사라지는 형태다.

⇒ **P4 에서는 `raise` 가 아니라 경고 + 생성**으로 낮춘다. 원칙 그대로다 — **관측이 제어를 판정하지 않는다.**
🔴 **P5 에서 제어가 `route` 를 보게 되면 그때 진짜 게이트로 승격**한다.

## 4-3. 🥇 M2b 의 `Moved` 는 `RobotTask` 만으로 만들 수 없다

계획서는 *"from/to 는 `ctx.py:40-42 RobotTask.from_unit`/`to_unit` 에서 온다"* 고 적었다.
**실측하니 목적지가 미지정인 경우가 있다.**

| task | `to_unit` | 실제 목적지 |
| --- | --- | --- |
| FW · SC · FC | `_select_executable_task` 가 **덮어쓴다** (`robot.py:165,181,193`) | 🟢 값 안에 있다 |
| **SW · P** | 🔴 **`'wash'` 그대로** — 덮어쓰지 않는다 | `job.allocated_data['wash_id']` |

⇒ 그대로 짜면 `to_node='wash'` 가 실려 나가고 **`route` 에 없어 `_moved` 가 거부한다.**
`_complete_task` 자신은 이미 `allocated_data` 에서 꺼내 쓰고 있다(`robot.py:213-215`) — **거기서 같이 꺼낸다.**

**그리고 식별자 형식이 다르다** — `node.external_ref` 가 프린터 시리얼만이 아니라 이것도 담아야 한다.

```
printer-1..4 → PRT-01..04      wash-1,2 → WSH-01,02
cure-1       → CUR-01          output   → @DONE 그룹의 완료 랙
```

✅ 곁가지 확인 — ASIS 라우트가 **경화기 1대(`CUR-01`)** 로 돼 있어 `mainSequence.py:33`
(2호기 주석 처리)과 **일치한다.** 여기는 손댈 것이 없다.

## 4-4. 🟡 프린터 `DONE` 을 15초 폴링으로 잡으면 놓칠 수 있다

`formlabs_client.py:554-561` — 출력이 끝나도 **플레이트를 빼면 `ready_to_print=READY` 가 되어
상태가 `IDLE` 로 바뀐다**(6/1 stale 버그 수정분). 즉 `FINISHED` 는 **출력 완료 ~ 플레이트 반출 사이에만
보이는 전이 상태**다.

계획의 M2c 매핑은 `FINISHED → DONE` · `IDLE → 발행하지 않음` 이다.
**폴링 주기(15초) 안에 반출되면 `DONE` 이 한 번도 발행되지 않는다.**
그러면 M3a 에서 `status` 가 `RUN` 에 남고, `_moved` 의 채번 조건 ①(`status=='DONE'`)이 막혀
**`P` 번호가 안 붙는다.** 에러 없이 번호만 비는 형태다.

⚠️ **실제로 일어나는지는 [미확인]** — 반출까지 15초 이상 걸리면 안 겪는다. 다만 **전이 상태를 폴링으로 잡는
구조**이고, 이 프로젝트는 같은 형태로 이미 한 번 당했다(6/1 stale 버그 자체).

⇒ **권고 — 프린터의 "완료" 1차 정보원을 프린터 API 가 아니라 `print_command.cmd_status = 40 PRINT_FINISHED`
로 바꾼다.** 제어가 이미 완료를 판정해 **DB 에 래치해 두었고 사라지지 않는다.**
M2c 는 `RUN`/`ERROR`/진행률 관측용으로 남고 **`DONE` 은 제어 쪽에서 낸다.**

📌 이것은 계획의 **"설비별 1차 정보원" 표를 고치는 일**이다.

## 4-5. 바뀌지 않는 것

M1 · M3a 의 불변식 · M4 뷰 · 계약 4종은 **그대로다.**
위 4건은 전부 **발행 지점과 값의 출처** 문제이지 모델 문제가 아니다.

---

# 5. 착수 순서

**A. 신규 스키마·배치 — 지금이 공짜인 것**

| # | 할 일 | 비용 | 지금 해야 하는 이유 |
| --- | --- | --- | --- |
| 1 | `command_log.cmd_id` → `log_id` | 2줄 | 데이터가 생기면 이사가 된다 |
| 2 | `unit.cmd_id` · `node.external_ref` · `source: IO` | 3줄 + 문서 | P4 어댑터가 이것 없이는 `unit` 을 못 찾는다 |
| 3 | 루트 5파일 → `sequence_service/app/line/`, `contract.py` 만 루트 유지 | 이동 + `PYTHONPATH` 2줄 | untracked 인 지금이 공짜 |
| 4 | **PostgreSQL 배치 결정** | 결정 | **P1 을 막고, 3-4(프로세스 수)의 상위 항목** |

**B. 모듈 계획 정정 — P4 착수 전 (§4)**

| # | 할 일 | 근거 |
| --- | --- | --- |
| 5 | **주문 생성 경로 결정** — 기본 주문 하나로 시작 | 4-1. 없으면 `_spawn` 이 전건 `raise` |
| 6 | `_spawn` 의 `plate_count` 거부 → **경고 + 생성** | 4-2. 배치가 조용히 사라진다 |
| 7 | `external_ref` 에 `printer-1`·`wash-2`·`cure-1`·`output` 매핑 추가 | 4-3. SW/P 는 `to_unit` 이 `'wash'` 그대로다 |
| 8 | 프린터 `DONE` 정보원을 `cmd_status=40` 으로 | 4-4. `FINISHED` 는 전이 상태라 폴링이 놓칠 수 있다 |

**C. 기존 코드 — 최소 수정**

| # | 할 일 | 비용 |
| --- | --- | --- |
| 9 | `vision/schemas.py:38` 타입 넓히기 | 1줄. 이것 전까지 M2a 는 실질 미가동 |
| 10 | `contract.py` 독스트링 `container_id` 정정 | 주석. 옛 설계 잔재 |

**건드리지 않는 것** — 기존 DB DDL · `frontend/` · `robot.py` 의 ①~⑦ ·
`camera_manager.py` 상수 4곳 · `ajin_io.py` 두 벌 · `local/routes.py` 의 Modbus·제어DB 경로 ·
M1 · M3a 불변식 · M4 뷰 · 계약 4종.

---

# 6. 미룬 것과 재개 조건

| 미룬 것 | 재개 조건 |
| --- | --- |
| 어댑터 이사 (`mqtt_client` · `polling_service` → `line/adapters/`) | **P4 에서 그 파일을 어차피 열 때** (asyncio→threading 비용 포함) |
| 프로세스 분리 | **PG 가 공장 PC 가 아닌 곳으로 정해질 때** |
| `node_external_id` 매핑 테이블 | `external_ref` 역방향 조회에 **제약이 필요해질 때** |
| `print_command` ↔ `unit` 통합 | **10/31 이후** (P5 제어 이관과 한 몸) |
| web-api 의 제어 경로 2건 회수 (제어DB 쓰기 · 자체 Modbus 마스터) | **P5 에서 `cell/` 을 어차피 고칠 때** |
| `ajin_io.py` 두 벌 정리 | 두 프로세스가 **같은 DLL 을 동시에 여는 사고가 실제로 날 때** |
| 빈피킹 · 알림 · 카메라 건강 이관 | **하지 않는다** (주제가 다르다) |

---
# 부록 — 확인 방법

```bash
# 1-3. cmd_id 충돌 · 개명 비용
grep -n "command_log\|cmd_id" schema.sql state_engine.py topo_sync.py simulator.py contract.py
grep -n "cmd_id" sequence_service/app/db/models.py        # print_command.cmd_id = String(36)

# 3-1①. web-api 가 제어 DB 에 쓰는 자리
grep -n "INSERT INTO\|UPDATE \|CREATE TABLE" web-api/app/local/automation_db.py
grep -rln "automation_db" web-api --include=*.py          # 호출자 = local/routes.py 하나

# 3-1②. DIO 두 벌
diff web-api/app/local/ajin_io.py sequence_service/app/io/ajin_io.py
grep -rn "ajin_io" web-api --include=*.py | grep -v "local/ajin_io.py"

# 3-1③. 프로세스 양방향
grep -n "uvicorn" main.py sequence_service/app/main.py

# 2-1. M2a 선행 버그
grep -n "timestamp" web-api/app/vision/schemas.py         # :38 str
grep -n "except Exception" web-api/app/vision/mqtt_client.py   # :86-88

# 3-3②. line/ 을 sequence_service 안에 넣어도 되는 근거
cat sequence_service/app/__init__.py                      # 빈 파일 = import 부작용 없음
grep -niE "nssm (stop|start)" deploy.bat                  # 재시작 단위가 이미 OrinuMain 하나
ls requirements.txt sequence_service/requirements.txt     # 루트 하나를 공유

# 3-3②. contract.py 만 루트여야 하는 근거 — 폴더 간 import 우회가 이미 있다
sed -n '65,83p' web-api/app/local/routes.py               # spec_from_file_location 으로 경로 로드
grep -n "ModbusHandshakeClient" web-api/app/local/routes.py   # web-api 자체 Modbus 마스터

# 4-1. 주문 없이는 spawn 이 안 된다
grep -n "없는 주문\|SHIPPED\|plate_count\|품목이 없습니다" state_engine.py
grep -rn "customer_order\|order_line" web-api sequence_service --include=*.py   # 0건

# 4-3. SW/P 만 목적지가 미지정이다
grep -n "to_unit=" sequence_service/app/cell/sequences/*.py
grep -n "task.to_unit = \|allocated_data\['wash_id'\]" sequence_service/app/cell/sequences/robot.py

# 4-4. FINISHED 는 전이 상태다
sed -n '552,566p' web-api/app/services/formlabs_client.py

# 2-2. M2b 발행 지점
grep -n "_complete_task\|STEP0070" sequence_service/app/cell/sequences/robot.py
```

⚠️ `sequence_service` 의 실물 DB 는 공장 PC 에만 있다 — 이 문서의 B 쪽은 **소스 기준**이다.
