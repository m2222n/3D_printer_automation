-- =====================================================================
-- 현행 운영 DB 스키마 (v1) — ERD 확인용
-- =====================================================================
-- 실물에서 뜬 것이다. 두 개의 **서로 다른 DB** 가 한 파일에 들어 있다.
--
--   A. web-api      SQLite  web-api/presets.db        (`sqlite3 .schema` 덤프)
--   B. sequence_service  MariaDB 11.3  automation DB  (SQLAlchemy 모델에서 생성)
--
-- 🚨 두 DB 는 서로 조인하지 않는다. 같은 프린터를 가리키는 키조차 다르다
--    (web-api = printer_serial 'Form4-...' / sequence_service = target_printer 1~4).
--
-- 🚨 실제 DB 에는 FOREIGN KEY 제약이 **하나도 없다.** 아래 FK 는 ERD 에서 선이
--    그려지도록 넣은 것이고, 운영 DB 에는 존재하지 않는 논리적 관계다.
--    (제약 없이 애플리케이션이 지키고 있다는 뜻 = 고아 행이 생길 수 있다)
--
-- 🚨 이 파일은 **라인 MES v2 스키마(schema.sql)와 별개다.** v2 는 아직 DB 로
--    만들어지지 않았고 프런트는 목업이 답한다(frontend/src/services/lineApi.ts:29).
--
-- 방언 = MySQL. AUTO_INCREMENT 는 주석으로만 표기했다(ERD 에 불필요 + SQLite 검증용).
-- =====================================================================


-- ==========================================================
-- A. web-api  (SQLite: web-api/presets.db)
--    Phase 1 모니터링 + Phase 2 프린트 제어 + 비전 + 빈피킹
-- ==========================================================

-- 출력 프리셋 — STL + 슬라이싱 설정 묶음
CREATE TABLE presets (
  id              VARCHAR(36)  NOT NULL,
  name            VARCHAR(100) NOT NULL,
  part_type       VARCHAR(50)  NOT NULL,
  description     TEXT,
  printer_serial  VARCHAR(100),               -- 'Form4-<시리얼>' 등. 외부 키 아님
  settings        JSON         NOT NULL,
  stl_filename    VARCHAR(255),
  print_count     INTEGER,
  created_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);
CREATE INDEX ix_presets_name           ON presets (name);
CREATE INDEX ix_presets_part_type      ON presets (part_type);
CREATE INDEX ix_presets_printer_serial ON presets (printer_serial);

-- 프린트 작업(큐) — 프리셋으로 만들어 프린터에 보낸 건
CREATE TABLE print_jobs (
  id                       VARCHAR(36)  NOT NULL,
  preset_id                VARCHAR(36),           -- → presets.id (제약 없음)
  stl_filename             VARCHAR(255) NOT NULL,
  printer_serial           VARCHAR(100) NOT NULL,
  status                   VARCHAR(20),
  error_message            TEXT,
  scene_id                 VARCHAR(100),          -- PreFormServer scene (외부 시스템 id)
  settings                 JSON         NOT NULL,
  estimated_print_time_ms  INTEGER,
  estimated_material_ml    FLOAT,
  scheduled_at             DATETIME,
  created_at               DATETIME     DEFAULT CURRENT_TIMESTAMP,
  updated_at               DATETIME     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  -- ERD 전용(실 DB 에 없음)
  CONSTRAINT fk_print_jobs_preset FOREIGN KEY (preset_id) REFERENCES presets (id)
);

-- 알림 이벤트 — 프린터 완료/에러. 프린터는 시리얼 문자열로만 참조한다
CREATE TABLE notification_events (
  id              VARCHAR(36) NOT NULL,
  event_type      VARCHAR(30) NOT NULL,
  printer_serial  VARCHAR(100) NOT NULL,
  printer_name    VARCHAR(100),
  job_name        VARCHAR(255),
  message         TEXT,
  is_read         INTEGER,                     -- SQLite 라 BOOLEAN 이 INTEGER 로 뜬다
  created_at      DATETIME    DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);
