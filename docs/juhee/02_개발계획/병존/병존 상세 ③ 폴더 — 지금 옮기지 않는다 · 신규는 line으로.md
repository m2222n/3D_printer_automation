# 3-1. 혼재는 사실이다 — 실측 3건

| # | 증거 |
| --- | --- |
| 1 | **web-api 가 제어 DB 에 직접 쓴다** — `local/automation_db.py` 안에서 `print_command` **4곳** · `cell_state` **3곳** · `automation_log` 1곳 · `automation_comm_config` 2곳 + **런타임 `CREATE TABLE` 2곳** |
| 2 | **web-api 가 DIO 하드웨어를 직접 연다** — `local/ajin_io.py`. `sequence_service/app/io/ajin_io.py` 와 **구현이 다른 두 벌**이고, 같은 AXL DLL 을 두 프로세스가 연다 |
| 3 | **프로세스 관계가 양방향** — 루트 `main.py` 도 web-api 를 띄우고 `sequence_service/app/main.py:66` 도 띄운다(`START_WEB`) |

---

# 3-2. 그런데 지금 옮기면 손해다

P1~P3 이 **"운영 코드 전부 무변경"** 으로 설계돼 있다. 8,700줄을 이사하면 그 전제가 깨지고 NSSM 서비스 · `deploy.bat` · 3개 서버 배포가 전부 검증 대상이 된다. **얻는 것은 폴더 이름뿐이다.**

---

# 3-3. 대신 3가지

## ① 경계를 규칙으로 고정한다 — 문은 이미 좁다

제어 DB 쓰기의 **호출자를 실측하니 `local/routes.py` 하나**였다. 즉 경계는 이미 파일 한 쌍이다. 옮기는 대신 규칙으로 박는다.

> **제어 DB 쓰기는 `automation_db.py` 를 통해서만 한다.**
> 

다른 파일에서 `print_command`/`cell_state` 에 쓰면 **실패하는 검사 하나**(~20줄)를 둔다. `ajin_io.py` 두 벌도 여기에 `ponytail:` 로 표시만 한다 — **삭제는 안 된다.** 수동 IO 화면(`local/routes.py:47`)이 실제로 쓰고 있다.

## ② 신규 코드는 `sequence_service/app/line/` 으로 — 이것만 지금 한다

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

**증거** — `web-api/app/local/routes.py:70` 이 이미 `sequence_service/app/cell/modbus_protocol.py` 를 **파일 경로로 로드**하고 있다 (`spec_from_file_location`, 주석 *"중복 없이 재사용"*). 두 폴더가 서로 import 할 수 없어서 나온 우회다. **`automation_db.py` 가 제어 DB 에 raw SQL 을 쓰는 것도 같은 이유**다.

M2m(수동 조작)은 web-api 에서 `Spawn`/`Moved`/`Split` 을 발행한다 ⇒ web-api 가 contract 를 import 해야 한다. `sequence_service` 안에 두면 **경로 로드 우회를 한 번 더 하거나, PG 에 raw SQL 을 쓰거나** 둘 중 하나다 ⇒ **세 번째 `automation_db.py` 가 생긴다.**

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

⚠️ web-api 를 uvicorn 으로 직접 띄우는 개발 상황에서는 `PYTHONPATH` 를 수동으로 준다. 스포너가 둘(`main.py` · `sequence_service/app/main.py`)이라 **양쪽에 넣어야 한다** — 한쪽만 넣으면 그 경로로 띄웠을 때만 import 가 깨진다.

## ③ 진짜 이사는 "어차피 그 파일을 열 때" 한다 = P4

`vision/mqtt_client.py` 와 `services/polling_service.py` 는 P4 에서 contract 를 발행하도록 **어차피 고친다.** 그때 `sequence_service/app/line/adapters/` 로 옮기면 diff 가 그 작업에 흡수된다. 그 전에 옮기면 **diff 만 크고 얻는 것이 없다.**

