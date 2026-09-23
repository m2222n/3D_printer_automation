# 개요

PostgreSQL 14+ · 테이블 18 · 컬럼 123 · 뷰 24 · 함수 2 · 트리거 1
*(2026-09-16 실측 — `information_schema` 로 센 값이다. 손으로 세지 않는다)*

## 개념 13개

```
라인이 어떻게 생겼나   노드 · 칸 · 경로 · 채번 · 반송자원
무엇을 만드나          주문 · 파트 · 개체 · 내용물
지금 어디 있나         상태 · 이력
누가 무엇을 판단했나   판정 · 조작 이력
```

```
customer_order   주문      고객 · 납기          주문 : 배치 = 1 : N
      ↓
unit (BATCH)     배치      한 플레이트 분량 · P3-W2      배치 : 부품 = 1 : N
      ↓ Split (부품 분리)
unit (PART)      부품      개별 부품 · P3-W2-S15-C102

플레이트 = line.plate_count 숫자.  바구니·박스 = product_state.group_id 꼬리표.
```

| 그룹 | 테이블 | 누가 채우나 |
| --- | --- | --- |
| 토폴로지 | `line` `node` `node_slot` `route` `id_counter` | M1 — `topology.yaml` 동기화 |
| 반송 자원 | `transporter` `transporter_state` | M1 (정의) · M3b (런타임) |
| 주문 · 파트 | `customer_order` `order_line` `part` | 영업·수주 (외부 입력) |
| 재공품 | `unit` `unit_content` | M3a |
| 상태 · 이력 | `product_state` `product_event` `part_scrap` | M3a |
| 판정 · 조작 | `judgement` `command_log` | M2m (작업자) · 어댑터 |

## 설계 원칙 5가지

1. **토폴로지는 데이터다** — 설비 개수·공정 순서가 코드에 없다
2. **공정 타입에 CHECK 를 걸지 않는다** — FDM 등 확장 대비
3. **위치는 반송 완료로만 확정한다** — 카메라는 추정
4. **삭제하지 않는다** — `is_active = false` 로 비활성화
5. **관측 시스템은 실물을 모방하지 않는다** — 플레이트는 숫자, 바구니는 꼬리표

## 축소 이력

|  | 개념 | 테이블 | 컬럼 | 코드 |
| --- | --- | --- | --- | --- |
| 물리 모방 설계 | 20 | 21 | 131 | topo_sync 450줄 · engine 518줄 |
| **추상화 후** | **13** | **17** | **115** | **295줄 · 293줄** |

뺀 것 — `route_handler`(span 전개) · `unit_alias` · `container` · `node_type` · `customer` · `topology_sync_log` · 예약(`to_slot_no`).

넣은 것 — `judgement` · `command_log` (와이어프레임 3종에서 도출).

---

# 토폴로지

## `line`

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `line_id` | text | PK | `RESIN-1` / `RESIN-1-ASIS` |
| `label` | text | ✓ |  |
| `process_family` | text | ✓ | `SLA` / `FDM` … CHECK 없음 |
| `plate_count` | int | ✓ | 🔴 **보유 빌드플레이트 수 = 동시 진행 배치 수 상한.** 플레이트를 개체로 추적하지 않는다 — 숫자로 충분하다.
넘으면 투입 거부. 프린터가 4대여도 플레이트가 3장이면 3대까지만 돈다 |
| `is_active` | bool | ✓ |  |

## `node` — 설비와 랙

