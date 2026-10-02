> 2026-09-07 · 공정 자동화 모니터링
대상 저장소 `3D_printer_automation/`
> 

---

## 0. 왜 이렇게 나누었나

모듈 경계는 기능이 아니라 **바뀌는 이유**를 따라 그었다.
같은 이유로 함께 바뀌는 코드는 한 모듈에, 다른 이유로 바뀌는 코드는 다른 모듈에 둔다.

| 바뀌는 이유 | 그때 손대는 모듈 |
| --- | --- |
| 라인을 개조한다 (설비 증감, 랙 제거, 공정 추가) | M1만 |
| 설비 벤더·프로토콜이 바뀐다 | M2의 해당 어댑터만 |
| 업무 규칙이 바뀐다 (채번 방식, 상태 정의) | M3a만 |
| 반송 정책이 바뀐다 (우선순위, 로봇암 증설) | M3b만 |
| 보고 싶은 것이 바뀐다 | M4·M5만 |

이 표가 유지되지 않으면 분할이 실패한 것이다.
예를 들어 "프린터를 6대로 늘렸는데 M3a를 고쳐야 한다"면 M1의 경계가 새는 것이다.

### 경계를 지키는 세 가지 장치

1. **토폴로지를 데이터로.** 설비 개수·공정 순서가 코드에 없다. `node`/`route` 테이블에 있다.
2. **이벤트 계약 하나.** M2와 M3a 사이에 `Spawn`/`State`/`Moved`/`Split` 네 가지만 흐른다.
3. **관측과 제어의 분리.** M3a는 DB만 쓰고 로봇에 명령하지 않는다.

---

## M1 — 토폴로지

**판정** 신규 · **상태** 레퍼런스 완성·검증 (2라인 18노드 60엣지 · 295줄)

### 책임

`topology.yaml` 을 읽어 검증한 뒤 DB에 반영한다. 이 저장소에서
"라인이 어떻게 생겼는가"를 아는 **유일한 곳**이다.

### 하지 않는 것

- 런타임 상태를 모른다. 어느 제품이 어디 있는지 알지 못한다.
- 상시 프로세스가 아니다. 기동 시 또는 수동으로 한 번 돌고 끝난다.
- 이벤트를 받지 않는다.

### 입출력

```
입력   config/topology.yaml     라인·노드·경로·반송자원·플레이트 수
       config/sources.yaml      접속정보 (IP·포트·태그). 별도 파일인 이유는
                                토폴로지와 수명주기가 다르고 비밀값이 섞이기 때문
출력   line, node, node_slot, route, transporter, id_counter
```

### 핵심 개념

**노드 통합.** 설비와 랙을 하나의 `node` 로 본다. 랙은 "가공하지 않고 용량이 큰 노드"다.
이 통합 덕에 랙 제거와 설비 증설이 모두 *행 조작*이 된다.

**경로는 엣지.** `step_seq` 정수가 아니라 `route(from_node, to_node)` 로 표현한다.
정수를 쓰면 중간에 랙 하나를 빼는 순간 뒤쪽 번호를 전부 다시 매겨야 한다.
순서가 필요하면 `v_node_order` 가 그래프를 훑어 계산한다.

**`edge_kind`.** `MAIN` 은 공정 진행 방향, `DETOUR` 는 되주차·재작업, `EXIT` 는 폐기다.
실제 라인은 비순환이 아니다 — 현행 라인에는 `세척기 → 빈 프린터 되주차` 가 있고,
불량은 어느 공정에서든 폐기함으로 빠진다.
`MAIN` 만 **순서 계산과 순환 검사의 대상**이고 나머지는 이동만 허용된다.

**폐기는 담당을 두지 않는다.** 수동이라 지시가 나가지 않고 대기 지표에도 안 잡힐다.

**담당은 노드별.** `node.transporter_id` — "이 노드에서 나가는 이동은 누가 하나."
엣지별로 달라지는 것은 폐기뿐이었고 폐기는 담당이 없으므로, 엣지별 `route_handler` 와
span 전개 BFS 가 통체로 사라졌다. YAML 에는 `transporters[].nodes: ["@PRINTERS", ...]`.

**`span` 전개 — 제거됨.** 담당이 노드별이 되므로 엣지로 펼칠 이유가 없어진다.

**노드 그룹.** `groups:` 에 이름을 정의하고 route · transporters.nodes 에서 `"@이름"` 으로 참조한다.
같은 역할의 설비·랙이 늘면 groups 한 줄만 고치면 route 전체와 담당이 따라간다.

**칸 구조.** `slots: [4, 4]` → `node_slot` 2행, `node.capacity` 는 **합계로 자동 계산**.
`slot_access` (FIFO/LIFO/RANDOM) · `slot_fill` (SEQUENTIAL/BALANCED) · `count_by_group` 도 데이터다.

**화면도 데이터다.** `ui_kind` 가 조작 화면 종류를, `group_label` 이 서브 메뉴 이름을 정한다.
2차 서포트제거 같은 공정을 넣으면 `v_control_menu` 에 탭이 자동으로 생긴다 — 화면 코드는 안 바뀜다.
게이트가 하나 더 있다 — `splits_batch` 인 노드는 `ui_kind` 가 반드시 `BATCH_SPLIT` 이어야 한다.

