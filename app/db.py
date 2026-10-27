import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlparse

from app.config import (
    DB_PATH,
    DB_POOL_MAX,
    DB_POOL_MIN,
    DEFAULT_TENANT_ID,
    EFFECTIVE_DATABASE_URL,
)

logger = logging.getLogger(__name__)

_use_postgres = bool(EFFECTIVE_DATABASE_URL)
_pg_pool: object | None = None


def _get_pg_pool():
    global _pg_pool
    if _pg_pool is None and _use_postgres:
        from psycopg2.pool import ThreadedConnectionPool

        parsed = urlparse(EFFECTIVE_DATABASE_URL)
        _pg_pool = ThreadedConnectionPool(
            minconn=DB_POOL_MIN,
            maxconn=DB_POOL_MAX,
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=parsed.password,
            database=parsed.path.lstrip("/"),
        )
        logger.info("PostgreSQL connection pool created (min=%d, max=%d)", DB_POOL_MIN, DB_POOL_MAX)
    return _pg_pool


def get_conn():
    """Get a database connection (SQLite or PostgreSQL). Caller must close/return it."""
    if _use_postgres:
        pool = _get_pg_pool()
        conn = pool.getconn()
        # Set tenant context for RLS
        tenant_id = get_current_tenant_id()
        if tenant_id:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL app.current_tenant = %s", (tenant_id,))
        return _PgConnectionWrapper(conn, pool)
    else:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn


class _PgConnectionWrapper:
    """Wrapper to return PostgreSQL connection to pool on close."""
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self._closed = False

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        if not self._closed:
            self._pool.putconn(self._conn)
            self._closed = True

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def cursor(self):
        return self._conn.cursor()

    def execute(self, *args, **kwargs):
        return self._conn.execute(*args, **kwargs)

    def executescript(self, *args, **kwargs):
        return self._conn.executescript(*args, **kwargs)

    def fetchone(self, *args, **kwargs):
        return self._conn.fetchone(*args, **kwargs)

    def fetchall(self, *args, **kwargs):
        return self._conn.fetchall(*args, **kwargs)


@contextmanager
def get_conn_ctx() -> Generator:
    """Get a database connection as a context manager."""
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()


def get_current_tenant_id() -> str | None:
    """Get current tenant ID from context variable."""
    from app.auth import current_tenant_id_var
    return current_tenant_id_var.get() or DEFAULT_TENANT_ID


def init_db():
    """Initialize database schema with multi-tenant support."""
    with get_conn() as conn:
        if _use_postgres:
            _init_postgres(conn)
        else:
            _init_sqlite(conn)
    logger.info("DB initialized (%s)", "PostgreSQL" if _use_postgres else f"SQLite at {DB_PATH}")