설비와 랙을 하나로. 타입별 공통 속성은 YAML `node_types` 에서 채워 넣는다 — **별도 `node_type` 테이블은 없다.**

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `node_id` | text | PK | `PRT-01` `SEP-01` `SUP-01` `RK-PRE-PRT-01` `EXIT-SCRAP` |
| `node_kind` | text | ✓ | `STATION` / `RACK` — 유일하게 CHECK 를 건다 |
| `node_type` | text | ✓ | `PRINTER` `WASHER` … 라벨. 제약 없음 |
| `label` | text | ✓ |  |
| `capacity` | int | ✓ | 랙이면 `sum(node_slot.capacity)` 자동 계산 |
| `std_cycle_s` | int |  | 진행률 계산용 |
| `id_prefix` | text |  | 채번 접두 `P W S C D B`. NULL 이면 채번 안 함 |
| `post_delay_s` | int | ✓ | 완료 후 반출 가능까지 (건조·냉각). `ready_at` 계산 |
| `slot_access` | text | ✓ | `FIFO`(기본) / `LIFO` / `RANDOM` |
| `slot_fill` | text | ✓ | `SEQUENTIAL`(기본) / `BALANCED` |
| `count_by_group` | bool | ✓ | 트레이 랙 — 묶음(`group_id`) 단위로 용량 계산 |
| `splits_batch` | bool | ✓ | 🔴 배치가 여기서 부품으로 분해된다 (부품 분리대).
배치는 이 노드를 **통과할 수 없다** — `Split` 만 가능. 엔진이 거부한다 |
| `ui_kind` | text | ✓ | 🔴 **조작 화면 종류. 공정 타입이 아니다.**
`BATCH_SPLIT` · `PART_JUDGE` · `MONITOR` · `TRANSPORT`
서포트제거와 치수검사는 둘 다 "부품 하나씩 판정"이므로 **같은 화면**을 쓴다 |
| `group_label` | text |  | 제어 화면 서브 메뉴 이름. 같은 값끼리 한 탭으로 묶인다.
NULL 이면 `label` 을 쓴다 (프린터 4대 → 탭 "프린터", 개별은 "프린터 1호기") |
| `transporter_id` | text | FK | 🔴 **이 노드에서 나가는 이동을 누가 하나.** 엣지별이 아니라 노드별.
엣지별로 달라지는 경우는 폐기뿐이고 폐기는 담당을 두지 않는다. 이걸로 `route_handler` 와 span 전개가 사라졌다 |
| `is_active` | bool | ✓ | DELETE 대신. 과거 이벤트 보존 |
| `draining` | bool | ✓ | 신규 투입 차단. 노드 제거 1단계 |
| `attrs` | jsonb |  | 🆕 노드 속성. `measure: {key,label,unit}` 이면 이 노드가 측정값을 받는다.
🔴 `ui_kind` 로 측정란을 분기하면 공정 타입 분기 금지 위반이라 여기서 데이터로 판단한다.
공차는 여기가 아니라 `part.attrs` (도면에서 온다) |
| `external_ref` | jsonb |  | 바깥에서 뭐라 부르나 — **계통마다 이름이 달라 한 노드가 여러 개를 갖는다.**
`{"printer_serial": "Form4-…", "legacy_target_printer": 1, "legacy_task_unit": "printer-1", "mqtt": "wash_1", "io": "PET#1/DI2"}`
어댑터가 외부 식별자로 `node_id` 를 역조회하는 자리 — GIN 인덱스(`jsonb_path_ops`).
✅ 9/22 `topology.yaml` 에 값 채움(프린터 4 · 세척 2 · 경화 2 · 완료 랙) — 전부 기존 코드에 실재하는 문자열. `io` 는 배선 미확정이라 비움.
🚨 제어가 `'wash'`·`'printer'` 로만 적는 미지정 표식은 노드 이름이 아니라 여기 넣지 않는다 |

## `node_slot` · `route` · `id_counter`

| 테이블 | 컬럼 | 설명 |
| --- | --- | --- |
| `node_slot` | `node_id` `slot_no` `capacity` | 랙의 칸. `slots: [4, 4]` 에서 옴. 칸 수·자리 수 가변 |
| `route` | `line_id` `from_node` `to_node` `priority` `edge_kind` | 공정 경로 = 엣지. `edge_kind` = `MAIN` 진행 · `DETOUR` 되주차 · `EXIT` 폐기. MAIN 만 순서 계산·순환 검사 |
| `id_counter` | `prefix` `next_val` | 접두별 채번. 리셋 없음 → `display_id` 전역 유니크. 박스 번호(`BOX`)도 여기서 |

---

# 반송 자원

| 테이블 | 컬럼 | 설명 |
| --- | --- | --- |
| `transporter` | `transporter_id` `kind` `label` `auto_dispatch` **`attrs`** `is_active` | `ARM-A` `OP-CURE` `ARM-B`. `auto_dispatch=false` 면 지시 안 나감, "작업자 대기" 표시만. 🆕 `attrs.commands` = **수동 제어 화면이 보여줄 명령 목록**(그리퍼 상태·이송·스핀들). 🚨 명령을 코드에 두면 자원이 늘 때 코드를 고쳐야 한다 — `node.attrs` 와 같은 이유로 jsonb 다 |
| `transporter_state` | `transporter_id` `status` `unit_id` `from_node` `to_node` `started_at` `updated_at` | 런타임. `IDLE`/`MOVING`/`ERROR`/`OFFLINE`.
예약(`to_slot_no`)과 반송 큐는 **P5 에서** — M3b 개조 시 `dispatch_queue` 와 함께 |

