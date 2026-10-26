import sqlite3
import logging
from datetime import datetime

from app.config import DB_PATH

logger = logging.getLogger(__name__)


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                platform TEXT,
                url TEXT,
                thumbnail TEXT,
                category TEXT,
                end_date TEXT,
                notified_at TEXT,
                reminder_sent_at TEXT,
                wishlist_notified_at TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(source, external_id)
            );
            CREATE TABLE IF NOT EXISTS dev_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                fetched_at TEXT NOT NULL,
                UNIQUE(source, external_id)
            );
            CREATE TABLE IF NOT EXISTS digests (
                date TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS wishlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.commit()
    except Exception:
        pass
    # migration for thumbnail column
    try:
        conn.execute("ALTER TABLE games ADD COLUMN thumbnail TEXT")
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE games ADD COLUMN wishlist_notified_at TEXT")
        conn.commit()
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE games ADD COLUMN category TEXT")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()
    logger.info("DB initialized at %s", DB_PATH)


def now_iso():
    return datetime.utcnow().isoformat()
