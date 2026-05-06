from __future__ import annotations

from datetime import datetime
from typing import Any
import uuid
import json
from pathlib import Path
import math
import socket

from sqlalchemy import create_engine, text

from app.core.config import get_settings

settings = get_settings()

# Lazy engine: MySQL이 없어도 앱 시작 가능 (자동화 API 호출 시에만 연결 시도)
_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(settings.SEQUENCE_MYSQL_DSN, future=True)
    return _engine


def _ensure_automation_log_table() -> None:
    with _get_engine().begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS automation_log (
                    id BIGINT PRIMARY KEY AUTO_INCREMENT,
                    log_type INT NOT NULL,
                    source VARCHAR(64) NOT NULL,
                    cmd_id VARCHAR(36) NULL,
                    message VARCHAR(2048) NOT NULL,
                    created_at DATETIME NOT NULL,
                    INDEX idx_automation_log_created (created_at),
                    INDEX idx_automation_log_type_created (log_type, created_at)
                )
                """
            )
        )


def _ensure_automation_comm_config_table() -> None:
    with _get_engine().begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS automation_comm_config (
                    id INT PRIMARY KEY,
                    robot_host VARCHAR(255) NOT NULL,
                    robot_port INT NOT NULL,
                    vision_host VARCHAR(255) NOT NULL,
                    vision_port INT NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        row = conn.execute(
            text("SELECT id FROM automation_comm_config WHERE id = 1 LIMIT 1")
        ).mappings().first()
        if not row:
            conn.execute(
                text(
                    """
                    INSERT INTO automation_comm_config
                    (id, robot_host, robot_port, vision_host, vision_port, updated_at)
                    VALUES (1, :robot_host, :robot_port, :vision_host, :vision_port, :updated_at)
                    """
                ),
                {
                    "robot_host": settings.ROBOT_TCP_HOST,
                    "robot_port": int(settings.ROBOT_TCP_PORT),
                    "vision_host": settings.VISION_TCP_HOST,
                    "vision_port": int(settings.VISION_TCP_PORT),
                    "updated_at": datetime.now(),
                },
            )


def get_comm_targets() -> dict[str, Any]:
    _ensure_automation_comm_config_table()
    with _get_engine().begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT robot_host, robot_port, vision_host, vision_port, updated_at
                FROM automation_comm_config
                WHERE id = 1
                LIMIT 1
                """
            )
        ).mappings().first()
    if not row:
        return {
            "robot_host": settings.ROBOT_TCP_HOST,
            "robot_port": int(settings.ROBOT_TCP_PORT),
            "vision_host": settings.VISION_TCP_HOST,
            "vision_port": int(settings.VISION_TCP_PORT),
            "updated_at": datetime.now(),
        }
    return dict(row)


def set_comm_targets(
    robot_host: str,
    robot_port: int,
    vision_host: str,
    vision_port: int,
) -> dict[str, Any]:
    _ensure_automation_comm_config_table()
    robot_host = (robot_host or "").strip() or settings.ROBOT_TCP_HOST
    vision_host = (vision_host or "").strip() or settings.VISION_TCP_HOST
    robot_port = int(robot_port)
    vision_port = int(vision_port)
    now = datetime.now()
    with _get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE automation_comm_config
                SET robot_host = :robot_host,
                    robot_port = :robot_port,
                    vision_host = :vision_host,
                    vision_port = :vision_port,
                    updated_at = :updated_at
                WHERE id = 1
                """
            ),
            {
                "robot_host": robot_host,
                "robot_port": robot_port,
                "vision_host": vision_host,
                "vision_port": vision_port,
                "updated_at": now,
            },
        )
    add_log(
        log_type=10,
        source="program",
        message=f"Manual comm target updated: robot={robot_host}:{robot_port}, vision={vision_host}:{vision_port}",
    )
    return get_comm_targets()


def add_log(log_type: int, source: str, message: str, cmd_id: str | None = None) -> None:
    if not message:
        return
    _ensure_automation_log_table()
    with _get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO automation_log (log_type, source, cmd_id, message, created_at)
                VALUES (:log_type, :source, :cmd_id, :message, :created_at)
                """
            ),
            {
                "log_type": int(log_type),
                "source": (source or "program")[:64],
                "cmd_id": cmd_id,
                "message": message[:2048],
                "created_at": datetime.now(),
            },
        )