**플레이트는 숫자.** `line.plate_count`. 동시에 라인에 있을 수 있는 배치 수의 상한.
재사용 자산은 개체로 추적하지 않는다 — 관측 시스템은 실물을 모방하지 않는다.

**비파괴.** YAML에서 사라진 노드는 `DELETE` 하지 않고 `is_active = false` 로 둔다.
과거 이벤트가 살아 있어야 사이클타임 분석이 된다.
제거는 두 단계다 — `draining: true` 로 신규 투입만 막고, 재고가 0이 되면 YAML에서 뺀다.

**`line_id`.** 목표 라인과 현행 라인을 동시에 등록하기 위한 이음매다.
FDM 도입 시에도 같은 장치를 쓴다. 재배치 전환은 route 재작성이 아니라
`unit.line_id` 발급 대상만 바꾸는 일이 되고, 진행 중 제품은 옛 라인으로 완주한다.

### 6개 검증 게이트

모두 통과해야 커밋한다. 하나라도 걸리면 기존 상태를 유지한다.

| # | 검사 | 범위 | 걸리는 예 |
| --- | --- | --- | --- |
| 1 | 순환 | **라인별 · MAIN만** | 되주차를 `kind: DETOUR` 로 표시하지 않음 |
| 2 | 고립 | **전역** | route에 연결되지 않은 노드 정의 |
| 3 | 재고 있는 노드 제거 | 전역 | 랙에 제품이 남았는데 YAML에서 삭제 |
| 4 | 참조 무결성 | 전역 | 정의되지 않은 노드/타입/라인 참조 |
| 5 | 담당 누락 / 중복 | 노드별 | MAIN·DETOUR 엣지가 나가는데 `transporter_id` 없음, 한 노드를 둘이 담당 |
| 6 | 칸 정합 | 전역 | 랙에 slots 없음, 설비에 칸 있음, slot_access/slot_fill 값 오류 |

⚠️ **1은 라인별, 2는 전역**이다. 헷갈리기 쉽다.
순환은 라인마다 따로 봐야 한다 — 두 라인이 노드를 공유하므로 합치면 오탐이 난다.
고립은 합쳐서 봐야 한다 — 노드는 *어느 한 라인에라도* 연결돼 있으면 정상이고,
라인별로 나누면 목표 라인에만 있는 `RK-DONE` 이 ASIS 라인에서 고립으로 잡힌다.

### 이 저장소에서의 이관 대상

| 위치 | 내용 | 처리 |
| --- | --- | --- |
| `sequence_service/app/cell/mainSequence.py:20-33` | 프린터 4 / 세척 2 / 경화 1 인스턴스 | → `node` |
| `sequence_service/app/cell/enums.py:19-28` | `PostProcStage` = 공정 순서 | → `route` |
| `sequence_service/app/cell/sequences/*.py` | 공정당 모듈 | → `node_type` 속성 |
| `web-api/app/vision/camera_manager.py:30-33` | 카메라 4대 (테이블 시드 상수) | 매핑표만. 상수 제거 아님 |
| `web-api/app/core/config.py:64-68` | `PRINTER_SERIALS` | **이관 불필요** — API 자동 발견 |

---

## M2 — 어댑터 계층 (공통)

### 책임

설비마다 제각각인 신호를 **네 가지 이벤트로 정규화**한다.

```python
Spawn(node_id, line_id, order_id, contents, source)             # 신규 투입
State(node_id, status, source, confidence)                      # 설비 상태 관측
Moved(unit_id | group_id, from_node, to_node,                   # 반송 완료
      transporter_id, slot_no, join_group, source)              #   unit/group 중 하나만
Split(unit_id, node_id, outputs, group_id, source)              # 배치 -> 부품 분해
```

- `Spawn.order_id` 필수. `contents` 를 비우면 `order_line` 을 그대로 배치 내용물로.
라인의 배치 수가 `plate_count` 에 다다르면 거부 — 정상적인 백프레셔
- `Moved.group_id` — 같은 꼬리표의 부품 전부가 함께 (바구니째 경화)
- `Moved.join_group` — 개별 이동인데 도착지에서 묶음에 합류 (OK 박스 적재)
- `Split.group_id` — 분해된 부품에 붙이는 꼬리표. 없으면 `G-{배치명}` 자동

### 하지 않는 것

- DB를 쓰지 않는다. 이벤트만 발행한다.
- 업무 판단을 하지 않는다. "이제 옮겨야 한다" 같은 결정은 M3b 몫이다.
- `State` 는 `unit_id` 를 싣지 않는다. **카메라는 제품 ID를 모른다.**
어느 제품인지는 M3a가 `node_id` 로 조회해 정한다.

### 왜 계약을 하나로 두는가

시뮬레이터와 실물 어댑터가 **같은 계약**을 쓰기 때문에, 실물로 교체할 때
M3a가 한 줄도 바뀌지 않는다. 이것이 "설비 없이 P2까지 개발한다"가 성립하는 이유다.

