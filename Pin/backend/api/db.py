import os
from contextlib import contextmanager
from dotenv import load_dotenv
import pymysql
from dbutils.pooled_db import PooledDB

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "zhaogebanshang"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "autocommit": False,
}

POOL = PooledDB(
    creator=pymysql,
    maxconnections=int(os.getenv("DB_MAX_CONNECTIONS", 20)),
    mincached=int(os.getenv("DB_MIN_CACHED", 5)),
    maxcached=int(os.getenv("DB_MAX_CACHED", 10)),
    blocking=True,
    ping=1,
    **DB_CONFIG,
)


@contextmanager
def get_db_connection():
    conn = POOL.connection()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_cursor():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()