---

# 주문 · 파트

| 테이블 | 컬럼 | 설명 |
| --- | --- | --- |
| `customer_order` | `order_id` `customer` `due_at` `status` | 고객명은 문자열. 반복 주문이 쌓이면 마스터로. `OPEN`→`IN_PROGRESS`(첫 투입 자동)→`SHIPPED`/`CANCELLED` |
| `order_line` | `order_id` `part_no` `qty` | 주문 품목. `Spawn.contents` 비우면 그대로 배치 내용물로.
주문 없이 Spawn 하면(9/22 현행) `unit_content` 0행 = 내용 미상, Split 때 확정 |
| `part` | `part_no` `name` `revision` `cad_ref` `attrs` `is_active` | **품종** 식별자. `attrs jsonb` 에 공차(`tol_mm`) 등 |

---

# 재공품

## `unit` — 라인을 흐르는 것

배치와 부품이 같은 테이블. **캐리어(플레이트·바구니)는 여기 없다** — 재사용 자산은 개체가 아니다.

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `unit_id` | uuid | PK | 불변 |
| `line_id` | text | ✓ FK |  |
| `order_id` | text | FK | 주문 : 배치 = 1 : N 이음매. 부품은 배치의 것을 물려받는다.
🆕 9/22 **NULL 허용** — 지금은 배치→유닛만 본다. 주문은 추후 붙인다. 없는 주문을 지어 넣지 않는다 |
| `cmd_id` | text | UQ | 🆕 9/22 기존 제어 DB(MariaDB)의 `print_command.cmd_id`. **두 진실을 잇는 유일한 다리.**
생성은 한 방향(`print_command` → `/local/print` 성공 → Spawn → `unit`) · 역방향 쓰기 없음 · BATCH 에만 · 수동 투입은 NULL.
FK 를 못 건다(다른 DB) — UNIQUE 가 같은 CMD 의 이중 Spawn 을 막는다 |
| `unit_kind` | text | ✓ | `BATCH` 프린터~부품 분리 · `PART` 이후 |
| `display_id` | text | ✓ UQ | 공정번호 `P3-W2-S15-C102-D98-B45`. 투입 직후 `U-a1b2c3d4`
과거 이름 검색: `= 'P3' OR LIKE 'P3-%'` (`text_pattern_ops` 인덱스) |
| `parent_unit_id` | uuid | FK | PART 의 출신 배치. CHECK `(PART) = (parent NOT NULL)` |
| `named_at` | text |  | 🔴 마지막으로 이름 받은 노드. 같은 노드에서 두 번 채번 방지 — `unit_alias` 를 대체 |
| `born_at` `consumed_at` | timestamptz |  | `consumed_at` = BATCH 분해 시각. 이후 이력으로만 |

## `unit_content`

"무슨 파트인가"의 유일한 답. BATCH 는 파트당 1행(혼재 2~3행), PART 는 1행 `qty=1`.

| 컬럼 | 설명 |
| --- | --- |
| `unit_id` `part_no` | PK |
| `qty` | 투입 수량. **불변** — 수율 계산에 원본 필요 |
| `qty_scrapped` | **트리거가 갱신.** 호출자는 `part_scrap` INSERT 만. CHECK `0..qty` |

---

# 상태 · 이력

## `product_state` — 지금 라인 위에 있는 것

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `unit_id` | uuid | PK FK |  |
| `node_id` | text | ✓ FK | **`Moved` 만이 바꾼다.** 카메라는 절대 못 바꾼다 |
| `group_id` | text |  | 🔴 **함께 움직이는 묶음 꼬리표.** 바구니·트레이·OK박스가 이것이다.
바구니의 정체는 알 필요 없다 — "이 부품들이 같이 간다"만. `Moved(group_id)` 로 묶음째, `Moved(unit_id, join_group)` 로 합류 |
| `slot_no` `pos_no` | int |  | 칸 · 앞에서 몇 번째(대기열 순번). FIFO 반출 시 뒤 순번을 당긴다.
🔴 UNIQUE 는 **부분 인덱스**다 — `(node_id, slot_no, pos_no) WHERE slot_no IS NOT NULL AND group_id IS NULL`.
묶음은 **한 자리를 공유**한다 — 트레이 랙에서는 자리 하나에 박스 하나이고 박스 안에 부품이 여럿이다 |
| `status` | text | ✓ | `WAIT` `RUN` `DONE` `ERROR` `HOLD`. `SETTLING` 은 뷰 파생 |
| `entered_at` `eta` `updated_at` | timestamptz |  |  |
| `ready_at` | timestamptz |  | 🔴 반출 가능 시각 = 완료 + `post_delay_s`. 상태로 두면 타이머가 생긴다. 값으로 두면 시간이 알아서 흐른다 |

