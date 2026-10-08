-- ============================================================
--  공정 자동화 모니터링 스키마 (P0)
--  PostgreSQL 14+ · 테이블 18 · 컬럼 122 · 뷰 24 · 함수 2 · 트리거 1
--
--  ⚠️ 위 숫자는 손으로 세지 않는다. 바꿨으면 아래로 확인할 것.
--     psql -f schema.sql && psql -c "
--       SELECT (SELECT count(*) FROM information_schema.tables
--                WHERE table_schema='public' AND table_type='BASE TABLE') AS tables,
--              (SELECT count(*) FROM information_schema.views
--                WHERE table_schema='public') AS views"
--
--  개념 13개
--    라인이 어떻게 생겼나   노드 · 칸 · 경로 · 채번 · 반송자원
--    무엇을 만드나          주문 · 파트 · 개체 · 내용물
--    지금 어디 있나         상태 · 이력
--    누가 무엇을 판단했나   판정 · 조작 이력
--
--  설계 원칙
--   1. 토폴로지는 데이터다 — 설비 개수/구성이 코드에 없다
--   2. 공정 타입에 CHECK 를 걸지 않는다 (FDM 등 확장 대비)
--   3. 위치는 반송 완료로만 확정한다 (카메라는 추정)
--   4. 삭제하지 않는다 — is_active=false 로 비활성화
--   5. 관측 시스템은 실물을 모방하지 않는다 — 플레이트는 숫자, 바구니는 꼬리표
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ============================================================
--  M1. 토폴로지
-- ============================================================

CREATE TABLE line (
  line_id        text PRIMARY KEY,
  label          text NOT NULL,
  process_family text NOT NULL,             -- SLA | FDM | ...  제약 걸지 않음
  -- 보유 빌드플레이트 수. 동시에 라인에 있을 수 있는 배치 수의 상한이다.
  -- 플레이트는 재사용 자산이라 개체로 추적하지 않는다 — 숫자로 충분하다.
  plate_count    int  NOT NULL DEFAULT 999,
  is_active      boolean NOT NULL DEFAULT true
);

-- 반송 자원. node 가 참조하므로 먼저 만든다.
CREATE TABLE transporter (
  transporter_id text PRIMARY KEY,
  kind           text NOT NULL,             -- ROBOT_ARM | OPERATOR | CONVEYOR
  label          text NOT NULL,
  auto_dispatch  boolean NOT NULL,          -- false 면 "작업자 대기" 표시만
  -- 반송 자원 속성. node.attrs 와 같은 이유로 컬럼이 아니라 jsonb 다.
  --   commands: [...]  수동 제어 화면이 보여줄 명령 목록 (그리퍼 상태 · 이송 · 스핀들)
  -- 🚨 명령을 코드에 두면 자원이 늘 때 코드를 고쳐야 한다 — v_control_menu 와 같은 원칙.
  attrs          jsonb,
  is_active      boolean NOT NULL DEFAULT true
);

-- 설비와 랙을 하나로. 랙은 "가공하지 않고 용량이 큰 노드".
-- 타입별 공통 속성은 YAML node_types 에서 채워 넣는다 — 별도 테이블은 두지 않는다.
CREATE TABLE node (
  node_id        text PRIMARY KEY,
  node_kind      text NOT NULL CHECK (node_kind IN ('STATION','RACK')),
  node_type      text NOT NULL,             -- PRINTER | WASHER | ... 라벨. 제약 없음
  label          text NOT NULL,
  capacity       int  NOT NULL DEFAULT 1,   -- 랙이면 sum(node_slot.capacity) 로 계산
  std_cycle_s    int,
  id_prefix      text,                      -- 채번 접두. NULL 이면 채번하지 않음
  post_delay_s   int  NOT NULL DEFAULT 0,   -- 완료 후 반출 가능까지 대기 (건조·냉각)
  slot_access    text NOT NULL DEFAULT 'FIFO',        -- FIFO | LIFO | RANDOM
  slot_fill      text NOT NULL DEFAULT 'SEQUENTIAL',  -- SEQUENTIAL | BALANCED
  count_by_group boolean NOT NULL DEFAULT false,      -- 트레이 랙: 묶음 단위로 용량 계산
  splits_batch   boolean NOT NULL DEFAULT false,      -- 배치가 여기서 부품으로 분해된다
  -- 이 노드를 어떤 화면으로 조작하는가. 공정 타입이 아니라 화면 종류다 —
  -- 서포트제거와 치수검사는 둘 다 "부품 하나씩 판정"이라 같은 화면을 쓴다.
  --   BATCH_SPLIT  랙>칸>배치 FIFO → 파트별 수량 → Split
  --   PART_JUDGE   대기 부품 목록 → 하나씩 OK/NG
  --   MONITOR      관측 + 상태 수동 입력
  --   TRANSPORT    반송 지시 (반송 자원 화면)
  ui_kind        text NOT NULL DEFAULT 'MONITOR',
  -- 제어 화면의 서브 메뉴 이름. 같은 값끼리 한 탭으로 묶인다.
  -- NULL 이면 label 을 쓴다 (프린터 4대 → 탭 "프린터", 개별 라벨은 "ShrewdStork" 같은 실제 프린터 이름)
  group_label    text,
  -- 이 노드에서 나가는 이동을 누가 하나. 엣지별이 아니라 노드별이다 —
  -- 엣지별로 달라지는 경우는 폐기뿐이고 폐기는 담당을 두지 않는다.
  transporter_id text REFERENCES transporter(transporter_id),
  -- 노드 속성. 공정 타입마다 다른 것을 컬럼으로 두면 타입이 늘 때마다 DDL 이 된다.
  --   measure: {key, label, unit}   이 노드가 측정값을 받는다 (치수검사)
  -- 🔴 ui_kind 로 "측정란을 띄운다" 를 분기하면 공정 타입 분기 금지 원칙 위반이다.
  --    화면은 attrs.measure 가 있으면 띄운다 — 공정 타입을 모른 채로 동작한다.
  -- 공차는 여기가 아니라 part.attrs 다 — 도면에서 오고 설비가 바뀌어도 안 바뀐다.
  attrs          jsonb,
  -- 바깥에서 이 노드를 뭐라 부르나. 어댑터가 외부 식별자로 node_id 를 역조회하는 자리다.
  -- 🚨 부르는 이름이 계통마다 다르다 — 한 노드가 여러 개를 동시에 갖는다.
  --   {"printer_serial": "Form4-<시리얼>",  -- Formlabs 클라우드 (A)
  --    "legacy_target_printer": 1,              -- print_command.target_printer (B)
  --    "legacy_task_unit": "wash",              -- RobotTask.to_unit 이 쓰는 이름 (B)
  --    "mqtt": "wash_1",                        -- 비전 카메라 device_type/device_id
  --    "io": "PET#1/DI2"}                       -- 리모트 I/O 접점
  -- 실측 대응: printer-1..4 → PRT-01..04 · wash-1,2 → WSH-01,02 · cure-1 → CUR-01
  --            output → @DONE 그룹의 완료 랙
  -- attrs 와 나눠 둔 이유 = 역조회 경로가 실제로 생긴다 (M2c 가 시리얼을 받아 노드를 찾는다).
  -- ponytail: 매핑 테이블 대신 컬럼 하나. 노드 18개라 어댑터 기동 시 dict 로 한 번 읽으면
  --   끝이다. 종류가 늘어 역방향 조회에 제약(UNIQUE)이 필요해지면 node_external_id
  --   테이블로 승급한다.
  -- 같은 사실이 지금 PRINTER_SERIAL_MAP(코드 상수)과 .env 두 곳에 흩어져 있다 —
  -- 토폴로지 한 곳으로 모으는 자리이지만 값 이관은 별건이다.
  external_ref   jsonb,
  is_active      boolean NOT NULL DEFAULT true,
  draining       boolean NOT NULL DEFAULT false       -- 신규 투입 차단, 재고만 소진
);
-- 역조회용. 포함 연산자(@>)를 쓰므로 jsonb_path_ops 가 작고 빠르다.
--   SELECT node_id FROM node WHERE external_ref @> '{"serial":"Form4-..."}'
CREATE INDEX node_external_ref_idx ON node USING gin (external_ref jsonb_path_ops);

