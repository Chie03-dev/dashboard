import logging
from datetime import date

from openai import OpenAI

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from app.db import get_conn, now_iso

logger = logging.getLogger(__name__)


def _client():
    return OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY or "dummy")


def _gather_context():
    conn = get_conn()
    try:
        games = [dict(r) for r in conn.execute("SELECT title, platform, end_date FROM games ORDER BY created_at DESC LIMIT 30").fetchall()]
        dev = [dict(r) for r in conn.execute("SELECT title, source FROM dev_items ORDER BY fetched_at DESC LIMIT 30").fetchall()]
    finally:
        conn.close()
    return games, dev


def _fallback(games, dev):
    lines = ["Daily digest (LLM unavailable):", "", "Free games:"]
    for g in games[:15]:
        lines.append(f"- {g.get('title')} ({g.get('platform')})")
    lines.append("")
    lines.append("Dev feed:")
    for d in dev[:15]:
        lines.append(f"- {d.get('title')} [{d.get('source')}]")
    return "\n".join(lines)


def build_digest():
    today = date.today().isoformat()
    games, dev = _gather_context()
    text = None
    if LLM_API_KEY:
        try:
            client = _client()
            prompt = (
                "Create a concise daily digest for a personal dashboard. "
                "Summarize free games available and notable dev/HN/GitHub items. "
                "Keep under 200 words.\n\n"
                f"Free games: {games}\n\nDev items: {dev}"
            )
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                timeout=60,
            )
            text = resp.choices[0].message.content
        except Exception as e:
            logger.error("llm digest failed: %s", e)
            text = None
    if not text:
        text = _fallback(games, dev)

    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO digests (date, text, created_at) VALUES (?,?,?) ON CONFLICT(date) DO UPDATE SET text=excluded.text, created_at=excluded.created_at",
            (today, text, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return text


def get_digest():
    today = date.today().isoformat()
    conn = get_conn()
    try:
        row = conn.execute("SELECT text FROM digests WHERE date=?", (today,)).fetchone()
        if row:
            return {"date": today, "text": row["text"]}
    finally:
        conn.close()
    # build
    text = build_digest()
    return {"date": today, "text": text}
