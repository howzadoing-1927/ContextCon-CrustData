"""Server-side Postgres access. API and worker connect with server credentials that bypass RLS,
so every query must filter by organization_id itself."""

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import get_settings

_pool: ConnectionPool | None = None


class DatabaseNotConfigured(RuntimeError):
    pass


def connect_kwargs() -> dict:
    # prepare_threshold=None keeps statements unprepared, which is safe behind Supabase poolers.
    return {"row_factory": dict_row, "autocommit": True, "prepare_threshold": None, "connect_timeout": 5}


def _configure(conn: psycopg.Connection) -> None:
    # Instants are persisted and returned in UTC. Needs a session-mode or direct connection.
    conn.execute("set time zone 'UTC'")


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        url = get_settings().database_url
        if not url:
            raise DatabaseNotConfigured("DATABASE_URL is not set")
        _pool = ConnectionPool(
            url, min_size=1, max_size=5, kwargs=connect_kwargs(), configure=_configure, open=False
        )
        _pool.open(wait=False)
    return _pool


def reset_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
    _pool = None


@contextmanager
def transaction(timeout: float = 5.0) -> Iterator[psycopg.Connection]:
    with get_pool().connection(timeout=timeout) as conn, conn.transaction():
        yield conn


@contextmanager
def connection(timeout: float = 5.0) -> Iterator[psycopg.Connection]:
    with get_pool().connection(timeout=timeout) as conn:
        yield conn
