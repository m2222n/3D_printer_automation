> 🔄 **2026-09-29 현행화** — 9/11 명세(읽기 10 · 쓰기 5)는 9/21 명세를 거쳐 9/23 에 **18개(읽기 12 · 쓰기 6)** 로 전부 구현됐다. 오류 코드 실명 · ETag 범위 · `LINE_DSN` 503 동작 · psycopg-only · 열린 결정 8건 중 4건 닫힘을 코드 기준으로 고쳤다. 정본은 `docs/juhee/04_API_명세/20260921_API명세.md` + `web-api/app/line/`.

<aside>
🔌

**Base URL** `https://{host}/api/v2` · **인증** JWT Bearer Token (전 경로, 예외 0개)

**응답 형식** `application/json` · 시각은 전부 ISO8601 UTC

**규모** 🔄 읽기 **12** · 쓰기 **6** · WebSocket 0 — 9/23 `20aa72a` 로 18개 전부 라우트 있음. 정본 = `web-api/app/line/routes_read.py` · `routes_write.py` · `schemas.py`(모델 36) · 테스트 `tests/test_line_v2.py` 10건 · 최신 명세 `docs/juhee/04_API_명세/20260921_API명세.md`

</aside>

web-api 에 `/api/v2` 라우터 하나. 읽기는 M4 뷰를 얇게 감싸고, 쓰기는 전부 **이벤트 4개 + 기록 테이블 3개**로만 간다. `product_state` 직접 UPDATE **0건**.

> **표기 규칙** — `(TBD)` 는 원본에 구조가 정의되지 않은 항목이다. 모델 골자에 없는 필드는 추측하지 않는다.
🔴 열린 결정 / 미검증 · 🥇 비용·우선순위가 가장 큰 항목
본 문서의 JSON 은 **응답 모델 골자에서 파생한 예시**다. 필드 이름은 확정, 값과 목록 래퍼 필드명(`nodes` `wip` 등)은 예시다.
> 

---

# 1. 공통 규약

## 1-1. 인증

```
Authorization: Bearer {access_token}
```

| 경로 | 보호 | 근거 |
| --- | --- | --- |
| `/api/v2/**` 전부 | 🔒 JWT | `_is_protected_path` 가 `/api/` 로 시작하면 전부 보호. 새 경로도 자동 |
| 공개 예외 | **0개** | v2 는 로그인 창구가 없다 |
| 헬스체크 | 없음 | v1 `/health` 는 SPA 폴백에 가려 HTML 을 반환한다. v2 는 그 경로를 따라가지 않는다 |

✅ 🔄 **loopback 면제 — 9/22 `1013bab` 로 닫힘.** `jwt_middleware.py:35 LOOPBACK_EXEMPT_PREFIXES = ("/api/v1/",)` — 면제는 v1 만, v2 는 같은 호스트에서도 JWT. (아래는 결정 전 분석)

|  | 면제가 필요한가 | 근거 |
| --- | --- | --- |
| v2 읽기·쓰기 | 🔴 아니다 | 호출자는 브라우저뿐이고 브라우저는 토큰이 있다 |
| v1 의 4경로 | 🟢 필요 | `printer_interface.py:41,70,79,86` 이 토큰 없이 부른다 |

**권고** — `LOOPBACK_EXEMPT_PREFIXES = ("/api/v1/",)` 한 줄로 접두 제한. v1 동작은 그대로이고 v2 만 빠진다.

⇒ **완화** = `actor` 필수 + 모든 쓰기를 `command_log`/`product_event` 에 남긴다.

✅ 🔄 ~~`/docs` `/openapi.json` 은 인증 없이 열린다~~ — 9/22 `1b3af01` `DOCS_PATHS` 를 JWT 뒤로.

## 1-2. 거부 규약

| 상황 | HTTP | 본문 |
| --- | --- | --- |
| 상태 엔진 거부 (FIFO 위반 · 경로 없음 · 정원 초과 …) | **409** | 🔄 `{detail: "<엔진 메시지 원문>", code: "ENGINE_REJECTED"}` (`routes_write.py:34-45 _engine`) |
| 없는 노드 · 개체 · 라인 | 404 | 🔄 엔진 `ValueError` 메시지에 "없는 개체 · 활성 노드가 아님 · 없는 라인 · 없음" 이 있으면 `NOT_FOUND` · R4/R1 `LINE_NOT_FOUND` · R7 `RACK_NOT_FOUND` · R11/W6 `TRANSPORTER_NOT_FOUND` `COMMAND_NOT_FOUND` `MANUAL_TRANSPORTER` |
| 요청 형식 오류 | 422 | FastAPI 기본 + 🔄 `BAD_STATUS`(W3) · `BAD_REF`(W2 unit/group 정확히 하나) · `BAD_VERDICT`(W4) |
| PostgreSQL 미연결 | 503 | 🔄 `LINE_MES_OFF`(`LINE_DSN` 비어 있음) · `LINE_MES_UNAVAILABLE`(`OperationalError`) |
| 🔄 W6 미검증 명령 | 409 | `UNVERIFIED_COMMAND` — `transporter.attrs.commands[].verified` 가 false |

```json
{
  "detail": "경화기에 빈 자리가 없습니다",
  "code": "ENGINE_REJECT"
}
```

🚨 **400 으로 뭉개지 않는다** — "경화기 빈 자리 없음" 과 "필드 누락" 은 작업자가 할 일이 다르다.

⭐ 엔진 메시지는 이미 한국어 완성문이다. API 가 다시 쓰지 않는다.

## 1-3. 공통 쓰기 규약

| 항목 | 규약 |
| --- | --- |
| `actor` | 🚨 **필수.** JWT 가 단일 계정(`admin`)이라 토큰으로는 누가 했는지 알 수 없다 |
| `source` | 🚨 **요청 필드가 아니다.** 이 API 를 통과한 쓰기는 서버가 `MANUAL` 로 고정한다. 사칭할 수 있으면 "어디가 아직 수동인가" 지표가 무너진다 |
| `product_state` | **직접 UPDATE 0건.** 전부 이벤트 4개 또는 기록 테이블 3개를 경유 |
| 응답 | 쓰기 5개 전부 `WriteResult` — 조작 직후 갱신은 이 응답이 해결한다 |

```json
{
  "ok": true,
  "event_ids": [10482],
  "unit_ids": ["3f2b1c8a-0d44-4e91-9a7c-6b0e2f1a8c33"],
  "group_id": "BOX-2026-0918-01",
  "message": "이동 완료",
  "warnings": []
}
```