CREATE TABLE node_slot (
  node_id  text NOT NULL REFERENCES node(node_id) ON DELETE CASCADE,
  slot_no  int  NOT NULL CHECK (slot_no > 0),
  capacity int  NOT NULL CHECK (capacity > 0),
  PRIMARY KEY (node_id, slot_no)
);

CREATE TABLE route (
  line_id   text NOT NULL REFERENCES line(line_id),
  from_node text NOT NULL REFERENCES node(node_id),
  to_node   text NOT NULL REFERENCES node(node_id),
  priority  int  NOT NULL DEFAULT 0,
  -- MAIN 공정 진행 · DETOUR 되주차/재작업 · EXIT 폐기
  -- MAIN 만 순서 계산과 순환 검사의 대상.
  edge_kind text NOT NULL DEFAULT 'MAIN',
  PRIMARY KEY (line_id, from_node, to_node)
);
CREATE INDEX route_from_idx ON route (line_id, from_node);

-- 채번 카운터. 접두별. 리셋하지 않고 계속 증가 → display_id 전역 유니크.
CREATE TABLE id_counter (
  prefix   text   PRIMARY KEY,
  next_val bigint NOT NULL DEFAULT 1
);

CREATE TABLE transporter_state (
  transporter_id text PRIMARY KEY REFERENCES transporter(transporter_id),
  status         text NOT NULL DEFAULT 'IDLE',  -- IDLE | MOVING | ERROR | OFFLINE
  unit_id        uuid,
  from_node      text,
  to_node        text,
  started_at     timestamptz,
  updated_at     timestamptz NOT NULL DEFAULT now()
);

-- ============================================================
--  주문 · 파트
-- ============================================================

-- order 는 SQL 예약어라 customer_order.
CREATE TABLE customer_order (
  order_id text PRIMARY KEY,
  customer text NOT NULL,                   -- 고객명. 마스터는 반복 주문이 쌓이면 그때
  due_at   timestamptz,
  status   text NOT NULL DEFAULT 'OPEN'     -- OPEN | IN_PROGRESS | SHIPPED | CANCELLED
);
CREATE INDEX customer_order_due_idx ON customer_order (due_at) WHERE status <> 'SHIPPED';

CREATE TABLE part (
  part_no   text PRIMARY KEY,               -- 품종 식별자. 같은 모양이면 공유
  name      text NOT NULL,
  revision  text,
  cad_ref   text,
  attrs     jsonb,
  is_active boolean NOT NULL DEFAULT true
);

CREATE TABLE order_line (
  order_id text NOT NULL REFERENCES customer_order(order_id) ON DELETE CASCADE,
  part_no  text NOT NULL REFERENCES part(part_no),
  qty      int  NOT NULL CHECK (qty > 0),
  PRIMARY KEY (order_id, part_no)
);

-- ============================================================
--  재공품
-- ============================================================