def create_command(
    file_path: str,
    file_name: str | None,
    washing_time: int,
    curing_time: int,
    allocated_data: dict[str, Any] | None = None,
    target_printer: int | None = None, # 260410 추가
) -> str:
    now = datetime.now()
    cmd_id = str(uuid.uuid4())
    resolved_name = file_name.strip() if file_name else Path(file_path).name
    payload = allocated_data or {}
    with _get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO print_command
                (cmd_id, file_path, file_name, cmd_status, post_proc_stage,
                 wash_minutes, washing_time, curing_time, use_yn, target_printer, allocated_data,
                 progress, message, claimed_by, locked_at, created_at, updated_at)
                VALUES
                (:cmd_id, :file_path, :file_name, 10, 0,
                 :wash_minutes, :washing_time, :curing_time, 'Y', :target_printer, :allocated_data,
                 0, :message, NULL, NULL, :created_at, :updated_at)
                """
            ),
            {
                "cmd_id": cmd_id,
                "file_path": file_path,
                "file_name": resolved_name,
                "wash_minutes": max(1, int(math.ceil(washing_time / 60))),
                "washing_time": washing_time,
                "curing_time": curing_time,
                "target_printer": target_printer, # None에서 target_printer로 수정
                "allocated_data": json.dumps(payload),
                "message": "QUEUED from automation tab",
                "created_at": now,
                "updated_at": now,
            },
        )
    add_log(log_type=10, source="program", cmd_id=cmd_id, message="CMD created from automation tab")
    return cmd_id


def list_commands(limit: int = 100) -> list[dict[str, Any]]:
    with _get_engine().begin() as conn:
        # Disable previous-day commands on each read to avoid accidental re-production.
        conn.execute(
            text(
                """
                UPDATE print_command
                SET use_yn = 'N',
                    updated_at = NOW()
                WHERE DATE(created_at) < CURDATE()
                  AND use_yn <> 'N'
                """
            )
        )
        rows = conn.execute(
            text(
                """
                SELECT cmd_id, file_path, file_name, cmd_status, post_proc_stage,
                       wash_minutes, washing_time, curing_time,
                       use_yn,
                       target_printer, allocated_data,
                       progress, message, claimed_by, locked_at,
                       created_at, updated_at
                FROM print_command
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": max(1, min(limit, 500))},
        ).mappings().all()
    return [dict(r) for r in rows]


def set_commands_use_yn(cmd_ids: list[str], use_yn: str) -> int:
    if not cmd_ids:
        return 0
    normalized = use_yn.strip().upper()
    if normalized not in {"Y", "N"}:
        raise ValueError("use_yn must be Y or N")
    now = datetime.now()
    placeholders = ", ".join([f":id_{i}" for i in range(len(cmd_ids))])
    params: dict[str, Any] = {"use_yn": normalized, "updated_at": now}
    for i, cmd_id in enumerate(cmd_ids):
        params[f"id_{i}"] = cmd_id
    with _get_engine().begin() as conn:
        if normalized == "N":
            # Treat Use=N from Automation UI as cancellation request.
            # Do not overwrite terminal DONE/ERROR states.
            result = conn.execute(
                text(
                    f"""
                    UPDATE print_command
                    SET use_yn = :use_yn,
                        cmd_status = CASE
                            WHEN cmd_status IN (90, 99, 98) THEN cmd_status
                            ELSE 98
                        END,
                        message = CASE
                            WHEN cmd_status IN (90, 99, 98) THEN message
                            ELSE 'CANCELED by UI(use_yn=N)'
                        END,
                        updated_at = :updated_at
                    WHERE cmd_id IN ({placeholders})
                    """
                ),
                params,
            )
        else:
            result = conn.execute(
                text(
                    f"""
                    UPDATE print_command
                    SET use_yn = :use_yn,
                        updated_at = :updated_at
                    WHERE cmd_id IN ({placeholders})
                    """
                ),
                params,
            )
    return int(result.rowcount or 0)