## 1-4. 목록 응답 · 갱신

- 목록 응답은 `response_model` 에 대응하는 단일 배열 필드를 담는다. **페이지네이션 없음** — 전부 라인/노드 스코프의 유한 집합이다
- 조회 응답에 **`ETag`**를 달고 `If-None-Match` 가 맞으면 **304**. 🔄 **R1 · R3 · R5 만**(폴링 화면) — `max(product_state.updated_at)` + 행 수의 md5(`routes_read.py:40-48`). R2·R9·R10 은 의도적으로 없음. FE `lineApi.ts v2()` 가 304 면 기억한 본문을 돌려준다
- ⚠️ 읽기 뷰는 **전부 `line_id` 로 묶는다.** `RESIN-1-ASIS` 와 `RESIN-1` 이 둘 다 active 라 안 걸면 행이 곱해진다

## 1-5. 이벤트와 기록의 경계

```
이벤트 4개    Spawn · State · Moved · Split           → product_state 를 바꾼다 (엔진이 검증)
직접 INSERT   judgement · command_log · group_close   → 아무것도 안 바꾼다 (기록만)
```

|  | 이벤트 (4개) | 직접 INSERT (3개) |
| --- | --- | --- |
| 무엇 | `Spawn` `State` `Moved` `Split` | `judgement` · `command_log` · `group_close` |
| 바꾸는 것 | **`product_state`** (위치 · 상태 · 채번 · 용량) | 아무것도 안 바꾼다 — 기록만 |
| 검증 | 상태 엔진이 한다 | FK 와 CHECK 뿐 |

경계는 **위치를 바꾸는 것만 이벤트**다. 검증이 두 벌이 되면 규칙이 갈라진다.

🚨 **NG 판정만은 둘이 붙어 있다** — 판정은 기록이고 폐기함으로 가는 것은 이동이라 **한 트랜잭션**으로 묶는다.

```
W1  BEGIN → Split(엔진) → part_scrap INSERT × N → COMMIT
W4  BEGIN → judgement INSERT → (NG면) Moved(엔진) → COMMIT
그 외 단건
```

---

# 2. 화면 정의

화면이 없는 엔드포인트는 만들지 않는다.

|  | 화면 | 필요한 것 | 엔드포인트 |
| --- | --- | --- | --- |
| **S1** | 라인 모니터링 › 설비·반송 | 요약 타일 4 · 반송 상태/큐 · 공정 순서대로 늘어선 랙·설비 · 구간별 담당 | R1 R2 |
| **S2** | 라인 모니터링 › 파이프라인 | 행=재공 1건 · 열=공정 · 셀=완료/현재/미도달 | R3 R4 |
| **S3** | 공정 제어 › 공통 | 서브 탭 목록 — **하드코딩 금지** | R4 |
| **S4** | 공정 제어 › MONITOR | ①투입 대기 큐 ②설비 블록 ③투입·시작·중지·완료 | R1 R5 W2 W3 |
| **S5** | 공정 제어 › BATCH_SPLIT | ①랙 ②칸 ③배치 FIFO 대기열 ④파트별 OK/NG ⑤묶음 | R6 R7 R8 R9 W1 W2 |
| **S6** | 공정 제어 › PART_JUDGE | ①대기 묶음 ②부품별 행+측정값 ③OK/NG ④박스 적재·마감 | R9 R10 W4 W2 W5 |
| 🔄 **S7** | 공정 제어 › BATCH_SPLIT · 내용 미상 배치 | 파트 마스터에서 골라 행 추가 | R12 |
| 🔄 **S8** | 공정 제어 › TRANSPORT (로봇암 수동제어 · `v_control_menu` 밖 합성 탭) | 반송자원 선택 → 명령 카탈로그 → 실행(기록만) | R2 R11 W6 |

🔄 FE 파일 = S1·S2 `LineMonitorPage.tsx` / S3 `ProcessControlPage.tsx` / S4 `MonitorScreen.tsx` / S5·S7 `BatchSplitScreen.tsx` / S6 `PartJudgeScreen.tsx` / S8 `RobotManualScreen.tsx`.

⭐ **R1 을 S1 과 S4 가 같이 쓴다** — 같은 질문("설비가 지금 어떤가")이라 나누지 않는다.

⭐ **요약 타일 4개는 별도 엔드포인트를 두지 않는다** — `nodes` 응답을 세면 나온다.

---

# 3. 읽기 API

## R1 · GET `/lines/{line_id}/nodes` — 노드 현황 조회

`response_model` `NodeListResponse` · 사용 뷰 `v_node_status` + `v_node_order` + `v_rack_slot` · 호출 화면 S1 S4

**Response 200**

```json
{
  "nodes": [
    {
      "node_id": "PRINTER-01",
      "label": "프린터 1호기",
      "node_kind": "MACHINE",
      "node_type": "PRINTER",
      "ui_kind": "MONITOR",
      "group_label": "프린터",
      "step_order": 20,
      "capacity": 1,
      "occupancy": 1,
      "status": "RUN",
      "display_id": "P3-W2",
      "display_ids": ["P3-W2"],
      "part_label": "브래킷 외 2종",
      "part_qty": 18,
      "elapsed_s": 1840,
      "std_cycle_s": 3600,
      "progress_pct": 51,
      "settle_left_s": null,
      "transport_wait_s": null,
      "transporter_id": "ARM-A",
      "attrs": "(TBD)",
      "slots": null
    },
    {
      "node_id": "RACK-CURE-IN",
      "label": "경화기 대기 랙",
      "node_kind": "RACK",
      "node_type": "RACK",
      "ui_kind": null,
      "group_label": "대기 랙",
      "step_order": 55,
      "capacity": 12,
      "occupancy": 5,
      "status": "IDLE",
      "display_id": null,
      "display_ids": ["P3-W2-S15", "P3-W1-S14"],
      "part_label": null,
      "part_qty": 5,
      "elapsed_s": null,
      "std_cycle_s": null,
      "progress_pct": null,
      "settle_left_s": 120,
      "transport_wait_s": 40,
      "transporter_id": "OP-CURE",
      "attrs": "(TBD)",
      "slots": "(TBD)"
    }
  ]
}
```