<aside>
🚨

**이때 런타임 모델이 바뀐다** — 두 파일은 web-api 의 **asyncio** 루프에서 돌고 `sequence_service` 는 **threading** 이다. 전용 스레드에서 `asyncio.run` 으로 감싸는 일이 붙는다. 목적지가 어디든 드는 비용이지만 **P4 견적에 넣어둔다.**

</aside>

---

# 3-4. 프로세스를 나눌지는 PostgreSQL 위치가 정한다

| PG 위치 | 프로세스 | 이유 |
| --- | --- | --- |
| **공장 PC** | 🟢 **하나** (`sequence_service` 가 제어 + 관측) | 프로세스 내 호출. P5 에서 제어가 PG 를 읽는 것도 그대로 성립 |
| 6000 등 다른 머신 | 🔴 둘로 강제 | 제어는 공장 PC 에 묶여 있고 M3a 는 PG 옆에 있어야 한다 ⇒ 공장 PC 는 **발행만**, 이벤트가 네트워크를 건넌다 |

⭐ **그래서 P1 의 "PostgreSQL 배치 결정" 이 폴더 문제의 상위 항목이다.** `contract.py` 가 루트에 있고 의존 방향이 한 방향이면 **어느 쪽으로 결정돼도 이사가 작다** — 그것이 이 배치의 목적이다.

---

# 3-5. 최종 형태 — 10/31 이후

가르는 축은 **프로토콜이 아니라 방향**이다.

```
sequence_service/   cell/ = 제어    쓰는 통신(Modbus write) · 시퀀스 · MariaDB 소유
                    line/ = 관측    읽는 통신(MQTT · 폴링 · 206 구독) · M1 M3a M4 · PostgreSQL 소유
web-api/            API            HTTP · WS · 인증 · 정적. 두 DB 를 읽기만, 쓰기는 소유자 경유
contract.py         경계           M2 → M3a 이벤트 4종. 세 곳이 다 import 한다
```

⭐ `modbus_protocol.py` 는 제어와 관측을 다 하지만 **소유는 `cell/`** 이고 관측은 발행 한 줄로 얹힌다 ⇒ **파일을 쪼갤 필요가 없다.**

🚨 **web-api 는 이미 제어 쪽으로 두 번 넘어가 있다** — 제어 DB 쓰기(3-1①)와 **자체 Modbus 마스터**(`local/routes.py:66` 가 `ModbusHandshakeClient` 를 직접 인스턴스화). 최종 형태로 가려면 이 둘이 `cell/` 호출로 바뀌어야 하지만 **지금은 규칙으로만 막는다**(3-3①).

---

# 확인 방법

```bash
# web-api 가 제어 DB 에 쓰는 자리
grep -n "INSERT INTO\|UPDATE \|CREATE TABLE" web-api/app/local/automation_db.py
grep -rln "automation_db" web-api --include=*.py          # 호출자 = local/routes.py 하나

# DIO 두 벌
diff web-api/app/local/ajin_io.py sequence_service/app/io/ajin_io.py
grep -rn "ajin_io" web-api --include=*.py | grep -v "local/ajin_io.py"

# 프로세스 양방향
grep -n "uvicorn" main.py sequence_service/app/main.py

# line/ 을 sequence_service 안에 넣어도 되는 근거
cat sequence_service/app/__init__.py                      # 빈 파일 = import 부작용 없음
grep -niE "nssm (stop|start)" deploy.bat                  # 재시작 단위가 이미 OrinuMain 하나
ls requirements.txt sequence_service/requirements.txt     # 루트 하나를 공유

# contract.py 만 루트여야 하는 근거 — 폴더 간 import 우회가 이미 있다
sed -n '65,83p' web-api/app/local/routes.py               # spec_from_file_location 으로 경로 로드
grep -n "ModbusHandshakeClient" web-api/app/local/routes.py   # web-api 자체 Modbus 마스터
```