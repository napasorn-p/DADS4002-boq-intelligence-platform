from contextlib import contextmanager

import mysql.connector

from .config import DB_CONFIG


def connect():
    """Open one MySQL connection using the local .env configuration."""
    return mysql.connector.connect(**DB_CONFIG)


@contextmanager
def connection():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def query(sql, params=(), *, dictionary=True):
    with connection() as conn:
        cursor = conn.cursor(dictionary=dictionary)
        try:
            cursor.execute(sql, params)
            if cursor.with_rows:
                return cursor.fetchall()
            return cursor.rowcount
        finally:
            cursor.close()


def execute(sql, params=()):
    with connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(sql, params)
            return cursor.lastrowid if cursor.lastrowid else cursor.rowcount
        finally:
            cursor.close()