- `attrs` — `measure` 등 노드 속성 jsonb. 키 구조는 노드 타입별로 다름, 원본 미정의
- `slots[]` — 랙일 때만 포함. 항목 구조는 `v_rack_slot` 스키마 확정 후 보완
- 🚨 **`display_status` 계열은 API 가 만들지 않는다** — `v_product_display` 의 `SETTLING` 파생을 그대로 싣는다
- `settle_left_s`(못 꺼냄)와 `transport_wait_s`(안 옮겨감)를 **둘 다** 내려보낸다. 구분은 화면의 몫이다

## R2 · GET `/lines/{line_id}/transporters` — 반송 자원 조회

`response_model` `TransporterListResponse` · 사용 뷰 `v_transporter_load` · 호출 화면 S1

**Response 200**

```json
{
  "transporters": [
    {
      "transporter_id": "ARM-A",
      "label": "로봇암 A (프린터~세척)",
      "kind": "ROBOT",
      "auto_dispatch": true,
      "status": "BUSY",
      "queued": 3,
      "avg_wait_s": 52,
      "max_wait_s": 180
    },
    {
      "transporter_id": "OP-CURE",
      "label": "작업자 (분리~검사)",
      "kind": "OPERATOR",
      "auto_dispatch": false,
      "status": "IDLE",
      "queued": 0,
      "avg_wait_s": 0,
      "max_wait_s": 0
    }
  ]
}
```

## R3 · GET `/lines/{line_id}/wip` — 재공 파이프라인 조회

`response_model` `WipListResponse` · 사용 뷰 `v_wip` · 호출 화면 S2

**Response 200**

```json
{
  "wip": [
    {
      "ref_kind": "UNIT",
      "ref": "3f2b1c8a-0d44-4e91-9a7c-6b0e2f1a8c33",
      "display_id": "P3-W2",
      "part_label": "브래킷 외 2종",
      "part_qty": 18,
      "node_id": "WASHER-02",
      "node_label": "세척기 2호기",
      "step_order": 40,
      "display_status": "SETTLING",
      "waiting": false
    },
    {
      "ref_kind": "GROUP",
      "ref": "BOX-2026-0918-01",
      "display_id": null,
      "part_label": "힌지",
      "part_qty": 7,
      "node_id": "SUPPORT-REMOVE",
      "node_label": "서포트 제거",
      "step_order": 70,
      "display_status": "WAITING",
      "waiting": true
    }
  ]
}
```

`ref_kind` — `UNIT` 개체 1건(배치 구간) · `GROUP` 묶음 1건(부품 구간).

행 접는 기준(배치=개체 단위, 부품=묶음 단위)은 **`v_wip` 이 정한다.** API 가 하면 화면마다 기준이 갈라진다.

## R4 · GET `/lines/{line_id}/control-menu` — 제어 서브 메뉴 조회

`response_model` `ControlMenuResponse` · 사용 뷰 **`v_control_menu`** · 호출 화면 S3 S2

**Response 200**

```json
{
  "menu": [
    {
      "menu_label": "부품 분리",
      "ui_kind": "BATCH_SPLIT",
      "step_order": 60,
      "node_count": 1,
      "node_ids": ["BATCH-SPLIT"]
    },
    {
      "menu_label": "서포트 제거",
      "ui_kind": "PART_JUDGE",
      "step_order": 70,
      "node_count": 1,
      "node_ids": ["SUPPORT-REMOVE"]
    },
    {
      "menu_label": "경화기",
      "ui_kind": "MONITOR",
      "step_order": 80,
      "node_count": 2,
      "node_ids": ["CURE-01", "CURE-02"]
    }
  ]
}
```

⭐ **서브 메뉴는 `v_control_menu` 가 준다** — 노드를 늘리면 탭이 자동으로 늘고 화면 코드는 안 바뀐다. 화면은 이 응답을 `.map()` 할 뿐이다.

~~프론트가 v2 탭을 감추는 근거도 **이 엔드포인트의 404 / 503** 이다.~~ 🔄 **바뀜** — v2 라우터는 항상 include 되고 `LINE_DSN` 이 비면 **503 `LINE_MES_OFF`**. FE 는 탭을 감추지 않고 **`GET /api/v1/system/config.line_mes`**(= `LINE_DSN` 유무)로 목업↔실 API 를 한 번에 전환한다(`lineApi.ts:39-46` · `95d8560`·`2d2042f`). `line_id` 도 같은 응답에서(`currentLineId()`).

## R5 · GET `/nodes/{node_id}/inbound` — 투입 대기 큐 조회

`response_model` `InboundQueueResponse` · 사용 뷰 `v_inbound_queue` · 호출 화면 S4

**Response 200**

```json
{
  "inbound": [
    {
      "key": "unit:3f2b1c8a",
      "ref_kind": "UNIT",
      "ref": "3f2b1c8a-0d44-4e91-9a7c-6b0e2f1a8c33",
      "label": "P3-W2",
      "qty": 18,
      "from_node": "RACK-WASH-OUT",
      "from_label": "세척기 완료 랙",
      "ready": true,
      "waiting_s": 410
    },
    {
      "key": "group:BOX-2026-0918-01",
      "ref_kind": "GROUP",
      "ref": "BOX-2026-0918-01",
      "label": "박스 01",
      "qty": 7,
      "from_node": "SUPPORT-REMOVE",
      "from_label": "서포트 제거",
      "ready": false,
      "waiting_s": 95
    }
  ]
}
```

`ready` 는 출처별 맨 앞(FIFO)인지 여부로, **뷰가 판정한다.** 묶음은 **1줄**로 본다 — `v_waiting_for` 는 부품 단위지만 화면은 묶음 단위다.

## R6 · GET `/nodes/{node_id}/source-racks` — 직전 출처 랙 목록

`response_model` `RackListResponse` · 사용 뷰 `v_node_prev` + `v_rack_load` · 호출 화면 S5

**Response 200**

```json
{
  "racks": [
    {
      "node_id": "RACK-WASH-OUT",
      "label": "세척기 완료 랙",
      "capacity": 12,
      "occupancy": 5,
      "slot_count": "(TBD)"
    }
  ]
}
```

"직전 MAIN 노드" 조건 3개(MAIN · 활성 · 같은 라인)는 **`v_node_prev` 에 있다.** 행 구조는 원본 모델 골자에 없어 `(TBD)`.

## R7 · GET `/racks/{node_id}/slots` — 랙 칸 목록

`response_model` `SlotListResponse` · 사용 뷰 `v_rack_slot` · 호출 화면 S5

**Response 200**

