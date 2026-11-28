"""Database connection helper for the 4-table schema in schema.sql.

Reads DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME (and optional DB_SSL_CA)
from .env and opens a MySQL connection. Every module that needs the database
should call get_connection() instead of connecting on its own.
"""

import os
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")


def get_connection():
    """Return a new MySQL connection (autocommit off: call commit() yourself)."""
    config = {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "3306")),
        "user": os.getenv("DB_USER", "root"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "boq_intelligence"),
        "autocommit": False,
    }
    if os.getenv("DB_SSL_CA"):
        config["ssl_ca"] = os.getenv("DB_SSL_CA")
    return mysql.connector.connect(**config)


def query(sql, params=()):
    """Run a SELECT and return a list of dicts, e.g.

        rows = query("SELECT product_name, price FROM master_product WHERE source = %s", ("TPSO",))
        for row in rows:
            print(row["product_name"], row["price"])

    Always pass values through params (the %s placeholders), never by building the SQL
    string yourself, so user input cannot break the query.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        cursor.close()
        return rows
    finally:
        conn.close()


def execute(sql, params=()):
    """Run one INSERT / UPDATE / DELETE, commit it, and return the new row id (or row count)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        conn.commit()
        result = cursor.lastrowid or cursor.rowcount
        cursor.close()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