## `product_event` · `part_scrap`

| 테이블 | 컬럼 | 설명 |
| --- | --- | --- |
| `product_event` | `event_id` `ts` `unit_id` `node_id` `status` `duration_s` `ready_at` `source` `confidence` `transporter_id` `msg` | append only. 사이클타임·병목 분석의 원천. `source` 로 어디가 아직 수동인지 본다.
`source` = `CAMERA` `ROBOT` `MANUAL` `ADAPTER` `SIM` **`IO`**(9/22 추가 · 리모트 I/O 접점은 확정이라 `confidence` NULL).
🚨 기존 `automation_log.source`('robot' 'system' 자유 문자열)와 **이름만 같다 — 조인하지 않는다** |
| `part_scrap` | `scrap_id` `ts` `unit_id` `part_no` `qty` `node_id` `reason` `source` `msg` | 폐기. **INSERT 한 문장** — 트리거 `part_scrap_apply` 가 `qty_scrapped` 를 맞춘다.
분해 전 = 배치 내용물 차감 (NG 부품은 `unit` 이 안 생김) · 분해 후 = `EXIT-SCRAP` 이동 |

---

# 판정 · 조작 이력

와이어프레임 3종(서포트제거·치수검사·로봇암)의 우측 패널에서 도출.

## `judgement`

서포트제거의 OK/NG 와 치수검사의 측정값이 **같은 개념** — "어느 부품을 어느 공정에서 누가 어떻게 판정했나."

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `judgement_id` `ts` |  | ✓ | append only |
| `unit_id` `node_id` |  | ✓ FK |  |
| `verdict` | text | ✓ | `OK` / `NG` / `RETEST` |
| `value` | jsonb |  | `{"measured": 12.03, "tol": 0.15}` — 공정마다 다르므로 jsonb |
| `note` | text |  | `서포트 자국 · 표면 결손` |
| `source` | text | ✓ | `AUTO` / `MANUAL`. 🔴 **사람이 자동 판정을 뒤집으면 새 행** — 이력이 남는다. 유효 판정은 `v_latest_judgement` |

## 🆕 `group_close`

묶음 **수동** 마감. 정원이 차서 닫힌 것은 수량으로 알 수 있으므로 행이 생기지 않는다 —
**미달인데 닫을 때만** 한 행.

| 컬럼 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `group_id` | text | PK | 묶음 꼬리표 |
| `node_id` | text | FK | 어디서 닫았나 |
| `closed_at` | timestamptz | ✓ | |
| `actor` | text |  | 누가 |

🔴 `group_id` 를 `BOX-0041-CLOSED` 로 바꾸는 안은 **기각했다** — `group_id` 는 조인 키다
(`product_state_group_idx` · `Moved.join_group`). 값이 바뀌면 마감 전후의 이력이 끊긴다.
⭐ 기존 선례와도 맞는다 — `print_command.allocated_data` 가 식별자를 바꾸지 않고 **옆에 상태를 적는다.**

## `command_log`

사람과 시스템이 내린 명령. `product_event` 는 `unit_id` 필수라 제품과 무관한 조작(모드 전환, 집진 ON)을 못 담는다.

| 컬럼 | 설명 |
| --- | --- |
| `log_id` `ts` `actor` | `SYSTEM` 또는 작업자 ID. 🔴 9/22 `cmd_id`→`log_id` — 기존 `print_command.cmd_id`(작업 지시의 정체성)와 이름 충돌. 형제(`event_id` `scrap_id` `judgement_id`)와도 이쪽이 일관 |
| `kind` | `MODE_CHANGE` `DISPATCH` `JUDGE` `JUDGE_OVERRIDE` `BATCH_DONE` `BOX_CLOSE` `DEVICE` … |
| `target` `payload` `result` | 대상 · jsonb · `OK`/`REJECTED`/`ERROR` |

---

# 뷰 · 함수

