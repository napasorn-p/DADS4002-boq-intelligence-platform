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
