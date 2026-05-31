"""MySQL connection helpers.

All callers should use ``get_conn()`` as a context manager so the
connection is closed automatically. Queries must be parameterized.
"""
from contextlib import contextmanager
import mysql.connector
from mysql.connector import pooling

from config import Config


_pool: pooling.MySQLConnectionPool | None = None


def _build_pool() -> pooling.MySQLConnectionPool:
    return pooling.MySQLConnectionPool(
        pool_name="greentable_pool",
        pool_size=5,
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        autocommit=False,
    )


def _get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = _build_pool()
    return _pool


@contextmanager
def get_conn():
    """Yield a pooled MySQL connection."""
    conn = _get_pool().get_connection()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor(dictionary: bool = True, commit: bool = False):
    """Yield a cursor and (optionally) commit on success."""
    with get_conn() as conn:
        cur = conn.cursor(dictionary=dictionary)
        try:
            yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
