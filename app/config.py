import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "dashboard.db"))

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