CREATE INDEX ix_notification_events_event_type     ON notification_events (event_type);
CREATE INDEX ix_notification_events_is_read        ON notification_events (is_read);
CREATE INDEX ix_notification_events_printer_serial ON notification_events (printer_serial);

-- 프린트 이력 메모 — print_guid 는 Formlabs 클라우드의 id 라 우리 테이블에 없다
CREATE TABLE print_notes (
  id          VARCHAR(36)  NOT NULL,
  print_guid  VARCHAR(100) NOT NULL,           -- 외부(Formlabs) 키. 우리 DB 에 대응 행 없음
  content     TEXT         NOT NULL,
  created_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);
CREATE INDEX ix_print_notes_print_guid ON print_notes (print_guid);

-- 비전 카메라 — 세척기/경화기 상태 감시 (MQTT 로 올라온다)
CREATE TABLE vision_cameras (
  camera_id          VARCHAR(20) NOT NULL,
  device_type        VARCHAR(10) NOT NULL,     -- 'wash' | 'cure'
  device_id          INTEGER     NOT NULL,     -- 장비 번호 1,2
  name               VARCHAR(50) NOT NULL,
  status             VARCHAR(20),
  confidence         FLOAT,
  is_online          INTEGER,
  firmware_version   VARCHAR(20),
  model_name         VARCHAR(100),
  ip_address         VARCHAR(15),
  wifi_rssi          INTEGER,
  last_seen          DATETIME,
  last_status_change DATETIME,
  created_at         DATETIME    DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (camera_id)
);
CREATE INDEX ix_vision_cameras_device_type ON vision_cameras (device_type);

-- 비전 상태 전이 이력
CREATE TABLE vision_events (
  id               VARCHAR(36) NOT NULL,
  camera_id        VARCHAR(20) NOT NULL,       -- → vision_cameras.camera_id (제약 없음)
  device_type      VARCHAR(10) NOT NULL,
  device_id        INTEGER     NOT NULL,
  previous_status  VARCHAR(20),
  new_status       VARCHAR(20) NOT NULL,
  confidence       FLOAT,
  created_at       DATETIME    DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  -- ERD 전용(실 DB 에 없음)
  CONSTRAINT fk_vision_events_camera FOREIGN KEY (camera_id) REFERENCES vision_cameras (camera_id)
);
CREATE INDEX ix_vision_events_camera_id  ON vision_events (camera_id);
CREATE INDEX ix_vision_events_created_at ON vision_events (created_at);
CREATE INDEX ix_vision_events_device_type ON vision_events (device_type);

-- 빈피킹 인식 장면 — 모듈이 POST 로 올린 한 장
CREATE TABLE binpick_scenes (
  id                       VARCHAR(36)  NOT NULL,
  scene_id                 VARCHAR(120),        -- 모듈이 붙인 이름(중복 가능)
  schema_version           VARCHAR(20)  NOT NULL,
  module                   VARCHAR(30)  NOT NULL,
  n_detections             INTEGER      NOT NULL,
  n_unique_labels          INTEGER      NOT NULL,
  recognition_track        VARCHAR(30),
  latency_ms               FLOAT,
  gate_verdict             VARCHAR(30)  NOT NULL,  -- in_distribution | out_of_distribution | not_checked
  gate_trusted             BOOLEAN,
  gate_valid_ratio_pct     FLOAT,
  gate_note                TEXT,
  gate_n_dropped_by_size   INTEGER      NOT NULL,
  reported_at              VARCHAR(40),
  created_at               DATETIME     DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
);
CREATE INDEX ix_binpick_scenes_created_at     ON binpick_scenes (created_at);
CREATE INDEX ix_binpick_scenes_gate_verdict   ON binpick_scenes (gate_verdict);
CREATE INDEX ix_binpick_scenes_module         ON binpick_scenes (module);
CREATE INDEX ix_binpick_scenes_module_created ON binpick_scenes (module, created_at);
CREATE INDEX ix_binpick_scenes_scene_id       ON binpick_scenes (scene_id);

