"""
v2 전용 PostgreSQL 커넥션 풀 — psycopg3 단독 (계획 §3: SQLAlchemy 를 쓰지 않는다).

읽기 = rows() 로 dict 리스트 → pydantic. 쓰기 = 같은 커넥션을 StateEngine(conn) 에 넘긴다.
그래서 "SQLAlchemy 트랜잭션 안의 세이브포인트" 문제(명세 §10-7)가 생기지 않는다.
LINE_DSN 이 비어 있으면 풀을 열지 않는다 — v2 라우터는 503 을 낸다.
"""
from contextlib import contextmanager
from typing import Any, Iterator

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import get_settings

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        dsn = get_settings().LINE_DSN
        if not dsn:
            raise RuntimeError("LINE_DSN 이 비어 있다 — 라인 MES(v2)는 이 인스턴스에서 꺼져 있다")
        _pool = ConnectionPool(dsn, min_size=1, max_size=4, kwargs={"row_factory": dict_row}, open=True)
    return _pool


@contextmanager
def connection() -> Iterator[Connection]:
    with pool().connection() as conn:
        yield conn


def rows(sql: str, **params: Any) -> list[dict]:
    """읽기 한 방. 활성 라인이 둘이라 모든 조회는 line_id 로 걸어야 한다(계획 §2-3)."""
    with connection() as conn:
        return conn.execute(sql, params).fetchall()