### 설계 규칙 두 가지

**위치를 바꾸는 것은 `Moved` 뿐이다.** `State` 는 절대 `node_id` 를 옮기지 않는다.
카메라는 추정이고 로봇의 이동 완료는 물리적 사실이다. 이 구분이 없으면
카메라 오탐 한 번에 제품 위치가 틀어진다.

**채번은 `Moved` 에서만 일어난다.** 카메라가 "끝난 것 같다"고 할 때 미리 번호를 따면
반송이 실패했을 때 번호가 새고, 순번이 실제 처리 순서와 어긋난다.

---

## M2a — MQTT 어댑터 (카메라)

**판정** 수정 · **기존 자산** `web-api/app/vision/mqtt_client.py`

### 담당 범위

세척기 2대, 경화기 2대. **프린터에는 카메라가 없다** (S2 토픽에 printer 없음).

### 입력

토픽 5개 — `factory/{wash|cure}/+/{status|heartbeat}`, `factory/camera/+/info`.
⚠️ 분기는 **토픽 마지막 세그먼트만** 본다. `+` 자리는 파싱되지만 쓰이지 않고,
설비 식별은 전부 페이로드에서 온다.

페이로드 `MQTTStatusMessage` — `camera_id`, `device_type`, `device_id`, `status`,
`confidence`, `timestamp`, `consecutive_count`, `fps`, `mem_free`

### 할 일

**1. 설비 ID 매핑**

| 페이로드 | node_id |
| --- | --- |
| `wash_1` / `wash_2` | `WSH-01` / `WSH-02` |
| `cure_1` / `cure_2` | `CUR-01` / `CUR-02` |

개명이 아니라 **매핑표**를 둔다. 네 문자열이 `camera_manager.py:29-34`,
`simulator.py:19-24`, `schemas.py:133` 에 박혀 있고,
`routes.py:117` 이 `f"{device_type}_{device_id}"` 로 키를 재조립하기 때문이다.

**2. 상태 어휘 매핑**

| MQTT | contract |
| --- | --- |
| `wash_running` / `cure_running` | `RUN` |
| `wash_complete` / `cure_complete` | `DONE` |
| `wash_idle` / `cure_idle` | 발행하지 않음 (제품이 없다는 뜻) |
| `offline` / `error` | `ERROR` |

**3. 통과 게이트**

디바운싱은 **새로 만들지 않는다.** 이미 디바이스에 있다 —
`OpenMV/scripts/config.py:39 DEBOUNCE_COUNT = 5`,
`wash_detector.py:197 CONFIDENCE_THRESHOLD = 0.7`.
어댑터는 `consecutive_count` 가 임계 이상인 것만 통과시키는 한 겹이면 된다.

### 🔴 선행 버그

디바이스는 `timestamp` 를 **float** 로 보내고 (`wash_detector.py:111`),
스키마는 **str** 을 요구한다 (`schemas.py:38`).
`mqtt_client.py:86-88` 의 `except Exception` 이 `ValidationError` 를 삼켜
**실물 메시지가 전건 사라진다.** 시뮬레이터는 `isoformat()` 을 보내서 통과한다.

**대응** — 스키마를 `float | str` 로 넓힌다. 발행 측을 고치면 현장 기기 4대를
재플래시해야 하고 롤백이 어렵다. 스키마 수정은 하위 호환이고 `deploy.bat` 으로 되돌린다.

⚠️ 이 버그를 고치기 전까지 **vision 상태감시는 실질 미가동**이다.

---

## M2b — Modbus 어댑터 (로봇암 A)

**판정** 수정 · **기존 자산** `sequence_service/app/cell/modbus_protocol.py`

### 방향

**우리가 마스터다.** `modbus_protocol.py:59 ModbusTcpClient` 로 로봇에 직접 쓴다.
초기 설계 시 우려했던 "우리가 슬레이브일 가능성"은 빗나갔다.

⚠️ `bin_picking/src/communication/modbus_server.py` 는 슬레이브지만
**파일 머리에 폐기 선언이 박혀 있다** (`:1-20`, 2026-07-30). 참조하지 말 것.

### 레지스터 맵 (정본 = `sequence_service/app/core/config.py:36-42`)

| 레지스터 | 뜻 | 방향 |
| --- | --- | --- |
| `130` | 명령값 (`P/SW=0` · `FW=1` · `FC=2`, 안전리셋 `100`) | PC → 로봇 |
| `131~135` | 파라미터 5개 — **좌표가 아니라 설비 ID·대기시간** | PC → 로봇 |
| `150` | 송신 트리거 | PC → 로봇 |
| `151` | PC Ready | PC → 로봇 |
| `200` | Robot Ready | 로봇 → PC |
| **`206`** | **Robot Moved = 이동 완료** | 로봇 → PC |

🚨 **`CLAUDE.md` 의 Modbus 절은 폐기된 맵이다.** 방향이 반대이고, 좌표는 애초에
Modbus로 가지 않으며, 실제 완료 레지스터 `200`/`206` 이 빠져 있다. 별건으로 정정 필요.

### `Moved` 발행 지점