```json
{
  "slots": [
    { "slot_no": 1, "capacity": 4, "occupancy": 3, "head_display_id": "P3-W2" },
    { "slot_no": 2, "capacity": 4, "occupancy": 0, "head_display_id": null }
  ]
}
```

랙 = 칸 > 자리, **FIFO 대기열**. 순번은 절대 좌표가 아니라 "앞에서 몇 번째"다. 행 구조 `(TBD)`.

## R8 · GET `/racks/{node_id}/slots/{slot_no}/queue` — 칸 FIFO 대기열 조회

`response_model` `SlotQueueResponse` · 사용 뷰 `v_slot_map` + `v_retrievable` + `v_unit_summary` + `unit_content` · 호출 화면 S5

**Response 200**

```json
{
  "queue": [
    {
      "unit_id": "3f2b1c8a-0d44-4e91-9a7c-6b0e2f1a8c33",
      "display_id": "P3-W2",
      "pos_no": 1,
      "retrievable": true,
      "total_qty": 18,
      "kinds": 3,
      "contents": [
        { "part_no": "BRK-1002", "part_name": "브래킷", "qty": 8, "qty_scrapped": 0 },
        { "part_no": "HNG-2041", "part_name": "힌지", "qty": 6, "qty_scrapped": 1 },
        { "part_no": "CAP-3310", "part_name": "캡", "qty": 4, "qty_scrapped": 0 }
      ]
    }
  ]
}
```

🚨 **4개를 조인하지만 계산은 없다** — `retrievable` 은 `v_retrievable` 에 있는 행인지 여부(LEFT JOIN), 파트 구성은 `unit_content` 원본 행이다. **판정 로직을 API 가 다시 쓰지 않는다.**

## R9 · GET `/nodes/{node_id}/groups` — 노드의 묶음 조회

`response_model` `GroupListResponse` · 사용 뷰 `v_group_at_node` · 호출 화면 S5 S6

**Response 200**

```json
{
  "groups": [
    {
      "group_id": "BOX-2026-0918-01",
      "node_id": "SUPPORT-REMOVE",
      "unit_qty": 7,
      "capacity": 12,
      "closed": false,
      "sources": [
        {
          "parent_display_id": "P3-W2",
          "parts": { "BRK-1002": 4, "HNG-2041": 3 }
        }
      ]
    }
  ]
}
```

🥇 **작업대 묶음과 랙 박스가 같은 모양**이라 뷰 하나로 둘 다 덮는다.

`closed` 는 `group_close` LEFT JOIN. 정원이 차서 자동 마감된 경우는 행이 생기지 않는다. 박스 정원은 `node.capacity` 에서 온다 — **하드코딩 아님.**

## R10 · GET `/nodes/{node_id}/parts` — 부품 판정 목록 조회

`response_model` `PartJudgeListResponse` · 사용 뷰 `v_node_parts` · 호출 화면 S6

**Response 200**

```json
{
  "parts": [
    {
      "unit_id": "9c4d7e12-55aa-4b30-8f61-2d7c0b93ae57",
      "display_id": "P3-W2-S15-C102",
      "group_id": "BOX-2026-0918-01",
      "part_no": "BRK-1002",
      "part_name": "브래킷",
      "measure_spec": "(TBD)",
      "tol": "(TBD)",
      "verdict": "OK",
      "value": "(TBD)",
      "judged_at": "2026-09-18T02:14:00Z"
    },
    {
      "unit_id": "b1e0aa73-118f-4c02-9ad4-7f5e6c210d88",
      "display_id": "P3-W2-S15-C103",
      "group_id": "BOX-2026-0918-01",
      "part_no": "HNG-2041",
      "part_name": "힌지",
      "measure_spec": "(TBD)",
      "tol": "(TBD)",
      "verdict": null,
      "value": null,
      "judged_at": null
    }
  ]
}
```

`measure_spec` = `node.attrs.measure` · `tol` = `part.attrs` · `value` = 측정값 jsonb. 🔄 `measure_spec` 은 `{key, label, unit}`(치수검사 `INS-01` = `height_mm`)로 확정, 나머지는 미정의.

부품 행 하나에 **최신 판정 + 측정 스펙 + 공차**가 붙어서 온다. **jsonb 키 이름을 API 가 알면 안 된다.**

## 🔄 R11 · GET `/transporters/{transporter_id}/commands` — 명령 카탈로그 (9/23 추가)

`response_model` `RobotCommandListResponse` · 원천 `transporter.attrs.commands[]` + `attrs.endpoint` · 호출 화면 S8. 404 `TRANSPORTER_NOT_FOUND`.
명령을 코드가 아니라 토폴로지에 둔 이유 = `v_control_menu` 와 같다(자원이 늘어도 코드 무변경). `verified` 플래그가 W6 의 관문.

## 🔄 R12 · GET `/parts?all=` — 부품 마스터 (9/22 추가)

`response_model` `PartListResponse` · 원천 `part` · 호출 화면 S7(내용 미상 배치에 파트 행 추가). `all=true` 면 비활성 포함.

---

# 4. 쓰기 API

## W1 · POST `/units/{unit_id}/split` — 배치 완료 등록 (부품 분리)

번역되는 것 **`Split`** • `part_scrap` INSERT(NG) · 호출 화면 S5

**Request Body**

```json
{
  "node_id": "BATCH-SPLIT",
  "outputs": [
    { "part_no": "BRK-1002", "qty": 8 },
    { "part_no": "HNG-2041", "qty": 5 }
  ],
  "scraps": [
    { "part_no": "HNG-2041", "qty": 1, "reason": "출력 변형" }
  ],
  "group_id": null,
  "actor": "kim.op"
}
```

**Response 200** — `WriteResult`

| 필드 | 규약 |
| --- | --- |
| `outputs` | 🚨 **NG 는 여기 넣지 않는다** — 부품 unit 이 생기면 안 된다 |
| `scraps` | `part_scrap` 으로 수량 차감. `unit` 이 생기지 않는다 |
| `group_id` | null 이면 새 묶음, 값이 있으면 이어 담기. 🔴 **서버 기본값을 정하지 않는다** — 정하면 화면이 못 바꾼다 |

분리 화면은 **부품 ID 를 쓰지 않는다** — 그 시점에 부품은 존재하지 않고 작업자가 손에 든 물건과 매칭할 수도 없다. **파트넘버 × 수량**으로 판정한다.

