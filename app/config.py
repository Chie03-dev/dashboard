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