`robot.py:402-631` 의 논블로킹 스텝머신이 `STEP0070`(`:578-598`)에서
레지스터 `206 == 1` 을 확인한 뒤 `robot.py:204 _complete_task(task)` 로 넘어간다.
**여기에 `Moved` 발행을 추가한다.**

from/to는 `ctx.py:40-42 RobotTask.from_unit` / `to_unit` 에서 온다.

### 🔴 반드시 지킬 것

**발행 실패가 반송을 멈추면 안 된다.** `try/except` 로 감싸 예외를 삼킨다.
관측이 제어를 막는 순간 이 모듈은 라인 정지의 원인이 된다.

### 담당 범위

이 경로는 **ARM-A 전용**이다. 빔피킹(ARM-B)은 `pick_socket_server.py` = 펜던트 소켓으로
완전히 별개 경로이며, ARM-B의 `Moved` 는 따로 만들어야 한다 (10/31 이후).

---

## M2c — 프린터 어댑터

**판정** 재사용 · **기존 자산** `web-api/app/adapters/` + `services/polling_service.py`

### 왜 손댈 게 적은가

`adapters/base.py:23 PrinterAdapter` Protocol 이 이미 벤더를 추상화하고 있고,
`formlabs_client.py:178 get_target_printers()` 가 **클라우드 API로 프린터를 자동 발견**한다.
`PRINTER_SERIALS` 가 플레이스홀더면 전체를 반환하므로 **프린터 증설에 코드 수정이 필요 없다.**

이 때문에 M1 이관 대상에서 프린터는 빠진다.

### 상태 매핑

`schemas/printer.py:200 PrinterSummary.status` →

| 프린터 API | contract |
| --- | --- |
| `PRINTING` / `PREHEAT` | `RUN` |
| `FINISHED` | `DONE` |
| `ERROR` / `OFFLINE` | `ERROR` |
| `IDLE` | 발행하지 않음 |
| `PAUSED` / `PAUSING` / `ABORTING` | `HOLD` |

### 카메라와 경쟁하지 않는다

프린터에는 카메라가 없으므로 정보원이 하나뿐이다. `source='ADAPTER'`.
폴링 주기는 이미 15초 (`config.py:58`).

FDM 프린터를 도입해도 어댑터 1개 + `factory.py` 분기 하나면 된다.

---

## M3a — 상태 엔진

**판정** 신규 · **상태** 레퍼런스 완성·검증

### 책임

이벤트를 받아 `product_state` 를 갱신하고, `display_id` 를 채번하고,
`product_event` 에 이력을 남긴다.

### 하지 않는 것

- **로봇에 명령하지 않는다.** DB만 쓴다.
- **타이머를 돌리지 않는다.** `ready_at` 으로 대체됐다.
- **공정 이름을 모른다.** `state_engine.py` 에 `'WASHER'` 같은 문자열이 0회 등장한다.
동작 차이는 전부 `node_type` 속성(`id_prefix`, `post_delay_s`, `node_kind`)에서 읽는다.
이것이 FDM 전환 대비의 실질적 증거다.

### 네 개의 핸들러

**`_spawn`** — 신규 배치 투입. 주문을 확인하고 **라인의 배치 수가 `plate_count` 미만**인지 본다.
`unit(BATCH)` 을 만들고 임시 `display_id`(`U-a1b2c3d4`)를 부여하고, 내용물을 `order_line` 에서 복사한다.

**`_state`** — 카메라/어댑터 관측. **위치를 바꾸지 않는다.**

- `RUN` → `status='RUN'`, `eta = now + std_cycle_s`
- `DONE` → `status='DONE'`, **`ready_at = now + post_delay_s` 를 한 번 계산**
- `ERROR` → `status='ERROR'`, `ready_at=NULL`

🔴 **노드에 있는 개체 전부에 적용한다.** 경화기처럼 한 번에 여러 개를 처리하는
설비가 있다. 하나만 갱신하면 나머지가 영원히 `RUN` 에 남는다 — 실제로 겪음.
노드에 개체가 없으면 경고만 남기고 무시한다.

**`_split`** — 서포트 제거에서 배치 → 부품 N개. `group_id` 꼬리표를 붙이고 `S` 번호를 준다.
부모 배치는 `consumed_at` 으로 소비되고 `product_state` 에서 빠진다 → 플레이트 자리가 자동으로 난다.
**NG 부품은 `outputs` 에 넣지 않는다** — `part_scrap` 으로 배치 내용물을 차감하고 `unit` 은 생기지 않는다.

🔴 **배치는 `splits_batch` 노드를 통과할 수 없다** — `_moved_unit` 이 거부한다.
토폴로지에 `부품분리 → 경화기` 엣지가 있어 반송 후보에 잡힐고, 분해 전에 경화기로 가는 버그가 났다 — 시뮬이 잡았다.

**`_moved`** — 반송 완료. **위치를 확정한다.**