🔄 **내용 미상 배치**(실물 Spawn 에 `part_type` 이 없어 `unit_content` 0행)는 W1 이 **같은 트랜잭션에서 `part`·`unit_content` 를 먼저 채우고** `warnings` 에 남긴 뒤 `Split` 한다 — 이것이 B6.

## W2 · POST `/moves` — 이동

번역되는 것 **`Moved`** · 호출 화면 S4 투입 · S5 넘기기 · S6 박스 합류

**Request Body**

```json
{
  "group_id": "BOX-2026-0918-01",
  "from_node": "SUPPORT-REMOVE",
  "to_node": "CURE-02",
  "transporter_id": "OP-CURE",
  "slot_no": null,
  "join_group": null,
  "actor": "kim.op"
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `unit_id` · `group_id` | uuid · string | **정확히 하나.** 묶음째 옮기면 부품 N 건이 아니라 **1건** |
| `from_node` / `to_node` | string | 🚨 후보는 **R1 의 다음 MAIN 노드**. 설비 개수 하드코딩 금지 |
| `slot_no` | integer · null | 랙으로 갈 때의 칸 번호 |
| `join_group` | string · null | 도착지에서 합류할 묶음 (예: `BOX-2026-0918-01`) |
| `actor` | string | 필수 |

**Response 200** — `WriteResult` · **오류** `409` FIFO 위반 · 용량 초과 · 경로 없음 / `404` 없는 노드 · 개체

## W3 · POST `/nodes/{node_id}/state` — 설비 상태 변경

번역되는 것 **`State`** · 호출 화면 S4 시작 · 중지 · 완료

**Request Body**

```json
{
  "status": "RUN",
  "duration_s": 900,
  "confidence": null,
  "actor": "kim.op"
}
```

| `status` 값 | 설명 |
| --- | --- |
| `RUN` | 가동 시작 |
| `DONE` | 완료 — `ready_at` 은 엔진이 `post_delay_s` 로 계산 |
| `ERROR` | 이상 |
| `HOLD` | 중지 — 멈춘 것은 꺼낼 수 없으므로 엔진이 `ready_at`·`eta` 를 지운다 |

`duration_s` 는 작업별 가동 시간(초). 없으면 `std_cycle_s`. 기존 `print_command.washing_time` 과 같은 성격이다.

`HOLD` 는 기존 `cell_state.paused`(셀 전체 운전 모드)와 **층이 다르다** — 이쪽은 개체 하나의 상태다.

**Response 200** — `WriteResult`. 🔄 노드에 개체가 없으면 **200 `ok=false`**(엔진이 경고만 남긴다 · 409 아님). `status` 가 넷 밖이면 422 `BAD_STATUS`.

## W4 · POST `/judgements` — 부품 판정

번역되는 것 `judgement` INSERT (+NG 면 **`Moved`** → `EXIT-SCRAP`) · 호출 화면 S6

**Request Body**

```json
{
  "unit_id": "9c4d7e12-55aa-4b30-8f61-2d7c0b93ae57",
  "node_id": "DIM-INSPECT",
  "verdict": "NG",
  "value": { "dim_a": 12.41 },
  "note": "공차 상한 초과",
  "actor": "kim.op"
}
```

| `verdict` 값 | 설명 |
| --- | --- |
| `OK` | 합격 — 다음 랙이 `count_by_group` 이면 이어서 W2 `join_group=BOX-…` |
| `NG` | 불합격 — **W4 안에서 한 트랜잭션**으로 `EXIT-SCRAP` 이동까지 |
| `RETEST` | 재검 |

**Response 200** — `WriteResult`

🚨 **두 번 호출하게 하지 않는다.** 나눠서 클라이언트가 두 번 부르면 중간에 실패했을 때 **판정만 남고 부품이 라인에 남는다.**

판정 뒤집기는 새 행이다. 기존 행을 수정하지 않는다.

🔄 NG 의 목적지는 하드코딩 `EXIT-SCRAP` 이 아니라 **`route` 의 `edge_kind=EXIT` 엣지**에서 찾는다. 없으면 409 — 현 활성 라인 `RESIN-1-ASIS` 엔 EXIT 엣지가 없다(재배치 라인 `RESIN-1` 에만). `verdict` 가 셋 밖이면 422 `BAD_VERDICT`.

## W5 · POST `/commands` — 조작 기록

번역되는 것 `command_log` INSERT (+박스 마감이면 `group_close`) · 호출 화면 S6 박스 수동 마감

**Request Body**

```json
{
  "kind": "GROUP_CLOSE",
  "target": "BOX-2026-0918-01",
  "payload": { "reason": "교대 마감" },
  "actor": "kim.op"
}
```

**Response 200** — `WriteResult`

정원이 차서 자동 마감되는 경우는 수량으로 알 수 있어 행이 생기지 않는다. 🔄 빈 묶음 마감은 409, 이미 마감된 묶음은 `ON CONFLICT` 로 `warnings` 에만.

## 🔄 W6 · POST `/transporters/{transporter_id}/commands/{command_id}` — 로봇 명령 (9/23 절단본)

번역되는 것 `command_log(kind='DEVICE', result='REJECTED')` · 호출 화면 S8 · Body `{actor}`

**10/31 안엔 송신 어댑터를 열지 않는다**(제어권 단일 원칙 · 결정 7). 검사 순서 = 404 `TRANSPORTER_NOT_FOUND` → 404 `MANUAL_TRANSPORTER`(`auto_dispatch=false`) → 404 `COMMAND_NOT_FOUND` → 409 `UNVERIFIED_COMMAND` → 기록 후 **200 `ok=false` "기록됨, 미송신"**. 실행됐다고 답하지 않는다. FE 는 `warnings` 를 그대로 띄운다.

---

# 5. 화면 액션 → 이벤트 매핑

🔴 **`product_state` 를 직접 UPDATE 하는 경로는 0건이다.**

| 화면 액션 | 엔드포인트 | 이벤트 / 테이블 | 비고 |
| --- | --- | --- | --- |
| 배치 완료 등록 | W1 | **`Split`**  • `part_scrap` | 🚨 NG 는 `outputs` 에 넣지 않는다 |
| 서포트 제거대로 넘기기 | W2 | **`Moved(group_id)`** | 묶음째 **1건**. 부품 N 건이 아니다 |
| 경화기 투입 | W2 | **`Moved(group_id, to_node)`** | 🚨 경화기 개수 하드코딩 금지 — 후보는 R1 의 다음 MAIN 노드 |
| 랙 → 설비 투입 | W2 | **`Moved(unit_id, to_node)`** | FIFO 위반은 엔진이 거부(409) |
| 부품 OK | W4 | `judgement` | 다음 랙이 `count_by_group` 이면 이어서 W2 `join_group` |
| 부품 NG | W4 | `judgement`  • **`Moved(→EXIT-SCRAP)`** | 🚨 W4 안에서 한 트랜잭션 |
| 설비 시작 · 완료 | W3 | **`State(RUN`** / **`DONE)`** | `ready_at` 은 엔진이 `post_delay_s` 로 계산 |
| 설비 중지 | W3 | **`State(HOLD)`** | 엔진이 `ready_at`·`eta` 를 지운다. `cell_state.paused` 와 층이 다르다 |
| 가동 시간 입력 | W3 | **`State(RUN, duration_s)`** | 없으면 `std_cycle_s` |
| 박스 수동 마감 | W5 | `command_log`  • **`group_close`** | 자동 마감은 행이 생기지 않는다 |
| 인터록 토글 | 🔴 유보 | – | 데이터원이 없다. 화면 체크박스는 목업 (🔄 9/29 그대로) |
| 집진 ON/OFF · 그리퍼 | 🔄 W6 절단본 | `command_log(DEVICE, REJECTED)` | 카탈로그(R11)에서 고르고 기록만. 송신은 10/31 이후 |

---

# 6. 실시간 — 폴링

## WebSocket 을 만들지 않는 근거

1. **선례가 나쁘다.** 기존 WS 3개 중 **2개가 구독자 0** 이고, 쓰이는 `/api/v1/ws` 는 `?token=` 을 안 붙여 **loopback 이 아니면 close 4401** 이다. 15초 폴링 폴백이 그 고장을 가리고 있다
2. **요구 주기가 1초 미만이 아니다.** 최단이 3초다
3. **조작 직후 갱신은 응답이 해결한다.** 쓰기 5개가 전부 `WriteResult` 를 준다
4. **푸시가 필요해지는 것은 P5** — 작업자 반송 *지시* 가 생길 때가 처음이다

## 화면별 갱신 주기

| 화면 | 주기 | 근거 |
| --- | --- | --- |
| S1 흐름 | 5초 | 설비 진행률은 초 단위로 안 바뀐다 |
| S2 파이프라인 | 15초 | 재공이 공정을 옮기는 빈도 |
| S3 서브 탭 | 진입 시 1회 | 토폴로지는 `topo_sync` 때만 바뀐다 |
| S4 MONITOR | **3초** | 🥇 가장 짧다 — 투입 가능 여부가 남의 조작으로 바뀐다 |
| S5 · S6 | 조작 직후 + 10초 | 한 사람이 붙잡고 하는 화면이라 경쟁이 적다. 🔄 구현은 **조작 직후(tick)만** — 10초 주기 폴링은 넣지 않았다 |

🚨 **폴백이 에러를 삼키지 않게 한다** — 조회 실패를 화면에 **표시**한다. v2 화면은 **마지막 갱신 시각과 실패 배지**를 띄운다. 🔄 `LineMonitorPage.tsx FreshnessBadge` ✅ · `MonitorScreen` 3초 ✅ · S1 5초/S2 15초 ✅ · WebSocket 0 ✅.

만들게 되면 `WS /api/v2/ws?token=<JWT>` — 쿼리 토큰 필수, 실패 시 `close 4401` 을 **화면에 표시한 뒤** 폴링으로 내려간다.

---

# 7. 이 API 가 쓰는 신규 뷰 5개

**판정 기준** — API 가 *계산* 해야 하면 뷰를 추가한다. 단순 조인·필터면 추가하지 않는다. (그래서 R8 은 4개를 조인하지만 새 뷰를 만들지 않았다)

| 뷰 | 왜 필요한가 |
| --- | --- |
| `v_wip` | 파이프라인 행 = 재공 1건. **배치는 개체 단위, 부품은 묶음 단위**로 접는 것이 집계다. API 가 하면 화면마다 기준이 갈라진다 |
| `v_inbound_queue` | `v_waiting_for` 는 부품 단위인데 화면은 묶음 1줄로 본다. 묶음 집계 + 출처별 맨 앞(FIFO) 판정이 계산 |
| `v_node_prev` | "직전 MAIN 노드" 의 조건 3개(MAIN · 활성 · 같은 라인)가 여러 화면에 흩어지면 갈라진다 |
| `v_node_parts` | 부품 행 하나에 **최신 판정 + 측정 스펙 + 공차**가 붙어야 한다. jsonb 키 이름을 API 가 알면 안 된다 |
| `v_group_at_node` | 묶음 = 꼬리표뿐이라 "몇 개 담겼고 어디서 왔나" 가 전부 집계. 🥇 작업대 묶음과 랙 박스가 같은 모양이라 뷰 하나로 둘 다. `group_close` LEFT JOIN 으로 `closed` 동봉 |

⚠️ **전부 `line_id` 로 묶는다.** 🔄 9/23 부터 활성 라인은 하나(`RESIN-1-ASIS`)라 곱해질 일은 없지만 규칙은 유지 — 5개 뷰 전부 `schema.sql` 에 반영됐다(뷰 24개 중 5).

---

# 8. 설계 규칙

| 규칙 | 지금 상태 |
| --- | --- |
| 화면이 안 부르면 만들지 않는다 | 🔄 18개 전부 S1~S8 중 하나가 부른다. 만들지 않은 것 6종은 §9 에 사유와 함께 |
| `response_model` 전부 선언 | 🔄 **18/18**. 기존 v1 은 31/80 |
| `product_state` 직접 쓰기 금지 | **0건**. 전부 이벤트 또는 기록 테이블 |
| 뷰에 있는 계산을 API 가 다시 하지 않는다 | 사용 뷰를 엔드포인트마다 명시. 계산이 필요하면 뷰를 추가(§7) |
| 서브 메뉴 · 개수 · 라벨 하드코딩 금지 | R4 가 `v_control_menu` 만 읽는다. 노드를 늘리면 응답이 자동으로 는다 |
| 경로 등록 순서 | include 를 SPA 폴백보다 앞에. 기존 `/health` 가 그 순서를 어겨 HTML 을 반환한다 |
| WS 를 만들면 토큰 필수 | 지금은 만들지 않는다. 만들 때의 경로는 §6 |

⚠️ 유보 항목이 풀리면 엔드포인트가 늘어난다. **그때도 화면부터 확인한다.**

---

# 9. 만들지 않는 것

| 만들지 않는 것 | 사유 |
| --- | --- |
| `POST /spawns` (신규 배치 투입) | 투입은 **작업 지시** 화면의 일인데 그 화면이 설계 전 스텁이다 |
| 반송 지시 · 큐 순서변경 · 취소 | 확정 와이어프레임에 TRANSPORT 화면이 없다. 반송 *상태* 표시는 S1 이 덮는다. 지시는 **P5** |
| 주문 보드 · 납기(`v_order_progress`) | 뷰는 있으나 **확정 와이어프레임에 주문 화면이 없다** |
| 폐기 집계 · 계보 · 파트별 진척 | 같은 이유. 화면이 생기면 **뷰가 이미 있으므로 엔드포인트만 얹으면 된다** |
| 인터록 조회 | 🔴 데이터원이 DB 에 없다 — 인터록 4항목에 대응하는 코드가 **0건** |
| `GET /api/v2/health` | 부르는 화면이 없다. 🔄 "v2 를 켜나" 의 답은 **`/api/v1/system/config.line_mes`** |

---

# 10. 🔴 열린 결정

| # | 항목 | 무엇이 있어야 닫나 | 안 정하면 |
| --- | --- | --- | --- |
| 1 | **PostgreSQL 위치** | ✅ 🔄 **공장 PC** 확정 — 설치(D7)는 🔴 출근일 미실행. 순서 = `20260922_API개발_전체계획.md §10` | — |
| **2** | **loopback 면제 접두 제한** | ✅ 🔄 **닫힘 9/22** `LOOPBACK_EXEMPT_PREFIXES=("/api/v1/",)` + `/docs` JWT | — |
| 3 | 리모트 I/O = MQTT vs Modbus | 🔴 미결 — PET-2255U 채널 배정 회신. 지금은 카메라 MQTT 가 세척기 `State` 를 낸다 | `State` 를 누가 발행하나가 안 정해진다 |
| 4 | 부품 ID 표기 | 🔴 미결 — 화면은 `display_id`. 작업자와 5분 대화 | R8·R10 의 `display_id` 가 작업자가 보는 번호와 다를 수 있다 |
| 5 | 화면이 보는 `line_id` | ✅ 🔄 **닫힘 9/23** `.env LINE_ID=RESIN-1-ASIS`(실물 경로) → `/system/config.line_id`. 재배치 날 `RESIN-1` 로 | — |
| 6 | 인터록 데이터원 | 🔴 미결 | 화면 체크박스가 영원히 목업 |
| 7 | SQLAlchemy ↔ `StateEngine` 커넥션 경계 | ✅ 🔄 **소멸** — v2 는 psycopg3 + `psycopg_pool` 만(`db.py`). 쓰기는 `with connection() as conn: StateEngine(conn)` 한 트랜잭션 | — |
| 8 | v1 SQLite → PostgreSQL 이식 | P5 그대로 | web-api 가 DBMS 3개를 계속 본다 |

## 와이어프레임에 따라 바뀔 수 있는 자리

| 항목 | 지금 명세 | 상태 |
| --- | --- | --- |
| 혼재 반영 | R8 이 파트별 행, W1 이 파트별 `outputs` | 🟢 **혼재가 기본**이라는 전제는 `unit_content` 와 일치 |
| 묶음 누적 기본 동작 | W1 의 `group_id` 가 null 이면 새 묶음(`G-{배치명}`), 값이 있으면 이어 담기 | 🔄 구현은 명시 전달 그대로 — 화면이 기존 묶음(R9)을 골라 넘긴다 |
| 박스 정원 12 | `node.capacity` 에서 온다 | 🟢 하드코딩 아님 |

---

# 부록 A. 엔드포인트 요약

|  | 메서드 | 경로 | 설명 | 화면 | 뷰 / 이벤트 |
| --- | --- | --- | --- | --- | --- |
| R1 | GET | `/lines/{line_id}/nodes` | 노드 현황 | S1 S4 | `v_node_status` `v_node_order` `v_rack_slot` |
| R2 | GET | `/lines/{line_id}/transporters` | 반송 자원 | S1 | `v_transporter_load` |
| R3 | GET | `/lines/{line_id}/wip` | 재공 파이프라인 | S2 | `v_wip` |
| R4 | GET | `/lines/{line_id}/control-menu` | 제어 서브 메뉴 | S3 S2 | `v_control_menu` |
| R5 | GET | `/nodes/{node_id}/inbound` | 투입 대기 큐 | S4 | `v_inbound_queue` |
| R6 | GET | `/nodes/{node_id}/source-racks` | 직전 출처 랙 | S5 | `v_node_prev` `v_rack_load` |
| R7 | GET | `/racks/{node_id}/slots` | 랙 칸 목록 | S5 | `v_rack_slot` |
| R8 | GET | `/racks/{node_id}/slots/{slot_no}/queue` | 칸 FIFO 대기열 | S5 | `v_slot_map` `v_retrievable` `v_unit_summary` `unit_content` |
| R9 | GET | `/nodes/{node_id}/groups` | 노드의 묶음 | S5 S6 | `v_group_at_node` |
| R10 | GET | `/nodes/{node_id}/parts` | 부품 판정 목록 | S6 | `v_node_parts` |
| W1 | POST | `/units/{unit_id}/split` | 배치 완료 등록 | S5 | `Split`  • `part_scrap` |
| W2 | POST | `/moves` | 이동 | S4 S5 S6 | `Moved` |
| W3 | POST | `/nodes/{node_id}/state` | 설비 상태 변경 | S4 | `State` |
| W4 | POST | `/judgements` | 부품 판정 | S6 | `judgement`  • `Moved` |
| W5 | POST | `/commands` | 조작 기록 | S6 | `command_log`  • `group_close` |
| 🔄 R11 | GET | `/transporters/{transporter_id}/commands` | 명령 카탈로그 | S8 | `transporter.attrs` |
| 🔄 R12 | GET | `/parts?all=` | 부품 마스터 | S7 | `part` |
| 🔄 W6 | POST | `/transporters/{transporter_id}/commands/{command_id}` | 로봇 명령 (기록만) | S8 | `command_log` |

전부 `/api/v2` prefix · 전부 JWT(loopback 면제 없음) · 전부 `response_model` 선언 · WebSocket 0 · ETag = R1·R3·R5. 🔄 **18/18 라우트 있음 (9/23).**

---

# 부록 B. 붙일 위치 (설계 배경)

## B-1. 3안 비교

|  | **A. web-api 에 라우터 추가** | B. 별도 서비스 | C. 기존 라우터 확장 |
| --- | --- | --- | --- |
| DB | 🔴 한 프로세스가 **DBMS 3개** | 🟢 PostgreSQL 만 | 🔴 A 와 같음 |
| 인증 | 🟢 기존 미들웨어 재사용 | 🔴 새로 정해야 (JWT 발급처가 web-api) | 🟢 A 와 같음 |
| 배포 | 🟢 프로세스 그대로 | 🔴 프로세스 +1 · 포트 +1 · NSSM +1 | 🟢 그대로 |
| 기존 80개 영향 | 🟢 0 | 🟢 0 | 🔴 `/api/v1/local` 이 51개에서 더 커진다 |
| 계약 분리 | 🟢 `/api/v2` 로 버전이 갈린다 | 🟢 완전 분리 | 🔴 v1 dict 관행과 섞인다 |

**권고 = A · 근거 셋**

1. **coexistence §3-5 가 이미 그린 그림이다** — *"web-api — HTTP · WS · 인증 · 정적. 두 DB 를 읽기만"*
2. **서버를 늘린 선례가 없다.** `sequence_service` · `bin_picking` 은 HTTP 서버를 **0개** 정의하고 전부 클라이언트다
3. **C 는 v1 의 문제를 물려받는다.** `/automation/*` 27개가 전부 `response_model` 없이 dict 직행이다

## B-2. A 의 비용 셋

| 비용 | 내용 |
| --- | --- |
| 🥇 **DBMS 3개** | web-api 는 이미 **SQLite**(`core/config.py:117`) + **MariaDB**(`local/automation_db.py:23`) 를 본다. v2 를 붙이면 **셋**. 트랜잭션은 안 건너지만 백업·모니터링 절차가 3벌이 된다 |
| loopback 면제 상속 | 기존 미들웨어를 타므로 면제도 물려받는다 — §1-1 |
| 🥇 **인스턴스 3개 중 하나에서만 돈다** | web-api 는 공장 PC · 카카오 VM · 6000 셋에서 돌고 PG 에 닿는 것은 하나뿐 |

| 인스턴스 | v2 라우터 |
| --- | --- |
| **공장 PC** | 🟢 여기서 돈다 (PG 가 같은 머신일 때) |
| 카카오 VM · 6000 | 🔴 PG 에 못 닿으면 **503** |

⇒ ~~`DATABASE_URL_LINE` 이 비면 v2 라우터를 include 하지 않는다~~ 🔄 **실제 구현** — 변수명은 `LINE_DSN`, 라우터는 항상 include, 비면 `db.py` 가 `RuntimeError` → **503 `LINE_MES_OFF`**. 발행기·Spawn 도 같은 변수로 no-op. 카카오·6000 은 `LINE_DSN` 을 비워 둔다.

## B-3. 경로 충돌 — 실측

```
등록 경로 88 · /api/ 80
/api/v2 충돌: 없음
SPA 폴백 규칙: if full_path.startswith("api/") → 404
```

🚨 **등록 순서를 지켜야 한다** — ✅ 🔄 `main.py:200-201` 에서 include, SPA 폴백은 `:210`. 폴백은 `api/`·`docs`·`redoc` 접두를 404 로 돌린다.

## B-4. DBMS 통일 — 측정 결과

**① v2 를 SQLite 로 → 🔴 불가**

```
뷰 19개 중 통과 3 · 실패 16
함수 2개는 시도조차 못 함 (SQLite 에 CREATE FUNCTION 이 없다)
막는 구문 = ::캐스트 34 · timestamptz 14 · uuid 9 · extract(epoch) 8 ·
            DISTINCT ON · LATERAL generate_series · array_agg · PL/pgSQL 트리거
```

M4 를 통째로 다시 쓰는 일이고, 그러면 *"뷰가 M4↔M5 계약"* 이라는 근거가 사라진다. 특히 `next_place()` 를 앱으로 올리면 *"M3b 지시와 M3a 기록이 같은 함수를 쓴다"* 는 요점이 깨진다.

**② v1 을 PostgreSQL 로 → 🟢 기술적으로 싸다. 막는 것은 운영이다**

v1 SQLite 쪽 = ORM 4모델 · 36컬럼 · **FK 0 · 뷰 0 · 트리거 0** · SQLite 전용 SQL **0건**. 종속은 `config.py:117` 한 줄.

막는 것 — **인스턴스가 3대라 이사가 셋** · *"기존 DDL 0건"* 원칙 위반 · 10/31 앞 운영 데이터.

⇒ **v2 만 PG. 통일한다면 방향은 ② 이고 P5 항목이다.**

## B-5. 라이브러리 경계

`StateEngine` 은 **psycopg3 API** 를 쓴다 — `with self.conn.transaction():` 와 `%s` 파라미터.

🔄 **결정 = SQLAlchemy 를 쓰지 않는다.** `web-api/app/line/db.py` 가 `psycopg_pool.ConnectionPool(LINE_DSN, min 1 · max 4, dict_row)` 를 지연 생성하고, 읽기는 `rows(sql, **params)`, 쓰기는 `with connection() as conn: StateEngine(conn).handle(e)` — 같은 커넥션 한 트랜잭션. §10-7 의 중첩 트랜잭션 문제는 생기지 않는다.

## B-6. ⭐ 이 결정이 PG 위치를 확정시킨다

v2 라우터가 web-api 안에 있다 ⇒ web-api 프로세스가 PG 에 직접 커넥션을 연다 ⇒ web-api 는 공장 PC 에서 돌므로 **PG 도 공장 PC 에 두는 것이 자연스럽다.** 🔄 **확정(9/22 결정 6)** — 레이아웃 변경 출근일에 설치. `sequence_service` 도 같은 `LINE_DSN`(`../web-api/.env` 공유)으로 B3·B5 를 발행한다.

다른 머신에 두면 DB 커넥션이 인터넷을 건너고, 끊기면 **관측이 아니라 제어 프로세스가 느려진다.**

<aside>
📌

*"이 API 를 web-api 에 붙이는 결정은 PostgreSQL 을 공장 PC 에 두는 결정과 한 몸이다. PG 를 다른 머신에 두기로 하면 A 는 재검토 대상이 된다."*

</aside>