뷰가 M4 와 M5 사이의 계약이다. `SETTLING` 판정이나 대기시간 계산이 패널 쿼리에 들어가면 정의를 바꿀 때 패널을 전부 고쳐야 한다.

| 이름 | 용도 | 주의 |
| --- | --- | --- |
| 🆕 `v_node_prev` | 직전 MAIN 노드 | MAIN·활성·같은 라인 세 조건을 한 곳에. 여러 화면이 각자 `route` 를 걸면 갈라진다 |
| 🆕 `v_wip` | 파이프라인 행 = 재공 1건 | 배치는 개체, 부품은 묶음으로 접는다. 접는 기준을 한 번만 정한다 |
| 🆕 `v_inbound_queue` | 이 노드에 들어올 차례 | `v_waiting_for` 를 묶음 1줄로 집계. `ready` = 출처마다 맨 앞(FIFO) |
| 🆕 `v_node_parts` | 부품 + 최신 판정 + 공차 | `part.attrs` 의 공차 키 이름을 화면·API 가 몰라도 되게 여기서 꺼낸다 |
| 🆕 `v_group_at_node` | 묶음 집계 | 작업대 묶음과 랙 박스가 같은 모양이라 뷰 하나로 둘 다. `group_close` LEFT JOIN 으로 `closed` |
| `v_control_menu` | 제어 화면 서브 메뉴 — `group_label` 로 묶고 공정 순서대로 | 🔴 **메뉴를 하드코딩하지 않기 위한 뷰.**
노드를 늘리면 뱃지 숫자가 늘고, 2차 서포트제거 같은 공정을 넣으면 탭이 생긴다 |
| `v_order_progress` | 주문 진척 — 납기 남은 시간, 주문/생산/폐기/완료 | 완료 = MAIN 으로 들어오되 나가지 않는 랙. **폐기함은 EXIT 로만 들어오므로 제외** — 이 조건 없으면 폐기가 완료로 세어진다 (실제로 겪음) |
| `v_plate_usage` | 라인의 배치 수 / `plate_count` | 빈 플레이트 수 = 투입 가능 여부. 프린터 앞단의 진짜 제약일 수 있다 |
| `v_waiting_for` | 다음 MAIN 목적지 기준 대기 큐 | **치수검사 대기 큐가 이것** — `next_node = 'INS-01'`. 물리 큐가 아니라 파생. 사람이 넣지 않아도 나타난다 |
| `v_latest_judgement` | 부품·노드별 유효 판정 | 뒤집힌 이력은 `judgement` 원본에 |
| `v_node_order` | `step_order` 계산 (재귀 CTE) | **MAIN 만.** DETOUR·EXIT 넣으면 순환 |
| `v_product_display` | `SETTLING` 파생, `transport_wait_s` | `transport_wait_s` 는 순수 반송 대기. 건조 시간 안 섞임 |
| `v_unit_content` | 투입/폐기/양품, `single_part` | `single_part` NULL = 혼재. 파트별 사이클타임은 `IS NOT NULL` 만 |
| `v_unit_summary` | BATCH·PART 같은 모양 | 내용물 일원화로 `unit_kind` 분기 없음 |
| `v_unit_lineage` | 부품 → 배치 → 주문 계보 |  |
| `v_node_status` | 설비 카드. M5a 기본 쿼리 | ⚠️ `line_id` 로 묶어야 행이 안 곱해진다. 다중 점유는 활성도 순 대표 상태 |
| `v_slot_map` `v_rack_slot` `v_rack_load` | 자리 하나하나 · 칸 단위 · 랙 점유 | `full_slots` — 총 용량 남아도 칸이 차면 못 받는다 |
| `v_retrievable` | 지금 꺼낼 수 있는 것 (FIFO 1번) | 🔴 M3b 후보 산출은 이 뷰. 안 그러면 집을 수 없는 위치를 지시 |
| `v_transporter_load` | 반송 자원 부하 — 핵심 병목 지표 | 노드별 담당이라 조인 단순. `DISTINCT` 불필요해짐 |
| `v_part_progress` `v_output` `v_scrap_summary` | 파트별 위치 · 개체/부품 수 · 공정별 불량 | 배치·부품 구분 없이 동작 |
| `next_place(node_id)` 함수 | 다음 (칸, 자리). `count_by_group` 랙은 묶음 단위 | M3b 지시와 M3a 기록이 **같은 함수** |
| `trg_apply_scrap()` 트리거 | `part_scrap` → `qty_scrapped` | 폐기 한 문장 |