- `unit_id` → 개체 하나. `group_id` → **묶음째** (같은 꼬리표 전부)
- 둘 다 `_relocate()` 를 공유한다 — 채번·위치 규칙이 두 벌이 되지 않도록
- `route` 검증 → 채번 → 위치 갱신 → 빠져나온 칸의 순번 당기기
- 개별 이동은 묶음에서 꺼내는 것 → `group_id` 가 끊긴다. `join_group` 이 있으면 도착지에서 새 묶음에 합류

### 캐리어는 없다

플레이트는 `line.plate_count` 숫자, 바구니·박스는 `group_id` 꼬리표다.
어느 바구니가 어디 있는지는 모른다 — 알 필요가 없다. "이 부품들이 같이 간다"만 알면 된다.
관측 시스템은 실물을 모방하지 않는다.

### 자리 결정 주체는 M3b다

로봇에게 목적지를 알려줘야 하므로 **M3b가 지시할 때 칸을 정하고 M3a는 결과를 기록**한다.
M3a가 자리를 고르는 것은 시뮬레이터용 경로다.

- 자리 선택 규칙은 **SQL 함수 `next_place(node_id)` 한 곳에만** 있다.
M3b와 M3a가 같은 함수를 호출한다 — 정의가 두 벌이면 지시한 자리와 기록한 자리가 어긋난다
- `Moved` 에 `slot_no` 를 실어 보낸다. **칸까지만** — FIFO는 밀어 넣으면
물리적으로 뒤에 붙으므로 위치(`pos_no`)는 로봇이 몰라도 된다
- 예약(`to_slot_no`)과 반송 큐는 **P5 에서** M3b 개조와 함께 `dispatch_queue` 로. 지금은 관측만 하므로 없다

### 채번 규칙 — 가장 미묘한 부분

**조건 ② `from_node` 에서 `status == 'DONE'` 이었을 것. 조건 ② `unit.named_at != from_node` — 그 노드에서 아직 이름을 받지 않았을 것.**
② 가 없으면 분해로 태어난 부품이 서포트 제거를 떠날 때 `S` 를 또 받는다 (`P1-W1-S1-S12`).

`edge_kind` 로 판별하면 **틀린다.** 되주차 경로에서도 세척기를 떠나는 것은
세척을 마친 것이므로 `W` 번호가 붙어야 한다. 반대로 보관용으로 되주차된 프린터는
`RUN` 을 겪지 않아 `WAIT` 에 머문다.

즉 `status` 가 이미 "가공했는가"를 알고 있다. `edge_kind` 는 순서 계산 전용이다.
**두 관심사가 각자의 장치를 쓴다.**

검증 결과:

| 경로 | display_id |
| --- | --- |
| 되주차 있음 (`PRT→WSH→PRT→CUR`) | `P1-W1-C1` — P가 두 번 붙지 않음 |
| 되주차 없음 (`PRT→WSH→CUR`) | `P2-W2-C2` |

카운터는 각 2. 부풀려지지 않는다.

### `ready_at` — 왜 상태가 아닌가

`SETTLING` 을 상태로 두면 `SETTLING → DONE` 전이를 **아무도 이벤트로 알려주지 않는다.**
시간이 흘렀을 뿐이다. 그러면 M3a에 타이머가 생기고, 재기동 시 복구 로직이 필요하고,
타이머가 누락되면 제품이 영구 정체한다.

`ready_at` 은 시간이 알아서 흐른다. 재기동해도 값이 거기 있다.
그리고 나중에 냉각을 온도 센서로 판정하기로 하면 `ready_at = now()` 로 앞당기기만 하면 되고,
M3b도 뷰도 바뀌지 않는다. **`ready_at` 은 "왜 아직 못 꺼내는지"의 판정 방식을 감싸는 계약이다.**

표시용 `SETTLING` 은 `v_product_display` 가 파생으로 계산한다.

### 불변식

| # | 규칙 | 깨지면 |
| --- | --- | --- |
| 1 | `State` 는 `node_id` 를 바꾸지 않는다 | 카메라 오탐이 제품 위치를 틀어뜨린다 |
| 2 | 채번 지점은 이 모듈 하나뿐이다 | 번호 중복 |
| 3 | `route` 에 없는 이동은 거부한다 | 유령 이동이 기록된다 |
| 4 | `ready_at` 은 완료 시 한 번만 계산한다 | 조회할 때마다 시각이 밀린다 |
| 5 | 캐리어(플레이트·바구니)는 `unit` 이 아니다 — 숫자와 꼬리표다 | 재사용 자산에 공정번호가 붙어 100번 바뀜다 |

---

## M3b — 반송 제어기

**판정** 수정 · **기존 자산** 🔴 **이미 존재** — `sequence_service` 의 `RobotSequence`

### 책임 — 7단계

**이동 후보 산출** (옮겨도 되는 것을 걸러낸다)

| # | 조건 | 근거 |
| --- | --- | --- |
| ① | 가공이 끝났나 | `status = 'DONE'` |
| ② | 꺼낼 수 있나 | `ready_at` 도래 — 건조·냉각 완료 |
| ③ | 갈 곳이 정해지나 | `route` 에 나가는 엣지 |
| ④ | 그 자리가 비었나 | 목적지 재고 < `capacity` |

**자원 배정** (그중 무엇을 누가 옮길지 정한다)

