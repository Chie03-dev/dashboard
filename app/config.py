import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "dashboard.db"))

# PostgreSQL configuration
DATABASE_URL = os.getenv("DATABASE_URL", "")
# Format: postgresql://user:pass@host:port/dbname
# If not set, falls back to SQLite

DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
SMTP_TO = os.getenv("SMTP_TO", SMTP_USER)
NTFY_URL = os.getenv("NTFY_URL", "")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

LLM_API_KEY = (
    os.getenv("LLM_API_KEY")
    or os.getenv("FREELLM_API_KEY")
    or os.getenv("FREE_LLM_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or ""
)
LLM_BASE_URL = (
    os.getenv("LLM_BASE_URL")
    or os.getenv("FREELLM_BASE_URL")
    or os.getenv("FREE_LLM_BASE_URL")
    or "http://localhost:3001/v1"
)
LLM_MODEL = os.getenv("LLM_MODEL") or os.getenv("FREELLM_MODEL") or "auto"

# LLM token budget per tenant (monthly)
LLM_TOKEN_BUDGET_PER_TENANT = int(os.getenv("LLM_TOKEN_BUDGET_PER_TENANT", "100000"))
# Model fallback chain (comma-separated, tried in order)
LLM_MODEL_FALLBACK_CHAIN = os.getenv("LLM_MODEL_FALLBACK_CHAIN", "gpt-3.5-turbo,gpt-4,claude-3-haiku").split(",")
# Semantic cache TTL for LLM prompts
LLM_SEMANTIC_CACHE_TTL = int(os.getenv("LLM_SEMANTIC_CACHE_TTL", "86400"))

FETCH_TIMEOUT = int(os.getenv("FETCH_TIMEOUT", "20"))
SCHEDULER_HOURS = int(os.getenv("SCHEDULER_HOURS", "3"))
HN_LIMIT = int(os.getenv("HN_LIMIT", "15"))
REMINDER_HOURS = float(os.getenv("REMINDER_HOURS", "2"))

REDIS_URL = os.getenv("REDIS_URL", "")
REDIS_ENABLED = os.getenv("REDIS_ENABLED", "true").lower() == "true"

CACHE_TTL_WEATHER = int(os.getenv("CACHE_TTL_WEATHER", "600"))
CACHE_TTL_DEALS = int(os.getenv("CACHE_TTL_DEALS", "3600"))
CACHE_TTL_HN = int(os.getenv("CACHE_TTL_HN", "1800"))
CACHE_TTL_GITHUB = int(os.getenv("CACHE_TTL_GITHUB", "1800"))
CACHE_TTL_DIGEST = int(os.getenv("CACHE_TTL_DIGEST", "86400"))
CACHE_TTL_GAMES = int(os.getenv("CACHE_TTL_GAMES", "1800"))

RATE_LIMIT_GAMERPOWER = int(os.getenv("RATE_LIMIT_GAMERPOWER", "10"))
RATE_LIMIT_EPIC = int(os.getenv("RATE_LIMIT_EPIC", "10"))
RATE_LIMIT_HN = int(os.getenv("RATE_LIMIT_HN", "30"))
RATE_LIMIT_GITHUB = int(os.getenv("RATE_LIMIT_GITHUB", "30"))
RATE_LIMIT_CHEAPSHARK = int(os.getenv("RATE_LIMIT_CHEAPSHARK", "10"))
RATE_LIMIT_OPENMETEO = int(os.getenv("RATE_LIMIT_OPENMETEO", "60"))
RATE_LIMIT_LLM = int(os.getenv("RATE_LIMIT_LLM", "20"))

SYNC_MAX_RETRIES = int(os.getenv("SYNC_MAX_RETRIES", "3"))
SYNC_RETRY_BASE_DELAY = float(os.getenv("SYNC_RETRY_BASE_DELAY", "2.0"))
SYNC_RETRY_MAX_DELAY = float(os.getenv("SYNC_RETRY_MAX_DELAY", "60.0"))

# Celery configuration
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL or "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL or "redis://localhost:6379/0")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60  # 30 minutes
CELERY_TASK_SOFT_TIME_LIMIT = 25 * 60  # 25 minutes
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 100

# Celery Beat schedule (periodic tasks)
CELERY_BEAT_SCHEDULE = {
    "sync-games-every-3-hours": {
        "task": "app.tasks.sync_games_task",
        "schedule": 3 * 60 * 60,  # 3 hours in seconds
        "options": {"queue": "sync"},
    },
    "sync-dev-every-3-hours": {
        "task": "app.tasks.sync_dev_task",
        "schedule": 3 * 60 * 60,
        "options": {"queue": "sync"},
    },
    "build-digest-daily": {
        "task": "app.tasks.build_digest_task",
        "schedule": 24 * 60 * 60,  # Daily at midnight
        "options": {"queue": "sync"},
    },
}

# Auth/JWT
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
JWT_REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Multi-tenant
DEFAULT_TENANT_ID = os.getenv("DEFAULT_TENANT_ID", "00000000-0000-0000-0000-000000000001")
