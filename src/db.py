#!/usr/bin/env python3
"""
Database helpers for app runtime and refresh scripts.
"""

from __future__ import annotations

import os
import ssl

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from dotenv import load_dotenv
load_dotenv()

JAKARTA_TIMEZONE = "Asia/Jakarta"
_MYSQL_ENGINE: Engine | None = None


def get_current_jakarta_time() -> pd.Timestamp:
    return pd.Timestamp.now(tz=JAKARTA_TIMEZONE).tz_localize(None) # current Jakarta time


def require_db_env() -> dict[str, str]:
    required = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")
    values = {key: os.getenv(key, "") for key in required}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            f"Missing required database environment variables: {', '.join(missing)}"
        )
    return values


def get_sql_param_placeholder(conn) -> str:
    return "%s"


def get_mysql_engine() -> Engine:
    global _MYSQL_ENGINE

    if _MYSQL_ENGINE is not None:
        return _MYSQL_ENGINE

    values = require_db_env()
    db_user = values["DB_USER"]
    db_password = values["DB_PASSWORD"]
    db_host = values["DB_HOST"]
    db_port = int(values["DB_PORT"])
    db_name = values["DB_NAME"]

    # SSL config, if want looser but still encrypted, set both to "false"
    ssl_verify_cert = os.getenv("DB_SSL_VERIFY_CERT", "false").lower() == "true"
    ssl_verify_identity = os.getenv("DB_SSL_VERIFY_IDENTITY", "false").lower() == "true"

    connect_args = {
        "connect_timeout": 30,
        "ssl": {
            "check_hostname": ssl_verify_identity,
        },
    }
    if not ssl_verify_cert:
        connect_args["ssl"]["verify_mode"] = ssl.CERT_NONE

    _MYSQL_ENGINE = create_engine(
        f"mysql+pymysql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}",
        pool_pre_ping=True,
        connect_args=connect_args,
    )
    return _MYSQL_ENGINE


def get_conn():
    try:
        engine = get_mysql_engine()
    except ImportError as exc:
        raise ImportError("SQLAlchemy and PyMySQL are required for the database connection.") from exc

    return engine.raw_connection()