| # | 조건 | 근거 |
| --- | --- | --- |
| ⑤ | 누가 담당인가 | `node.transporter_id` — 노드별 담당자 하나 |
| ⑥ | 그 자원이 비었나 | `transporter_state ≠ MOVING` |
| ⑦ | 무엇을 먼저 | `priority`, 그다음 오래 기다린 것 |

### ⑦이 유일하게 판단인 이유

①~⑥은 기계적이다. ⑦은 처리량을 바꾼다.

로봇암이 유휴이고 후보가 둘이라고 하자. `PRT-01 → WSH` 를 하면 프린터 한 대가 풀리고,
`CUR-01 → 반출` 을 하면 경화기가 풀린다. 어느 쪽을 먼저 하느냐로 하루 생산량이 달라진다.
`robot.py:86 _priority(task_type)` 가 이 판단을 코드로 굳혀 놓은 것이다.

### 🔴 왜 신규를 만들면 안 되는가

M3b가 두 벌이면 판단하는 코드가 둘인데 **로봇암은 한 대다.**
두 프로그램이 같은 순간 서로 다른 결론을 내고 둘 다 레지스터 `130` 에 쓴다.
로봇은 나중에 쓰인 값을 실행하고 앞 지시는 사라진다. 제품이 어중간한 위치에 멈추거나,
최악의 경우 없는 물건을 집으러 간다.

### 기존 구현 대응

| 단계 | `sequence_service` |
| --- | --- |
| ①~④ | `robot.py:72 _select_executable_task()` |
| ④ 자리 확인 | `robot.py:101 _find_free_wash()` · `:104 _find_free_printer_without_plate()` · `:116 _find_free_cure()` |
| ⑦ | `robot.py:86 _priority(task_type)` |
| 지시 발행 | `robot.py:402-631` 스텝머신 |
| 완료 확인 | `robot.py:578 STEP0070` |

### 2단계 개조 계획

**① 관측 발행만 추가 (P4, ~10/31)** — `_complete_task` 에 `Moved` 발행 한 줄.
제어 로직 무변경. 예외를 삼켜 반송이 멈추지 않게 한다.

**② `route` 이관 (10/31 이후)** — ①~④를 `route`/`ready_at` 조회로 교체.
그러면 세척기가 3대가 돼도 `_find_free_wash()` 를 고칠 필요가 없어진다.
운영 중인 로봇 제어 코드 개조이므로 **대시보드가 실물 데이터로 검증된 뒤**에 한다.

### 현재 한계

`mainSequence.py:20-33` 이 설비 개수를 인스턴스 생성으로 정한다.
**경화기 2호기는 주석 처리돼 있어 코드가 아는 경화기는 1대다.**`enums.py:19-28 PostProcStage` 가 공정 순서를 IntEnum으로 고정하고 있다.
둘 다 ② 단계의 이관 대상이다.

---

## M4 — 조회 뷰

**판정** 신규 · **상태** 레퍼런스 완성

### 왜 뷰인가

**Grafana가 업무 로직을 갖지 않게 하기 위해서다.**`SETTLING` 판정이나 반송 대기시간 계산이 패널 쿼리에 들어가면,
정의를 바꿀 때 패널을 전부 고쳐야 하고 패널마다 정의가 달라진다.
뷰가 M4와 M5 사이의 계약이다.

### 19개 뷰 + 함수 1개 + 트리거 1개

**`v_control_menu`** — 제어 화면 서브 메뉴. `group_label` 로 묶고 공정 순서대로.
노드를 늘리면 뱃지가 늘고, 공정을 넣으면 탭이 생긴다 — **메뉴 하드코딩을 없애는 뷰**.

**`v_order_progress`** — 주문 진척. 납기까지 남은 시간, 주문/생산/폐기/완료 수량.
**"납기 임박한 주문이 어디 걸려 있나"** 에 답한다.
⚠️ 완료 = MAIN 으로 들어오되 나가지 않는 랙. 폐기함은 EXIT 로만 들어오므로 제외 — 이 조건 없으면 폐기가 완료로 세어진다 (실제로 겪음)

**`v_plate_usage`** — 라인의 배치 수 / `plate_count`. 빈 플레이트 수 = 투입 가능 여부.

**`v_waiting_for`** — 다음 MAIN 목적지 기준 대기 큐. **치수검사 대기 큐가 이것** (`next_node='INS-01'`).
물리 큐가 아니라 파생 — 경화가 끝난 부품은 사람이 넣지 않아도 나타난다.

**`v_latest_judgement`** — 부품·노드별 유효 판정. 뒤집힌 이력은 `judgement` 원본에.

**`trg_apply_scrap()`** (트리거) — `part_scrap` INSERT 시 `qty_scrapped` 를 자동 갱신.
두 문장을 따로 쓰면 하나만 실행됐을 때 조용히 어긋난다.

**`v_node_order`** — `route` 를 재귀 CTE로 훑어 `step_order` 를 계산한다.
**`edge_kind = 'MAIN'` 만 훑는다.** DETOUR를 포함하면 순환에 빠진다.
`depth < 50` 안전 가드.

