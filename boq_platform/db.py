from contextlib import contextmanager

import mysql.connector

from .audit import transaction_buffer
from .config import DB_CONFIG


def connect():
    """Open one MySQL connection using the local .env configuration."""
    return mysql.connector.connect(**DB_CONFIG)


@contextmanager
def connection():
    """One transaction: commit on success, rollback on error.

    Audit lines raised inside the block are written after the commit/rollback.
    """
    conn = connect()
    try:
        with transaction_buffer():
            try:
                yield conn
                conn.commit()
            except BaseException:
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
