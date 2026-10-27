import logging
from datetime import date

from app.cache import cache_key, get, set
from app.config import CACHE_TTL_DIGEST, LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from app.db import get_conn, now_iso
from openai import OpenAI

logger = logging.getLogger(__name__)


def _client():
    return OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY or "dummy")


def _get_tenant_id(conn):
    """Get current tenant_id from connection context."""
    try:
        if hasattr(conn, 'cursor'):
            # PostgreSQL
            with conn.cursor() as cur:
                cur.execute("SELECT current_setting('app.current_tenant', true)")
                result = cur.fetchone()
                if result and result[0]:
                    return result[0]
    except Exception:
        pass
    from app.config import DEFAULT_TENANT_ID
    return DEFAULT_TENANT_ID


def _gather_context(tenant_id: str):
    conn = get_conn()
    try:
        games = [dict(r) for r in conn.execute(
            "SELECT title, platform, end_date FROM games WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 30",
            (tenant_id,),
        ).fetchall()]
        dev = [dict(r) for r in conn.execute(
            "SELECT title, source FROM dev_items WHERE tenant_id = ? ORDER BY fetched_at DESC LIMIT 30",
            (tenant_id,),
        ).fetchall()]
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
    conn = get_conn()
    try:
        tenant_id = _get_tenant_id(conn)
    finally:
        conn.close()

    cache_k = cache_key("digest", today, tenant_id=tenant_id)
    cached = get(cache_k)
    if cached is not None:
        logger.debug("Cache hit for digest")
        return cached

    games, dev = _gather_context(tenant_id)
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
            logger.error("llm digest failed", error=str(e))
            text = None
    if not text:
        text = _fallback(games, dev)

    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO digests (tenant_id, date, text, created_at) 
               VALUES (?, ?, ?, ?) 
               ON CONFLICT(tenant_id, date) DO UPDATE SET text=excluded.text, created_at=excluded.created_at""",
            (tenant_id, today, text, now_iso()),
        )
        conn.commit()
    finally:
        conn.close()

    set(cache_k, text, CACHE_TTL_DIGEST)
    return text


def get_digest():
    today = date.today().isoformat()
    conn = get_conn()
    try:
        tenant_id = _get_tenant_id(conn)
    finally:
        conn.close()

    cache_k = cache_key("digest", today, tenant_id=tenant_id)
    cached = get(cache_k)
    if cached is not None:
        logger.debug("Cache hit for digest (get_digest)")
        return {"date": today, "text": cached}

    conn = get_conn()
    try:
        row = conn.execute("SELECT text FROM digests WHERE tenant_id = ? AND date = ?", (tenant_id, today)).fetchone()
        if row:
            text = row["text"]
            set(cache_k, text, CACHE_TTL_DIGEST)
            return {"date": today, "text": text}
    finally:
        conn.close()
    # build
    text = build_digest()
    return {"date": today, "text": text}