**`v_product_display`** — `SETTLING` 파생.

```
status='DONE' AND ready_at > now()  →  display_status = 'SETTLING'
                                       settle_left_s   = 남은 시간
status='DONE' AND ready_at <= now() →  transport_wait_s = 반출 대기시간
```

`transport_wait_s` 가 **순수 반송 대기시간**이다. 건조 시간이 섞이지 않는다.

**`v_node_status`** — 설비 카드용. 노드 + 현재 제품 + 파생 상태 + 진행률.
M5a Repeat 패널의 기본 쿼리.

**`v_rack_load`** — 랙 점유율. 칸 수·만재 칸 수·플레이트 수·부품 수를 함께 낸다.
**총 용량이 남아도 특정 칸이 차면 못 받는다** — `full_slots` 가 그걸 알려준다.

**`v_rack_slot`** — 칸 단위 점유. 사용/여유, 첫번째·마지막 위치, 내용물 목록.

**`v_slot_map`** — 위치 하나하나. 빈 자리도 행으로 나온다.

**`v_retrievable`** — 지금 꺼낼 수 있는 개체만. FIFO는 1번, LIFO는 마지막만.
🔴 **M3b의 이동 후보 산출은 `product_state` 가 아니라 이 뷰를 봐야 한다.**
그러지 않으면 물리적으로 집을 수 없는 위치를 로봇에게 지시하게 된다.

**`next_place(node_id)`** (함수) — 다음에 놓을 (칸, 위치). `count_by_group` 랙은 묶음 단위로 셈다.
M3b가 지시를 만들 때와 M3a가 결과를 기록할 때 **같은 함수**를 쓴다.

**`v_transporter_load`** — 반송 자원 부하. 이 시스템의 핵심 지표.
노드별 담당이라 `node.transporter_id` 조인 한 번. 예전 엣지별 구조에서 필요했던 `DISTINCT` 가 없어졌다.

**`v_unit_content`** — 개체 내용물 요약. 투입/폐기/양품을 나누고
`single_part` 가 혼재 여부 판정을 겸한다.

**`v_unit_summary`** — BATCH 와 PART 를 같은 모양으로. 상위 뷰와 화면이
`unit_kind` 로 분기하지 않게 하기 위한 장치.

**`v_unit_lineage`** — 부품 계보. 어느 배치에서 나왔는지 거슬러 올라간다.
`order_id` 와 함께 보면 "이 부품은 어느 주문의 몇 번째 판에서 나왔나"까지.

**`v_scrap_summary`** — 공정별·파트별·사유별 폐기 수량. 어느 공정이 얼마나 걸러내는가.

**`v_part_progress`** — 파트별 위치·수량. 내용물이 `unit_content` 로 일원화되어
배치와 부품을 구분하지 않고 동작한다.

**`v_output`** — 개체 수와 부품 수를 나란히. 배치 수 = 라인 속도, 부품 수 = 생산량.

⚠️ `v_node_status`·`v_part_progress` 는 `line_id` 로 묶어야 한다. 노드가 두 라인에
속하므로 안 걸면 행이 곱해진다. 실데이터 검증에서 실제로 겪었다.

---

## M5a — Repeat 대시보드

**판정** 신규 · **상태** 미착수

### 책임

설비 카드 격자, 랙 게이지, 반송 자원 패널, 제품 목록.

### 왜 Canvas가 아닌가

Canvas 패널은 도형을 손으로 배치한다. 프린터가 4대에서 6대가 되면
사람이 화면을 다시 그려야 한다. 이 프로젝트의 핵심 요구와 정면 충돌한다.

Repeat 변수(`$node` = `SELECT node_id FROM node WHERE is_active`)에
`Repeat by variable` 을 걸면 노드가 늘 때 패널이 자동으로 늘어난다.

### 한계

레이아웃이 균일 격자로 고정된다. 라인 형상대로 배치할 수 없고,
노드 타입별로 다른 패널을 쓸 수 없으며, 노드별 임계값 차등도 안 된다.
그것들이 필요해지면 M5b다.

### 완료 기준

**YAML에 프린터 2대를 추가하고 `topo_sync --apply` 했을 때
대시보드를 건드리지 않고 카드가 6장이 되는 것.**

### 프론트엔드와의 관계

기존 7탭은 **존치**한다. 대상이 다르다 —
`monitoring` 탭은 *프린터 대수의 상태*, 이 화면은 *제품 개체의 라인 통과 현황*이다.
그리고 4개 탭(`print`/`queue`/`automation`/`automation_manual`)에 조작 기능이 있어
Grafana가 대체할 수 없다.

---

## M5b — 라인 개요

**판정** 신규 · **시기** 10/31 이후

### 책임

`v_node_order` 와 `route` 를 읽어 좌표를 계산하고, 대시보드 JSON의 `gridPos` 를
찍어내 Grafana API로 올린다. 라인 형상대로 배치된 화면.

### 비용

Grafonnet 또는 Python + API. 빌드 파이프라인이 하나 늘고 배포 실패 시 롤백 절차가 필요하다.
M5a가 실물 데이터로 검증된 뒤에 붙인다.