---

# 와이어프레임 3종 대응

| 화면 | 지원 | 어떻게 |
| --- | --- | --- |
| **부품 분리** NG 는 다음 공정으로 안 넘어감 | ✅ | `Split` 에 OK 만. NG 는 `part_scrap` 으로 배치 차감 — `unit` 이 안 생긴다 |
| **혼재 배치** — 파트마다 다른 NG·다른 사유 | ✅ | `part_scrap` 이 파트별 행. 3종 혼재로 전 구간 검증함 |
| 서브 메뉴가 YAML 을 따름 | ✅ | `v_control_menu` — 공정을 넣으면 탭이 생긴다 |
| 부품별 판정 + 비고 | ✅ | `judgement` |
| **치수검사** 대기 큐 자동 등록 | ✅ | `v_waiting_for` 파생 |
| 측정값 12.03 / ±0.15 | ✅ | `judgement.value` jsonb · 공차는 `part.attrs` |
| 자동 판정 뒤집기 + 이력 | ✅ | append-only `judgement` |
| OK 박스 12개, 여러 플레이트 혼합, 자동 마감 | ✅ | `Moved(join_group=BOX-…)` · `RK-BPD-WAIT` 가 `count_by_group` · 번호는 `id_counter('BOX')` |
| **로봇암** 반송 지시 + 칸 | ✅ | `Moved.slot_no` · `next_place()` |
| 예상 소요 | ✅ | `product_event.duration_s` 구간 평균 — 파생 |
| 반송 큐 · 순서 변경 · 취소 | 🔴 P5 | M3b 데이터. `dispatch_queue`  • 예약 부활 |
| 집진 ON/OFF · 그리퍼 · 원점 복귀 | 🔴 어댑터 | 제어. `command_log` 에 결과만 |
| 인터록 (집진 가동, 스캐너 원점) | DB 밖 | 어댑터 라이브 상태. DB 에 두면 항상 낡다 |
| 알람 | M5 결정 후 | Grafana → alerting / React → `alarm` 테이블 |
| 부품 ID `PT-2026-0412-01` | 결정 필요 | `display_id`(공정 기반) 와 다름. `order_id + 순번` 뷰로 파생 가능. 작업자에게 확인 |

# 주요 제약 · 인덱스

CHECK 9개 · 인덱스 14개(PK 제외) · 트리거 1개.

| 제약 | 무엇을 막나 |
| --- | --- |
| `node` CHECK `node_kind IN ('STATION','RACK')` | 구조적 구분이므로 이것만 건다. **`node_type` · `ui_kind` 에는 CHECK 가 없다** — FDM 타입 추가가 DDL 이 되면 안 된다.
값 검증은 `topo_sync` 게이트가 한다 |
| `unit` CHECK `(unit_kind='PART') = (parent_unit_id IS NOT NULL)` | 부모 없는 부품, 부모 있는 배치 |
| `unit_content` CHECK `0 <= qty_scrapped <= qty` | 투입보다 많은 폐기. 트리거가 초과를 시도하면 여기서 막힐다 |
| `product_state` 부분 UNIQUE | 한 자리에 둘. 단 묶음은 자리 공유 (`group_id IS NULL` 조건) |
| `unit.display_id` UNIQUE + `text_pattern_ops` | 공정번호 중복. 접두 검색(`LIKE 'P3-%'`)을 위한 인덱스 |
| `customer_order` 부분 인덱스 `WHERE status <> 'SHIPPED'` | 미출하 주문만 훑는다 |
| 트리거 `part_scrap_apply` | 폐기 이중 기록. INSERT 한 문장이면 끝난다 |

---

# 알려진 약점

| 항목 | 내용 | 언제 |
| --- | --- | --- |
| `product_state` 비대 | 완료·폐기 개체가 남는다. 종착 도달 시 제거 또는 부분 인덱스 | P3 실물 데이터 |
| 뷰 중첩 | `v_node_status ← v_unit_summary ← v_unit_content` 3단. `v_order_progress` 서브쿼리 5개 | P3 `EXPLAIN ANALYZE` |
| 플레이트 개별 추적 불가 | "3번 플레이트가 휘었다"를 못 한다. 필요하면 `container` 재도입 — 방법은 안다 | 자산 관리 요구 시 |
| 반송 큐 · 예약 | M3b 개조와 함께 `dispatch_queue`, `to_slot_no` | P5 |