-- 라인을 흐르는 것. 배치(플레이트 한 장 분량)와 부품이 같은 테이블이다.
--   BATCH  프린터 ~ 부품 분리. 한 번의 출력으로 나온 묶음
--   PART   부품 분리 이후의 개별 부품
-- 주문 : 배치 = 1 : N,  배치 : 부품 = 1 : N.
CREATE TABLE unit (
  unit_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  line_id        text NOT NULL REFERENCES line(line_id),
  order_id       text REFERENCES customer_order(order_id),
  -- 기존 제어 DB(B: MariaDB automation)의 print_command.cmd_id. 개념이 정확히 같아
  -- 기존 이름을 그대로 쓴다. 두 진실을 잇는 유일한 다리다.
  --   print_command = 지시(제어)의 진실   ← sequence_service 만 쓴다
  --   unit          = 개체(관측)의 진실   ← state_engine 만 쓴다
  -- 🚨 생성은 한 방향뿐이다: print_command INSERT → Spawn 발행 → unit 생성.
  --    역방향 쓰기는 없다(관측이 제어를 판정하지 않는다).
  -- 🔴 다리는 BATCH 에만 있다 — 분해로 태어난 PART 는 parent_unit_id 로 상속한다.
  --    수동 투입 · 시뮬레이터는 NULL 이다. 없는 값을 지어내지 않는다.
  -- FK 를 걸지 않는 이유 = 다른 DB 의 다른 엔진에 있는 테이블이다.
  cmd_id         text UNIQUE,
  unit_kind      text NOT NULL DEFAULT 'BATCH',
  display_id     text NOT NULL UNIQUE,      -- 'P3-W2' → 'P3-W2-S15-C102-D98-B45'
  parent_unit_id uuid REFERENCES unit(unit_id),
  -- 마지막으로 이름을 받은 노드. 같은 노드에서 두 번 채번하지 않기 위한 표식.
  -- (분해로 태어난 부품이 부품 분리대를 떠날 때 S 를 또 받는 것을 막는다)
  named_at       text,
  born_at        timestamptz NOT NULL DEFAULT now(),
  consumed_at    timestamptz,               -- BATCH 가 분해된 시각
  CHECK (unit_kind IN ('BATCH','PART')),
  CHECK ((unit_kind = 'PART') = (parent_unit_id IS NOT NULL))
);
CREATE INDEX unit_parent_idx ON unit (parent_unit_id);
CREATE INDEX unit_order_idx  ON unit (order_id);
-- 과거 이름으로 검색: display_id = 'P3' OR display_id LIKE 'P3-%'
CREATE INDEX unit_display_prefix_idx ON unit (display_id text_pattern_ops);

-- "무슨 파트인가"의 유일한 답. BATCH 는 파트당 한 행, PART 는 한 행 qty=1.
CREATE TABLE unit_content (
  unit_id      uuid NOT NULL REFERENCES unit(unit_id) ON DELETE CASCADE,
  part_no      text NOT NULL REFERENCES part(part_no),
  qty          int  NOT NULL CHECK (qty > 0),        -- 투입 수량. 불변
  qty_scrapped int  NOT NULL DEFAULT 0,              -- 트리거가 갱신
  PRIMARY KEY (unit_id, part_no),
  CHECK (qty_scrapped BETWEEN 0 AND qty)
);

-- ============================================================
--  M3a. 상태 · 이력
-- ============================================================