---

## 모듈 간 계약 요약

| 경계 | 계약 | 형태 |
| --- | --- | --- |
| YAML → M1 | `topology.yaml` 스키마 | 파일 |
| M1 → 전체 | `node`(담당 포함), `route`, `transporter`, `line.plate_count` | DB 테이블 |
| M2 → M3a | `Spawn` / `State` / `Moved` / `Split` | `contract.py` |
| M3a → M3b | `product_state.status`, `ready_at` | DB 테이블 |
| M3b → M2b | 반송 지시 (랙 + 칸 번호) | Modbus 레지스터 130·150 — **인코딩 미결** |
| M3a → M4 | `product_state`, `product_event` | DB 테이블 |
| M4 → M5 | 19개 뷰 + 함수 1개 | SQL 뷰 |

---

## 변경 시나리오별 영향 범위

이 표가 분할이 제대로 됐는지 판정하는 기준이다.
●=수정 필요 · ○=설정/데이터만 · ―=무변경

| 변경 | M1 | M2a | M2b | M2c | M3a | M3b | M4 | M5a |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 프린터 4→6대 | ○ | ― | ― | ― | ― | ― | ― | ― |
| 랙 하나 제거 | ○ | ― | ― | ― | ― | ― | ― | ― |
| 로봇암 C 추가 | ○ | ― | ○ | ― | ― | ● | ― | ― |
| 수동 구간을 로봇으로 | ○ | ― | ○ | ― | ― | ― | ― | ― |
| **FDM 라인 추가** | ○ | ― | ― | ● | ― | ― | ― | ― |
| 카메라 모델 교체 | ― | ● | ― | ― | ― | ― | ― | ― |
| 냉각 판정을 센서로 | ○ | ● | ― | ― | ○ | ― | ― | ― |
| 반송 우선순위 변경 | ― | ― | ― | ― | ― | ● | ― | ― |
| 새 지표 추가 | ― | ― | ― | ― | ― | ― | ● | ○ |

**FDM 라인 추가 줄이 이 설계의 핵심 성과다.** 세척과 경화가 통째로 사라지고
서포트 제거가 들어오는데, M1의 YAML 수정과 M2c 어댑터 하나면 된다.
M3a·M3b·M4·M5a는 공정 이름을 모르기 때문에 바뀌지 않는다.

**로봇암 C 추가에서 M3b가 ●인 것**은 담당 구간이 겹칠 때 배정 정책이 필요해서다.
겹치지 않게 나누면 ○로 떨어진다.

---

## 미결 사항

| 항목 | 내용 | 시기 |
| --- | --- | --- |
| **Modbus 랙·칸 인코딩** | `RK-PRT-DONE-01` 을 정수로. 파라미터 배치, 새 명령값. 로봇 측과 합의 필요 | P4 실물 연결 전 |
| **로봇 티칭이 칸 단위인가** | 지시받은 칸이 아닌 곳에 넣으면 이후 위치 정보가 전부 틀어진다.
안 되면 로봇이 실제 넣은 칸을 `Moved` 에 실어 보내는 경로로 | P4 |
| 칸 채움 정책 | `SEQUENTIAL` vs `BALANCED` — 분산하면 반출 선택지가 늘어 M3b가 유연해짐 | 시뮬로 비교 |
| 되주차 플레이트 표시 | `step_order` 기준 1단계에 그려진다. 이벤트 이력의 최대 도달 단계로 보정 가능 | P3 |
| 위탁2 범위 중복 | Grafana 직접 구현이 위탁 과업과 겹치는지 **문서로** 확인 | P3 착수 전 |
| 바구니 회수 · 부족 | 바구니는 이제 꼬리표(`group_id`)일 뿐이라 재고 개념이 없다.
개수 제한이 필요해지면 `line.plate_count` 처럼 숫자 하나로 | 운영 문제 될 때 |
| **`product_state` 비대** | 완료 랙·폐기함의 개체가 계속 남는다. 부품 단위라 하루 수백 행.
종착 노드 도달 시 제거하거나 부분 인덱스 필요 | P3에서 실물 데이터로 재검토 |
| `display_id` 전역 유니크 | 두 라인이 `id_counter` 를 공유해서 성립한다.
라인별 채번으로 바꾸면 UNIQUE 를 `(line_id, display_id)` 로 | FDM 라인 도입 시 |
| 반송 큐 · 예약 | 로봇암 제어 화면의 큐·순서변경·취소. M3b 개조와 함께 `dispatch_queue`  • `to_slot_no` | P5 |
| 부품 ID 표기 | 와이어프레임 `PT-2026-0412-01`(주문 기반) vs `display_id`(공정 기반). 둘 다 파생 가능. 작업자에게 확인 | P3 |
| 알람 | Grafana → alerting / React → `alarm` 테이블 | M5 결정 후 |
| 주문 분할 운영 | 지금은 주문 1 = 배치 1. 수량이 커져 여러 장으로 나누면
장별 수량을 `Spawn.contents` 에 실어 보내면 된다 — 스키마는 이미 대비됨 | 수량 커질 때 |