def set_cell_state(action: str) -> dict[str, bool]:
    action = action.lower().strip()
    running = None
    paused = None
    if action == "start":
        running, paused = 1, 0
    elif action == "stop":
        running, paused = 0, 0
    elif action == "pause":
        paused = 1
    elif action == "resume":
        paused = 0
    else:
        raise ValueError(f"invalid action: {action}")

    now = datetime.now()
    with _get_engine().begin() as conn:
        row = conn.execute(
            text("SELECT id, running, paused FROM cell_state WHERE id = 1 LIMIT 1")
        ).mappings().first()
        if row:
            values: dict[str, Any] = {"updated_at": now}
            if running is not None:
                values["running"] = running
            if paused is not None:
                values["paused"] = paused
            conn.execute(
                text(
                    """
                    UPDATE cell_state
                    SET running = COALESCE(:running, running),
                        paused = COALESCE(:paused, paused),
                        updated_at = :updated_at
                    WHERE id = 1
                    """
                ),
                {
                    "running": values.get("running"),
                    "paused": values.get("paused"),
                    "updated_at": values["updated_at"],
                },
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO cell_state (id, running, paused, updated_at)
                    VALUES (1, :running, :paused, :updated_at)
                    """
                ),
                {
                    "running": running if running is not None else 0,
                    "paused": paused if paused is not None else 0,
                    "updated_at": now,
                },
            )
    add_log(log_type=10, source="program", message=f"Control action: {action.upper()}")
    return get_cell_state()


def set_simul_mode(mode: bool) -> dict[str, bool]:
    now = datetime.now()
    _ensure_cell_state_columns()  # 컬럼 유무 확인
    with _get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE cell_state
                SET simul_mode = :simul_mode,
                    updated_at = :updated_at
                WHERE id = 1
                """
            ),
            {
                "simul_mode": 1 if mode else 0,
                "updated_at": now,
            },
        )
    add_log(log_type=10, source="program", message=f"SIMUL_MODE toggled: {mode}")
    return get_cell_state()


def get_cell_state() -> dict[str, bool]:
    _ensure_cell_state_columns()
    with _get_engine().begin() as conn:
        try:
            row = conn.execute(
                text("SELECT running, paused, simul_mode FROM cell_state WHERE id = 1 LIMIT 1")
            ).mappings().first()
        except Exception:
            # 컬럼이 없는 등의 이유로 에러 발생 시 재시도 또는 기본값 반환
            row = conn.execute(
                text("SELECT running, paused FROM cell_state WHERE id = 1 LIMIT 1")
            ).mappings().first()

    if not row:
        return {"running": False, "paused": False, "simul_mode": False}
    return {
        "running": bool(row["running"]),
        "paused": bool(row["paused"]),
        "simul_mode": bool(row.get("simul_mode", 0))
    }


def _ensure_cell_state_columns() -> None:
    """cell_state 테이블에 필요한 컬럼(simul_mode 등)이 있는지 확인하고 없으면 추가합니다."""
    with _get_engine().begin() as conn:
        # simul_mode 컬럼 존재 여부 확인
        columns = conn.execute(text("SHOW COLUMNS FROM cell_state")).mappings().all()
        existing_cols = [c['Field'].lower() for c in columns]
        
        if 'simul_mode' not in existing_cols:
            try:
                conn.execute(text("ALTER TABLE cell_state ADD COLUMN simul_mode INT DEFAULT 0 AFTER paused"))
                add_log(log_type=10, source="program", message="DB Migration: Added 'simul_mode' column to cell_state")
            except Exception as e:
                print(f"Failed to add simul_mode column: {e}")


def get_queue_state() -> dict[str, Any]:
    with _get_engine().begin() as conn:
        row = conn.execute(
            text("SELECT queue_state FROM cell_state WHERE id = 1 LIMIT 1")
        ).mappings().first()
    if not row:
        return {}
    q = row.get("queue_state")
    if isinstance(q, str):
        try:
            return json.loads(q)
        except Exception:
            return {}
    return q or {}


def list_logs(limit: int = 200) -> list[dict[str, Any]]:
    _ensure_automation_log_table()
    with _get_engine().begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, log_type, source, cmd_id, message, created_at
                FROM automation_log
                ORDER BY id DESC
                LIMIT :limit
                """
            ),
            {"limit": max(1, min(limit, 1000))},
        ).mappings().all()
    return [dict(r) for r in rows]


def send_st_framed(host: str, port: int, payload: str, timeout_seconds: float) -> dict[str, Any]:
    msg = f"ST/{payload}\n".encode("utf-8")
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds) as sock:
            sock.sendall(msg)
            sock.settimeout(timeout_seconds)
            try:
                response = sock.recv(4096)
                return {
                    "ok": True,
                    "sent": msg.decode("utf-8", errors="ignore"),
                    "response": response.decode("utf-8", errors="ignore"),
                }
            except socket.timeout:
                return {
                    "ok": True,
                    "sent": msg.decode("utf-8", errors="ignore"),
                    "response": "",
                }
    except Exception as e:
        return {"ok": False, "sent": msg.decode("utf-8", errors="ignore"), "error": str(e)}


def probe_tcp(host: str, port: int, timeout_seconds: float) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout_seconds):
            return {"ok": True, "connected": True}
    except Exception as e:
        return {"ok": False, "connected": False, "error": str(e)}