CREATE TABLE product_state (
  unit_id    uuid PRIMARY KEY REFERENCES unit(unit_id),
  node_id    text NOT NULL REFERENCES node(node_id),  -- Moved 만이 바꾼다
  -- 함께 움직이는 묶음 꼬리표. 바구니·트레이가 이것이다.
  -- 바구니의 정체는 알 필요가 없고 "이 부품들이 같이 간다"만 알면 된다.
  group_id   text,
  slot_no    int,
  pos_no     int,                           -- 칸 안에서 앞에서 몇 번째 (대기열 순번)
  status     text NOT NULL,                 -- WAIT | RUN | DONE | ERROR | HOLD
  entered_at timestamptz NOT NULL,
  eta        timestamptz,
  ready_at   timestamptz,                   -- 반출 가능 시각 = 완료 + post_delay_s
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX product_state_node_idx  ON product_state (node_id);
CREATE INDEX product_state_group_idx ON product_state (group_id) WHERE group_id IS NOT NULL;
-- 한 자리에 두 개가 못 들어간다.
-- 단, 묶음(group_id)이 있는 개체는 같은 묶음이 한 자리를 공유한다 —
-- 트레이 랙에서는 자리 하나에 박스 하나이고 박스 안에 부품이 여럿이다.
CREATE UNIQUE INDEX product_state_pos_uq
  ON product_state (node_id, slot_no, pos_no) WHERE slot_no IS NOT NULL AND group_id IS NULL;

CREATE TABLE product_event (
  event_id       bigserial PRIMARY KEY,
  ts             timestamptz NOT NULL DEFAULT now(),
  unit_id        uuid NOT NULL REFERENCES unit(unit_id),
  node_id        text REFERENCES node(node_id),
  status         text,
  duration_s     int,
  ready_at       timestamptz,               -- 이력에서 SETTLING 복원용
  -- CAMERA | ROBOT | MANUAL | ADAPTER | SIM | IO
  -- 🚨 기존 automation_log.source(자유 문자열 'robot' 'system')와 이름만 같다 — 조인하지 않는다.
  -- IO = 리모트 I/O 접점. 추정이 아니라 확정이므로 confidence 는 NULL 로 둔다.
  source         text NOT NULL,
  confidence     real,
  transporter_id text,
  msg            text
);
CREATE INDEX product_event_ts_idx   ON product_event (ts DESC);
CREATE INDEX product_event_unit_idx ON product_event (unit_id, ts);

CREATE TABLE part_scrap (
  scrap_id bigserial PRIMARY KEY,
  ts       timestamptz NOT NULL DEFAULT now(),
  unit_id  uuid NOT NULL REFERENCES unit(unit_id),
  part_no  text NOT NULL REFERENCES part(part_no),
  qty      int  NOT NULL CHECK (qty > 0),
  node_id  text REFERENCES node(node_id),
  reason   text NOT NULL,
  source   text NOT NULL,
  msg      text
);
CREATE INDEX part_scrap_unit_idx ON part_scrap (unit_id);

-- 판정. 서포트제거의 OK/NG 와 치수검사의 측정값이 같은 개념이다 —
-- "어느 부품을 어느 공정에서 누가 어떻게 판정했나."
-- append only. 사람이 자동 판정을 뒤집으면 새 행이 생기고, 최신 것이 유효하다.
CREATE TABLE judgement (
  judgement_id bigserial PRIMARY KEY,
  ts           timestamptz NOT NULL DEFAULT now(),
  unit_id      uuid NOT NULL REFERENCES unit(unit_id),
  node_id      text NOT NULL REFERENCES node(node_id),
  verdict      text NOT NULL,               -- OK | NG | RETEST
  value        jsonb,                       -- {"measured": 12.03, "tol": 0.15} 등 공정마다 다름
  note         text,                        -- '서포트 자국 · 표면 결손'
  source       text NOT NULL                -- AUTO | MANUAL
);
CREATE INDEX judgement_unit_idx ON judgement (unit_id, ts DESC);

-- 조작 이력. 사람과 시스템이 내린 명령 — 모드 전환, 반출 지시, 박스 마감, 설비 명령.
-- product_event 는 제품 이력이라 unit_id 가 필수다. 여기는 제품과 무관한 조작도 담는다.
CREATE TABLE command_log (
  -- 🔴 cmd_id 가 아니라 log_id 다. 기존 운영 DB(B)의 print_command.cmd_id 가
  --    "작업 지시 하나"라는 정체성을 갖고 automation_log.cmd_id 가 그것을 참조한다.
  --    같은 이름 · 다른 뜻이 한 시스템에 있으면 읽는 사람이 조인하려 든다.
  --    형제(event_id · scrap_id · judgement_id)와도 이 쪽이 일관된다.
  log_id  bigserial PRIMARY KEY,
  ts      timestamptz NOT NULL DEFAULT now(),
  actor   text NOT NULL,                    -- 'SYSTEM' | 작업자 ID
  kind    text NOT NULL,                    -- MODE_CHANGE | DISPATCH | JUDGE | BOX_CLOSE | DEVICE ...
  target  text,                             -- node_id / transporter_id / unit_id
  payload jsonb,
  result  text                              -- OK | REJECTED | ERROR
);
CREATE INDEX command_log_ts_idx ON command_log (ts DESC);

-- 묶음 수동 마감. 정원이 차서 자동 마감되는 경우는 수량으로 알 수 있으므로 행이 생기지 않는다.
-- 미달인데 닫을 때만 한 행.
-- 🔴 group_id 를 'BOX-0041-CLOSED' 로 바꾸는 안은 기각했다 —
--    group_id 는 조인 키다(product_state_group_idx · Moved.join_group).
--    값이 바뀌면 마감 전후의 이력이 끊긴다.
-- 기존 선례와도 맞는다 — print_command.allocated_data 가 식별자를 바꾸지 않고 옆에 상태를 적는다.
CREATE TABLE group_close (
  group_id  text PRIMARY KEY,
  node_id   text REFERENCES node(node_id),
  closed_at timestamptz NOT NULL DEFAULT now(),
  actor     text
);

-- 폐기 기록을 한 문장으로. 사유만 남기면 수량은 트리거가 맞춘다.
CREATE FUNCTION trg_apply_scrap() RETURNS trigger AS $$
BEGIN
  UPDATE unit_content SET qty_scrapped = qty_scrapped + NEW.qty
   WHERE unit_id = NEW.unit_id AND part_no = NEW.part_no;
  IF NOT FOUND THEN
    RAISE EXCEPTION '내용물에 없는 파트: unit=% part=%', NEW.unit_id, NEW.part_no;
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER part_scrap_apply AFTER INSERT ON part_scrap
  FOR EACH ROW EXECUTE FUNCTION trg_apply_scrap();

-- ============================================================
--  M4. 뷰
-- ============================================================

CREATE VIEW v_node_order AS
WITH RECURSIVE walk(line_id, node_id, depth) AS (
  SELECT r.line_id, n.node_id, 0
    FROM node n JOIN route r ON r.from_node = n.node_id AND r.edge_kind = 'MAIN'
   WHERE n.is_active AND NOT EXISTS (
     SELECT 1 FROM route r2 JOIN node p ON p.node_id = r2.from_node AND p.is_active
      WHERE r2.to_node = n.node_id AND r2.line_id = r.line_id AND r2.edge_kind = 'MAIN')
  UNION ALL
  SELECT w.line_id, r.to_node, w.depth + 1
    FROM walk w
    JOIN route r ON r.from_node = w.node_id AND r.line_id = w.line_id AND r.edge_kind = 'MAIN'
    JOIN node n ON n.node_id = r.to_node AND n.is_active
   WHERE w.depth < 50
)
SELECT line_id, node_id, max(depth) AS step_order FROM walk GROUP BY line_id, node_id;

CREATE VIEW v_product_display AS
SELECT ps.*,
       CASE WHEN ps.status = 'DONE' AND ps.ready_at > now() THEN 'SETTLING'
            ELSE ps.status END                                        AS display_status,
       CASE WHEN ps.status = 'DONE' AND ps.ready_at > now()
            THEN extract(epoch FROM (ps.ready_at - now()))::int END    AS settle_left_s,
       CASE WHEN ps.status = 'DONE' AND ps.ready_at <= now()
            THEN extract(epoch FROM (now() - ps.ready_at))::int END    AS transport_wait_s
  FROM product_state ps;

CREATE VIEW v_unit_content AS
SELECT u.unit_id,
       count(c.part_no)                                          AS kinds,
       coalesce(sum(c.qty - c.qty_scrapped), 0)::int             AS total_qty,
       coalesce(sum(c.qty), 0)::int                              AS loaded_qty,
       coalesce(sum(c.qty_scrapped), 0)::int                     AS scrapped_qty,
       string_agg(c.part_no || '×' || (c.qty - c.qty_scrapped), ', ' ORDER BY c.part_no) AS mix,
       CASE WHEN count(c.part_no) = 1 THEN min(c.part_no) END    AS single_part
  FROM unit u LEFT JOIN unit_content c USING (unit_id)
 GROUP BY u.unit_id;

CREATE VIEW v_unit_summary AS
SELECT u.unit_id, u.unit_kind, u.line_id, u.order_id, u.display_id, u.parent_unit_id,
       vc.single_part,
       CASE WHEN vc.kinds = 1 THEN vc.single_part
            WHEN vc.kinds > 1 THEN '혼재 ' || vc.kinds || '종' END  AS part_label,
       coalesce(vc.total_qty, 0)::int                              AS part_qty,
       vc.mix
  FROM unit u LEFT JOIN v_unit_content vc USING (unit_id)
 WHERE u.consumed_at IS NULL;

CREATE VIEW v_unit_lineage AS
SELECT c.unit_id, c.display_id, cc.part_no, c.order_id,
       p.display_id AS batch_display_id, p.born_at AS batch_born_at, p.consumed_at AS split_at
  FROM unit c
  LEFT JOIN unit_content cc USING (unit_id)
  LEFT JOIN unit p ON p.unit_id = c.parent_unit_id
 WHERE c.unit_kind = 'PART';

-- 다음에 놓을 자리. M3b 지시와 M3a 기록이 같은 함수를 쓴다.
CREATE FUNCTION next_place(p_node text)
RETURNS TABLE (slot_no int, pos_no int) AS $$
  WITH occ AS (
    SELECT sl.slot_no, sl.capacity,
           CASE WHEN n.count_by_group
                THEN count(DISTINCT ps.group_id) ELSE count(ps.unit_id) END AS used
      FROM node_slot sl
      JOIN node n ON n.node_id = sl.node_id
      LEFT JOIN product_state ps ON ps.node_id = sl.node_id AND ps.slot_no = sl.slot_no
     WHERE sl.node_id = p_node
     GROUP BY sl.slot_no, sl.capacity, n.count_by_group
  )
  SELECT o.slot_no, (o.used + 1)::int
    FROM occ o JOIN node n ON n.node_id = p_node
   WHERE o.used < o.capacity
   ORDER BY CASE WHEN n.slot_fill = 'BALANCED' THEN o.used END, o.slot_no
   LIMIT 1;
$$ LANGUAGE sql STABLE;

CREATE VIEW v_node_status AS
SELECT n.node_id, n.label, n.node_type, n.node_kind, n.transporter_id,
       n.ui_kind, coalesce(n.group_label, n.label) AS group_label,
       n.splits_batch, n.count_by_group,
       o.line_id, o.step_order, n.capacity,
       count(x.unit_id)::int                                        AS occupancy,
       CASE WHEN count(x.unit_id) = 1 THEN min(x.display_id) END    AS display_id,
       -- text[] (API 개발 계획 §5-1 · FE string[]). 빈 노드는 '{}'
       coalesce(array_agg(x.display_id ORDER BY x.entered_at) FILTER (WHERE x.unit_id IS NOT NULL), '{}') AS display_ids,
       CASE WHEN count(x.unit_id) = 1 THEN min(x.part_label) END    AS part_label,
       sum(x.part_qty)::int                                         AS part_qty,
       (array_agg(x.display_status ORDER BY
          CASE x.display_status WHEN 'ERROR' THEN 1 WHEN 'RUN' THEN 2
               WHEN 'SETTLING' THEN 3 WHEN 'DONE' THEN 4 WHEN 'WAIT' THEN 5 ELSE 6 END))[1]
                                                                    AS status,
       min(x.settle_left_s)                                         AS settle_left_s,
       max(x.transport_wait_s)                                      AS transport_wait_s,
       max(extract(epoch FROM (now() - x.entered_at)))::int         AS elapsed_s,
       n.std_cycle_s,
       CASE WHEN n.std_cycle_s > 0 THEN least(100, round(
         100.0 * max(extract(epoch FROM (now() - x.entered_at))) / n.std_cycle_s))::int END
                                                                    AS progress_pct,
       n.attrs                                                      -- 화면 분기(measure · duration_input · count_by_group) — §5-2
  FROM node n
  JOIN v_node_order o ON o.node_id = n.node_id
  LEFT JOIN (SELECT d.*, us.display_id, us.line_id, us.part_label, us.part_qty
               FROM v_product_display d JOIN v_unit_summary us USING (unit_id)) x
         ON x.node_id = n.node_id AND x.line_id = o.line_id
 WHERE n.is_active
 GROUP BY n.node_id, n.label, n.node_type, n.node_kind, n.transporter_id,
          n.ui_kind, n.group_label, n.splits_batch, n.count_by_group,
          o.line_id, o.step_order, n.capacity, n.std_cycle_s, n.attrs;

CREATE VIEW v_slot_map AS
SELECT sl.node_id, n.label, sl.slot_no, p.pos_no, u.display_id, ps.unit_id, ps.group_id, ps.entered_at
  FROM node_slot sl
  JOIN node n USING (node_id)
  CROSS JOIN LATERAL generate_series(1, sl.capacity) AS p(pos_no)
  LEFT JOIN product_state ps ON ps.node_id = sl.node_id AND ps.slot_no = sl.slot_no AND ps.pos_no = p.pos_no
  LEFT JOIN unit u ON u.unit_id = ps.unit_id
 WHERE n.is_active;

CREATE VIEW v_rack_slot AS
SELECT sl.node_id, n.label, n.slot_access, sl.slot_no, sl.capacity,
       count(ps.unit_id)::int AS used, (sl.capacity - count(ps.unit_id))::int AS free,
       -- text[] · 반출 차례(pos_no 1)부터 (§5-3). head_display_id = 다음에 나갈 것
       coalesce(array_agg(u.display_id ORDER BY ps.pos_no) FILTER (WHERE u.unit_id IS NOT NULL), '{}') AS contents,
       min(u.display_id) FILTER (WHERE ps.pos_no = 1)                                                AS head_display_id
  FROM node_slot sl
  JOIN node n USING (node_id)
  LEFT JOIN product_state ps ON ps.node_id = sl.node_id AND ps.slot_no = sl.slot_no
  LEFT JOIN unit u ON u.unit_id = ps.unit_id
 WHERE n.is_active
 GROUP BY sl.node_id, n.label, n.slot_access, sl.slot_no, sl.capacity;

-- 지금 꺼낼 수 있는 것. M3b 의 이동 후보 산출은 이 뷰를 봐야 한다.
CREATE VIEW v_retrievable AS
SELECT ps.unit_id, ps.node_id, ps.slot_no, ps.pos_no, ps.status, ps.ready_at, n.slot_access
  FROM product_state ps JOIN node n USING (node_id)
 WHERE ps.slot_no IS NULL OR n.slot_access = 'RANDOM'
    OR (n.slot_access = 'LIFO' AND ps.pos_no = (SELECT max(x.pos_no) FROM product_state x
                                                WHERE x.node_id = ps.node_id AND x.slot_no = ps.slot_no))
    OR (n.slot_access = 'FIFO' AND ps.pos_no = (SELECT min(x.pos_no) FROM product_state x
                                                WHERE x.node_id = ps.node_id AND x.slot_no = ps.slot_no));

CREATE VIEW v_rack_load AS
SELECT n.node_id, n.label, n.capacity AS slot_capacity,
       (SELECT count(*) FROM product_state p WHERE p.node_id = n.node_id)::int          AS unit_qty,
       (SELECT coalesce(sum(us.part_qty), 0)::int FROM product_state p
          JOIN v_unit_summary us USING (unit_id) WHERE p.node_id = n.node_id)           AS part_qty,
       (SELECT count(*) FROM node_slot sl WHERE sl.node_id = n.node_id)::int           AS slots,
       (SELECT count(*) FROM v_rack_slot vs WHERE vs.node_id = n.node_id AND vs.free = 0)::int AS full_slots
  FROM node n WHERE n.is_active AND n.node_kind = 'RACK';

-- 반송 자원 부하. 노드별 담당이므로 조인이 단순하다.
CREATE VIEW v_transporter_load AS
SELECT t.transporter_id, t.label, t.kind, t.auto_dispatch, ts.status,
       count(q.unit_id)::int                                                    AS queued,
       coalesce(round(avg(extract(epoch FROM (now() - q.ready_at)))), 0)::int   AS avg_wait_s,
       coalesce(round(max(extract(epoch FROM (now() - q.ready_at)))), 0)::int   AS max_wait_s
  FROM transporter t
  LEFT JOIN transporter_state ts USING (transporter_id)
  LEFT JOIN node n ON n.transporter_id = t.transporter_id AND n.is_active
  LEFT JOIN v_retrievable q ON q.node_id = n.node_id AND q.status = 'DONE'
                           AND (q.ready_at IS NULL OR q.ready_at <= now())
 WHERE t.is_active
 GROUP BY t.transporter_id, t.label, t.kind, t.auto_dispatch, ts.status;

CREATE VIEW v_part_progress AS
SELECT c.part_no, p.name AS part_name, u.line_id, ps.node_id, n.label AS node_label,
       o.step_order, d.display_status AS status,
       count(*)::int AS unit_qty, sum(c.qty - c.qty_scrapped)::int AS part_qty
  FROM unit_content c
  JOIN part p USING (part_no)
  JOIN unit u USING (unit_id)
  JOIN product_state ps USING (unit_id)
  JOIN v_product_display d ON d.unit_id = ps.unit_id
  JOIN node n ON n.node_id = ps.node_id
  LEFT JOIN v_node_order o ON o.node_id = ps.node_id AND o.line_id = u.line_id
 GROUP BY c.part_no, p.name, u.line_id, ps.node_id, n.label, o.step_order, d.display_status;

CREATE VIEW v_output AS
SELECT ps.node_id, count(*)::int AS units, coalesce(sum(vc.total_qty), 0)::int AS parts
  FROM product_state ps JOIN v_unit_content vc USING (unit_id) GROUP BY ps.node_id;

CREATE VIEW v_scrap_summary AS
SELECT s.node_id, n.label AS node_label, s.part_no, s.reason, count(*)::int AS events, sum(s.qty)::int AS qty
  FROM part_scrap s LEFT JOIN node n ON n.node_id = s.node_id
 GROUP BY s.node_id, n.label, s.part_no, s.reason;

-- 플레이트 사용률. 라인에 있는 배치 수 / 보유 플레이트 수.
CREATE VIEW v_plate_usage AS
SELECT l.line_id, l.plate_count,
       (SELECT count(*) FROM unit u JOIN product_state ps USING (unit_id)
         WHERE u.line_id = l.line_id AND u.unit_kind = 'BATCH')::int AS plates_in_use
  FROM line l WHERE l.is_active;

CREATE VIEW v_order_progress AS
SELECT o.order_id, o.customer, o.status, o.due_at,
       (extract(epoch FROM (o.due_at - now())) / 3600)::int                   AS due_in_h,
       (SELECT sum(qty) FROM order_line ol WHERE ol.order_id = o.order_id)::int AS ordered_qty,
       (SELECT count(*) FROM unit u WHERE u.order_id = o.order_id AND u.unit_kind = 'PART')::int
                                                                              AS produced_qty,
       (SELECT count(*) FROM unit u JOIN product_state ps USING (unit_id) JOIN node n USING (node_id)
         WHERE u.order_id = o.order_id AND u.unit_kind = 'PART' AND n.node_type = 'EXIT')::int
                                                                              AS scrapped_qty,
       (SELECT count(*) FROM unit u WHERE u.order_id = o.order_id
           AND u.unit_kind = 'BATCH' AND u.consumed_at IS NULL)::int          AS batch_in_progress,
       -- 완료 = 공정 종착 랙에 있는 부품.
       -- 종착 = MAIN 으로 들어오지만 MAIN 으로 나가지 않는 노드. 폐기함은 EXIT 로만 들어오므로 제외된다.
       (SELECT count(*) FROM unit u JOIN product_state ps USING (unit_id) JOIN node n USING (node_id)
         WHERE u.order_id = o.order_id AND u.unit_kind = 'PART' AND n.node_kind = 'RACK'
           AND EXISTS (SELECT 1 FROM route r WHERE r.to_node = n.node_id AND r.edge_kind = 'MAIN')
           AND NOT EXISTS (SELECT 1 FROM route r WHERE r.from_node = n.node_id AND r.edge_kind = 'MAIN'))::int
                                                                              AS done_qty
  FROM customer_order o;

-- 최신 판정. 뒤집힌 이력은 judgement 원본에 남고, 여기는 유효한 것만.
CREATE VIEW v_latest_judgement AS
SELECT DISTINCT ON (unit_id, node_id) unit_id, node_id, ts, verdict, value, note, source
  FROM judgement ORDER BY unit_id, node_id, ts DESC;

-- 어느 노드로 갈 차례인가. "치수검사 대기 큐"는 이 뷰에서 next_node = 'INS-01' 이다.
-- 물리 큐가 아니라 파생이다 — 경화가 끝난 부품은 사람이 넣지 않아도 여기 나타난다.
CREATE VIEW v_waiting_for AS
SELECT q.unit_id, u.display_id, q.node_id AS at_node, r.to_node AS next_node,
       q.ready_at, extract(epoch FROM (now() - q.ready_at))::int AS waiting_s
  FROM v_retrievable q
  JOIN unit u USING (unit_id)
  JOIN route r ON r.from_node = q.node_id AND r.line_id = u.line_id AND r.edge_kind = 'MAIN'
 WHERE q.status = 'DONE' AND (q.ready_at IS NULL OR q.ready_at <= now());

-- ============================================================
--  M4-b. 신규 API 가 요구한 뷰 5개 (20260916_api_design.md §5)
--  🚨 전부 line_id 로 묶는다 — 노드가 두 라인에 속하므로 안 걸면 행이 곱해진다.
-- ============================================================

-- 직전 MAIN 노드. "MAIN 이고 · 활성이고 · 같은 라인" 세 조건을 한 곳에 둔다.
-- 여러 화면이 각자 route 를 걸면 조건이 갈라진다.
CREATE VIEW v_node_prev AS
SELECT r.line_id, r.to_node AS node_id,
       p.node_id AS prev_node, p.label AS prev_label, p.node_kind AS prev_kind
  FROM route r
  JOIN node p ON p.node_id = r.from_node AND p.is_active
  JOIN node c ON c.node_id = r.to_node   AND c.is_active
 WHERE r.edge_kind = 'MAIN';

-- 파이프라인 행 = 재공 1건. 배치는 개체 하나, 부품은 묶음 하나로 접는다.
-- 접는 기준이 화면마다 갈리면 같은 라인이 다르게 보이므로 여기서 한 번만 정한다.
CREATE VIEW v_wip AS
SELECT 'UNIT'::text AS ref_kind, us.unit_id::text AS ref, us.display_id,
       us.line_id, us.part_label, us.part_qty,
       ps.node_id, n.label AS node_label, o.step_order,
       d.display_status, d.settle_left_s, d.transport_wait_s,
       (n.node_kind = 'RACK') AS waiting          -- 랙에서 다음 공정을 기다리는 중 (§5-4 · API 가 계산하지 않는다)
  FROM v_unit_summary us
  JOIN product_state ps USING (unit_id)
  JOIN v_product_display d USING (unit_id)
  JOIN node n ON n.node_id = ps.node_id
  LEFT JOIN v_node_order o ON o.node_id = ps.node_id AND o.line_id = us.line_id
 WHERE us.unit_kind = 'BATCH'
UNION ALL
SELECT 'GROUP', ps.group_id, ps.group_id,
       us.line_id,
       CASE WHEN count(DISTINCT uc.part_no) = 1 THEN min(uc.part_no)
            ELSE '혼재 ' || count(DISTINCT uc.part_no) || '종' END,
       count(*)::int,
       ps.node_id, n.label, o.step_order,
       (array_agg(d.display_status ORDER BY
          CASE d.display_status WHEN 'ERROR' THEN 1 WHEN 'HOLD' THEN 2 WHEN 'RUN' THEN 3
               WHEN 'SETTLING' THEN 4 WHEN 'DONE' THEN 5 WHEN 'WAIT' THEN 6 ELSE 7 END))[1],
       min(d.settle_left_s), max(d.transport_wait_s),
       (n.node_kind = 'RACK')
  FROM product_state ps
  JOIN v_unit_summary us USING (unit_id)
  JOIN v_product_display d USING (unit_id)
  JOIN node n ON n.node_id = ps.node_id
  LEFT JOIN unit_content uc ON uc.unit_id = ps.unit_id
  LEFT JOIN v_node_order o ON o.node_id = ps.node_id AND o.line_id = us.line_id
 WHERE ps.group_id IS NOT NULL AND us.unit_kind = 'PART'
 GROUP BY ps.group_id, us.line_id, ps.node_id, n.label, n.node_kind, o.step_order;

-- 이 노드에 들어올 차례. v_waiting_for 는 부품 단위인데 화면은 묶음 1줄로 본다.
-- ready = 출처마다 맨 앞의 것 (FIFO). 출처가 여럿이면 각 출처의 앞이 하나씩 선다.
CREATE VIEW v_inbound_queue AS
WITH q AS (
  SELECT w.next_node, w.at_node, u.line_id,
         coalesce(ps.group_id, w.unit_id::text) AS ref,
         CASE WHEN ps.group_id IS NULL THEN 'UNIT' ELSE 'GROUP' END AS ref_kind,
         w.unit_id, w.waiting_s, ps.pos_no
    FROM v_waiting_for w
    JOIN unit u USING (unit_id)
    JOIN product_state ps USING (unit_id)
)
SELECT q.next_node AS node_id, q.line_id, q.ref_kind, q.ref,
       CASE WHEN q.ref_kind = 'GROUP' THEN q.ref ELSE min(u.display_id) END AS label,
       count(*)::int                                   AS qty,
       q.at_node                                       AS from_node,
       min(n.label)                                    AS from_label,
       max(q.waiting_s)                                AS waiting_s,
       min(coalesce(q.pos_no, 1))                      AS pos_no,
       -- 출처(at_node)마다 맨 앞의 것 하나만 지금 넣을 수 있다
       (row_number() OVER (PARTITION BY q.next_node, q.at_node
                           ORDER BY min(coalesce(q.pos_no, 1)), q.ref) = 1) AS ready
  FROM q
  JOIN unit u ON u.unit_id = q.unit_id
  JOIN node n ON n.node_id = q.at_node
 GROUP BY q.next_node, q.line_id, q.ref_kind, q.ref, q.at_node;

-- 노드에 있는 부품 + 최신 판정 + 공차. 공차 키 이름을 화면이나 API 가 알 필요 없게 여기서 꺼낸다.
CREATE VIEW v_node_parts AS
SELECT ps.node_id, u.line_id, ps.unit_id, u.display_id, ps.group_id,
       uc.part_no, p.name AS part_name,
       (p.attrs->>'nominal_mm')::numeric AS nominal_mm,
       (p.attrs->>'tol_mm')::numeric     AS tol_mm,
       j.verdict, j.value AS judge_value, j.ts AS judged_at, j.source AS judge_source,
       n.attrs->'measure' AS measure_spec        -- 이 노드가 받는 측정값 {key,label,unit} (§5-7 · API 가 jsonb 키를 몰라도 되게)
  FROM product_state ps
  JOIN unit u USING (unit_id)
  JOIN node n ON n.node_id = ps.node_id
  JOIN unit_content uc USING (unit_id)
  JOIN part p USING (part_no)
  LEFT JOIN v_latest_judgement j ON j.unit_id = ps.unit_id AND j.node_id = ps.node_id
 WHERE u.unit_kind = 'PART';

-- 묶음 집계. 작업대의 묶음과 랙의 박스가 같은 모양이라 뷰 하나로 둘 다 덮는다.
-- closed = 수동 마감. 정원이 차서 닫힌 것은 unit_qty 로 알 수 있으므로 여기 안 남는다.
CREATE VIEW v_group_at_node AS
-- 묶음(바구니·박스) 한 행. sources = 출처 배치별 파트 수량 jsonb (API 개발 계획 §5-6 — 콤마 텍스트로는 화면이 못 그린다)
--   [{"parent_display_id": "P3-W2", "parts": {"BRK-1002": 4, "HNG-2041": 3}}, ...]
-- capacity = 묶음 정원. 트레이 랙(count_by_group)이면 자기 정원. 작업대면 "MAIN 2홉 안의 설비·트레이 랙 중 정원(>1) 최솟값"
--   (FE 목업 groupTarget 과 같은 규칙 — 서포트 제거대의 묶음은 다음 경화기 바구니(12)에 담기므로 그 정원이 목표다). 없으면 NULL
WITH pp AS (
  SELECT ps.node_id, ps.group_id,
         coalesce(pu.display_id, '(출처 없음)')                AS parent_display_id,
         uc.part_no, sum(uc.qty - uc.qty_scrapped)::int        AS qty
    FROM product_state ps
    JOIN unit u USING (unit_id)
    LEFT JOIN unit pu ON pu.unit_id = u.parent_unit_id
    JOIN unit_content uc ON uc.unit_id = ps.unit_id
   WHERE ps.group_id IS NOT NULL
   GROUP BY ps.node_id, ps.group_id, pu.display_id, uc.part_no
), src AS (
  SELECT node_id, group_id,
         jsonb_agg(jsonb_build_object('parent_display_id', parent_display_id, 'parts', parts)
                   ORDER BY parent_display_id)                  AS sources
    FROM (SELECT node_id, group_id, parent_display_id,
                 jsonb_object_agg(part_no, qty ORDER BY part_no) AS parts
            FROM pp GROUP BY node_id, group_id, parent_display_id) x
   GROUP BY node_id, group_id
)
SELECT ps.node_id, u.line_id, ps.group_id,
       count(*)::int                                          AS unit_qty,
       coalesce(CASE WHEN n.count_by_group THEN n.capacity END,
                (SELECT min(n2.capacity)
                   FROM (SELECT r1.to_node AS nid FROM route r1
                          WHERE r1.from_node = ps.node_id AND r1.line_id = u.line_id AND r1.edge_kind = 'MAIN'
                         UNION
                         SELECT r2.to_node FROM route r1
                           JOIN route r2 ON r2.from_node = r1.to_node AND r2.line_id = r1.line_id AND r2.edge_kind = 'MAIN'
                          WHERE r1.from_node = ps.node_id AND r1.line_id = u.line_id AND r1.edge_kind = 'MAIN') h
                   JOIN node n2 ON n2.node_id = h.nid AND n2.is_active
                  WHERE (n2.node_kind = 'STATION' OR n2.count_by_group) AND n2.capacity > 1))
                                                               AS capacity,
       (gc.group_id IS NOT NULL)                               AS closed,
       gc.closed_at, gc.actor AS closed_by,
       min(u.parent_unit_id::text)                             AS any_parent,
       coalesce((SELECT s.sources FROM src s WHERE s.node_id = ps.node_id AND s.group_id = ps.group_id),
                '[]'::jsonb)                                   AS sources
  FROM product_state ps
  JOIN unit u USING (unit_id)
  JOIN node n ON n.node_id = ps.node_id
  LEFT JOIN group_close gc ON gc.group_id = ps.group_id
 WHERE ps.group_id IS NOT NULL
 GROUP BY ps.node_id, u.line_id, ps.group_id, n.count_by_group, n.capacity,
          gc.group_id, gc.closed_at, gc.actor;

-- 제어 화면의 서브 메뉴. group_label 로 묶고 공정 순서대로.
-- 노드를 늘리면 탭이 늘고, 새 공정을 넣으면 탭이 생긴다 — 화면 코드는 안 바뀐다.
CREATE VIEW v_control_menu AS
SELECT line_id,
       coalesce(group_label, label)      AS menu_label,
       ui_kind,
       min(step_order)                   AS step_order,
       count(*)::int                     AS node_count,
       array_agg(node_id ORDER BY node_id) AS node_ids
  FROM v_node_status
 WHERE node_kind = 'STATION'
 GROUP BY line_id, coalesce(group_label, label), ui_kind
 ORDER BY line_id, min(step_order);