-- 장면 안의 검출 하나 = 부품 하나. idx 로 순서 보존
CREATE TABLE binpick_detections (
  id                VARCHAR(36) NOT NULL,
  scene_pk          VARCHAR(36) NOT NULL,      -- → binpick_scenes.id (제약 없음)
  idx               INTEGER     NOT NULL,
  label             VARCHAR(60),
  x                 FLOAT,
  y                 FLOAT,
  z                 FLOAT,
  angle             FLOAT,
  confidence        FLOAT,
  gripper_width_mm  FLOAT,
  created_at        DATETIME    DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  -- ERD 전용(실 DB 에 없음)
  CONSTRAINT fk_binpick_detections_scene FOREIGN KEY (scene_pk) REFERENCES binpick_scenes (id)
);
CREATE INDEX ix_binpick_detections_label    ON binpick_detections (label);
CREATE INDEX ix_binpick_detections_scene_pk ON binpick_detections (scene_pk);


-- ==========================================================
-- B. sequence_service  (MariaDB 11.3, DB 이름 = automation)
--    공장 PC 전용. 로봇 이송 시퀀스 런타임이 쓴다
--    🚨 위 A 와 물리적으로 다른 DB 이고 조인하지 않는다
-- ==========================================================

-- 자동화 명령(CMD) — 파일 한 건을 출력~후처리까지 끌고 가는 단위
CREATE TABLE print_command (
  cmd_id           VARCHAR(36)   NOT NULL,
  file_path        VARCHAR(1024) NOT NULL,
  file_name        VARCHAR(255)  NOT NULL,
  cmd_status       INTEGER       NOT NULL,       -- 상태 코드(정수). 라벨은 코드에 있다
  post_proc_stage  INTEGER       NOT NULL DEFAULT 0,
  washing_time     INTEGER       NOT NULL DEFAULT 6,
  curing_time      INTEGER       NOT NULL DEFAULT 120,
  use_yn           VARCHAR(1)    NOT NULL DEFAULT 'Y',
  target_printer   INTEGER,                      -- 1~4. 🚨 시리얼이 아니라 호기 번호다
  allocated_data   JSON,
  progress         INTEGER       NOT NULL DEFAULT 0,
  message          VARCHAR(1024),
  claimed_by       VARCHAR(64),                  -- 워커 락
  locked_at        DATETIME,
  created_at       DATETIME      NOT NULL,
  updated_at       DATETIME      NOT NULL,
  PRIMARY KEY (cmd_id)
);
CREATE INDEX idx_status_created ON print_command (cmd_status, created_at);
CREATE INDEX idx_locked         ON print_command (locked_at);

-- 셀 상태 — 한 행짜리 런타임 플래그(가동/일시정지/시뮬)
CREATE TABLE cell_state (
  id           INTEGER  NOT NULL,               -- AUTO_INCREMENT
  running      INTEGER  NOT NULL DEFAULT 0,
  paused       INTEGER  NOT NULL DEFAULT 0,
  simul_mode   INTEGER  NOT NULL DEFAULT 0,     -- 2026-05-06 머지 5차로 추가된 컬럼
  queue_state  JSON,
  updated_at   DATETIME NOT NULL,
  PRIMARY KEY (id)
);

-- 자동화 로그 — cmd_id 가 있으면 그 명령의 로그다(널 허용 = 시스템 로그)
CREATE TABLE automation_log (
  id          BIGINT        NOT NULL,           -- AUTO_INCREMENT
  log_type    INTEGER       NOT NULL,
  source      VARCHAR(64)   NOT NULL,
  cmd_id      VARCHAR(36),                      -- → print_command.cmd_id (제약 없음)
  message     VARCHAR(2048) NOT NULL,
  created_at  DATETIME      NOT NULL,
  PRIMARY KEY (id),
  -- ERD 전용(실 DB 에 없음)
  CONSTRAINT fk_automation_log_cmd FOREIGN KEY (cmd_id) REFERENCES print_command (cmd_id)
);
CREATE INDEX idx_automation_log_created      ON automation_log (created_at);
CREATE INDEX idx_automation_log_type_created ON automation_log (log_type, created_at);