def _init_postgres(conn):
    """Initialize PostgreSQL schema with RLS."""
    with conn.cursor() as cur:
        # Enable UUID extension
        cur.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

        # Create tenants table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tenants (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                settings JSONB DEFAULT '{}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        # Create users table
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(tenant_id, email)
            )
            """
        )

        # Create games table with tenant_id
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS games (
                id BIGSERIAL PRIMARY KEY,
                tenant_id UUID NOT NULL DEFAULT gen_random_uuid(),
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                platform TEXT,
                url TEXT,
                thumbnail TEXT,
                category TEXT,
                end_date TIMESTAMPTZ,
                notified_at TIMESTAMPTZ,
                reminder_sent_at TIMESTAMPTZ,
                wishlist_notified_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(tenant_id, source, external_id)
            )
            """
        )

        # Create dev_items table with tenant_id
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS dev_items (
                id BIGSERIAL PRIMARY KEY,
                tenant_id UUID NOT NULL DEFAULT gen_random_uuid(),
                source TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT,
                fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(tenant_id, source, external_id)
            )
            """
        )

        # Create digests table with tenant_id
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS digests (
                tenant_id UUID NOT NULL DEFAULT gen_random_uuid(),
                date DATE NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (tenant_id, date)
            )
            """
        )

        # Create llm_usage table for token budget tracking
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS llm_usage (
                tenant_id UUID NOT NULL DEFAULT gen_random_uuid(),
                month_start DATE NOT NULL,
                tokens_used BIGINT NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (tenant_id, month_start)
            )
            """
        )

        # Create wishlist table with tenant_id
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS wishlist (
                id BIGSERIAL PRIMARY KEY,
                tenant_id UUID NOT NULL DEFAULT gen_random_uuid(),
                name TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(tenant_id, name)
            )
            """
        )

        # Create archived tables for history retention
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS games_archive (
                LIKE games INCLUDING ALL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS dev_items_archive (
                LIKE dev_items INCLUDING ALL
            )
            """
        )

        # Enable Row Level Security
        cur.execute("ALTER TABLE games ENABLE ROW LEVEL SECURITY")
        cur.execute("ALTER TABLE dev_items ENABLE ROW LEVEL SECURITY")
        cur.execute("ALTER TABLE digests ENABLE ROW LEVEL SECURITY")
        cur.execute("ALTER TABLE wishlist ENABLE ROW LEVEL SECURITY")
        cur.execute("ALTER TABLE games_archive ENABLE ROW LEVEL SECURITY")
        cur.execute("ALTER TABLE dev_items_archive ENABLE ROW LEVEL SECURITY")

        # Create RLS policies
        _create_rls_policies(cur)

        # Create indexes
        cur.execute("CREATE INDEX IF NOT EXISTS idx_games_tenant_created ON games (tenant_id, created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_games_tenant_end_date ON games (tenant_id, end_date) WHERE end_date IS NOT NULL")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_dev_items_tenant_fetched ON dev_items (tenant_id, fetched_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_digests_tenant_date ON digests (tenant_id, date DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_wishlist_tenant ON wishlist (tenant_id)")

        conn.commit()


def _create_rls_policies(cur):
    """Create Row Level Security policies for tenant isolation."""
    tables = ["games", "dev_items", "digests", "wishlist", "games_archive", "dev_items_archive"]
    for table in tables:
        # Drop existing policy if exists
        cur.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        # Create new policy
        cur.execute(
            f"""
            CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id = current_setting('app.current_tenant')::uuid)
            WITH CHECK (tenant_id = current_setting('app.current_tenant')::uuid)
            """
        )


def _init_sqlite(conn):
    """Initialize SQLite schema (with tenant_id columns for future migration)."""
    # First, create new tables that don't exist
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            settings TEXT DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
            tenant_id TEXT NOT NULL,
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(tenant_id, email)
        );
        CREATE TABLE IF NOT EXISTS games_archive (
            id INTEGER PRIMARY KEY,
            tenant_id TEXT NOT NULL,
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
            archived_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS dev_items_archive (
            id INTEGER PRIMARY KEY,
            tenant_id TEXT NOT NULL,
            source TEXT NOT NULL,
            external_id TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            fetched_at TEXT NOT NULL,
            archived_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS llm_usage (
            tenant_id TEXT NOT NULL,
            month_start TEXT NOT NULL,
            tokens_used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (tenant_id, month_start)
        );
        """
    )
    conn.commit()

    # Migration: add tenant_id columns to existing tables if they don't exist
    _migrate_sqlite_add_tenant_id(conn)

    # Create indexes after migration
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_games_tenant_created ON games (tenant_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_dev_items_tenant_fetched ON dev_items (tenant_id, fetched_at DESC);
        CREATE INDEX IF NOT EXISTS idx_digests_tenant_date ON digests (tenant_id, date DESC);
        CREATE INDEX IF NOT EXISTS idx_wishlist_tenant ON wishlist (tenant_id);
        """
    )
    conn.commit()

    # Insert default tenant if not exists
    try:
        conn.execute(
            "INSERT OR IGNORE INTO tenants (id, name, slug) VALUES (?, ?, ?)",
            (DEFAULT_TENANT_ID, "Default", "default"),
        )
        conn.commit()
    except Exception:
        pass


def _migrate_sqlite_add_tenant_id(conn):
    """Add tenant_id columns to existing tables for multi-tenant support."""
    from app.config import DEFAULT_TENANT_ID

    # Check if games table has tenant_id column
    try:
        cursor = conn.execute("PRAGMA table_info(games)")
        columns = [row[1] for row in cursor.fetchall()]
        if "tenant_id" not in columns:
            logger.info("Adding tenant_id column to games table")
            conn.execute(f"ALTER TABLE games ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}'")
            # Update unique constraint - SQLite doesn't support ALTER COLUMN, so we need to recreate
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_games_tenant_source_ext ON games (tenant_id, source, external_id)")
    except Exception as e:
        logger.warning("Failed to migrate games table: %s", e)

    # Check dev_items table
    try:
        cursor = conn.execute("PRAGMA table_info(dev_items)")
        columns = [row[1] for row in cursor.fetchall()]
        if "tenant_id" not in columns:
            logger.info("Adding tenant_id column to dev_items table")
            conn.execute(f"ALTER TABLE dev_items ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}'")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_dev_items_tenant_source_ext ON dev_items (tenant_id, source, external_id)")
    except Exception as e:
        logger.warning("Failed to migrate dev_items table: %s", e)

    # Check digests table
    try:
        cursor = conn.execute("PRAGMA table_info(digests)")
        columns = [row[1] for row in cursor.fetchall()]
        if "tenant_id" not in columns:
            logger.info("Adding tenant_id column to digests table")
            conn.execute(f"ALTER TABLE digests ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}'")
            # For digests, we need to recreate the primary key
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_digests_tenant_date ON digests (tenant_id, date)")
    except Exception as e:
        logger.warning("Failed to migrate digests table: %s", e)

    # Check wishlist table
    try:
        cursor = conn.execute("PRAGMA table_info(wishlist)")
        columns = [row[1] for row in cursor.fetchall()]
        if "tenant_id" not in columns:
            logger.info("Adding tenant_id column to wishlist table")
            conn.execute(f"ALTER TABLE wishlist ADD COLUMN tenant_id TEXT NOT NULL DEFAULT '{DEFAULT_TENANT_ID}'")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_wishlist_tenant_name ON wishlist (tenant_id, name)")
    except Exception as e:
        logger.warning("Failed to migrate wishlist table: %s", e)

    conn.commit()


def close_pool():
    """Close PostgreSQL connection pool."""
    global _pg_pool
    if _pg_pool:
        _pg_pool.closeall()
        _pg_pool = None
        logger.info("PostgreSQL connection pool closed")


def now_iso():
    return datetime.utcnow().isoformat()


def migrate_sqlite_to_postgres(pg_url: str):
    """Migrate data from SQLite to PostgreSQL."""
    import psycopg2
    from psycopg2.extras import execute_values

    logger.info("Starting SQLite to PostgreSQL migration...")

    # Connect to SQLite
    sqlite_conn = sqlite3.connect(DB_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    # Connect to PostgreSQL
    pg_conn = psycopg2.connect(pg_url)
    pg_conn.autocommit = False

    try:
        with pg_conn.cursor() as pg_cur:
            # Get default tenant ID
            pg_cur.execute("SELECT id FROM tenants WHERE slug = 'default' LIMIT 1")
            row = pg_cur.fetchone()
            if row:
                tenant_id = row[0]
            else:
                pg_cur.execute("INSERT INTO tenants (name, slug) VALUES ('Default', 'default') RETURNING id")
                tenant_id = pg_cur.fetchone()[0]

            # Migrate games
            games = sqlite_conn.execute("SELECT * FROM games").fetchall()
            if games:
                game_data = []
                for g in games:
                    game_data.append((
                        tenant_id,
                        g["source"],
                        g["external_id"],
                        g["title"],
                        g["platform"],
                        g["url"],
                        g["thumbnail"],
                        g["category"],
                        g["end_date"],
                        g["notified_at"],
                        g["reminder_sent_at"],
                        g["wishlist_notified_at"],
                        g["created_at"],
                    ))
                execute_values(pg_cur, """
                    INSERT INTO games (tenant_id, source, external_id, title, platform, url, thumbnail,
                                     category, end_date, notified_at, reminder_sent_at, wishlist_notified_at, created_at)
                    VALUES %s
                    ON CONFLICT (tenant_id, source, external_id) DO NOTHING
                """, game_data)
                logger.info("Migrated %d games", len(games))

            # Migrate dev_items
            dev_items = sqlite_conn.execute("SELECT * FROM dev_items").fetchall()
            if dev_items:
                dev_data = []
                for d in dev_items:
                    dev_data.append((
                        tenant_id,
                        d["source"],
                        d["external_id"],
                        d["title"],
                        d["url"],
                        d["fetched_at"],
                    ))
                execute_values(pg_cur, """
                    INSERT INTO dev_items (tenant_id, source, external_id, title, url, fetched_at)
                    VALUES %s
                    ON CONFLICT (tenant_id, source, external_id) DO NOTHING
                """, dev_data)
                logger.info("Migrated %d dev items", len(dev_items))

            # Migrate digests
            digests = sqlite_conn.execute("SELECT * FROM digests").fetchall()
            if digests:
                digest_data = []
                for d in digests:
                    digest_data.append((
                        tenant_id,
                        d["date"],
                        d["text"],
                        d["created_at"],
                    ))
                execute_values(pg_cur, """
                    INSERT INTO digests (tenant_id, date, text, created_at)
                    VALUES %s
                    ON CONFLICT (tenant_id, date) DO UPDATE SET text = EXCLUDED.text, created_at = EXCLUDED.created_at
                """, digest_data)
                logger.info("Migrated %d digests", len(digests))

            # Migrate wishlist
            wishlist = sqlite_conn.execute("SELECT * FROM wishlist").fetchall()
            if wishlist:
                wish_data = []
                for w in wishlist:
                    wish_data.append((
                        tenant_id,
                        w["name"],
                        w["created_at"],
                    ))
                execute_values(pg_cur, """
                    INSERT INTO wishlist (tenant_id, name, created_at)
                    VALUES %s
                    ON CONFLICT (tenant_id, name) DO NOTHING
                """, wish_data)
                logger.info("Migrated %d wishlist items", len(wishlist))

            pg_conn.commit()
            logger.info("Migration completed successfully")

    except Exception as e:
        pg_conn.rollback()
        logger.error("Migration failed: %s", e)
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()