import hashlib
import json
import logging
from datetime import date
from typing import Optional

from openai import OpenAI

from app.cache import cache_key, get, set
from app.config import (
    CACHE_TTL_DIGEST,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL_FALLBACK_CHAIN,
    LLM_SEMANTIC_CACHE_TTL,
    LLM_TOKEN_BUDGET_PER_TENANT,
)
from app.db import get_conn, now_iso

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


def _check_token_budget(tenant_id: str, estimated_tokens: int) -> bool:
    """Check if tenant has enough token budget remaining for the month."""
    from datetime import datetime
    
    conn = get_conn()
    try:
        # Get current month's token usage
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        row = conn.execute(
            "SELECT COALESCE(SUM(tokens_used), 0) FROM llm_usage WHERE tenant_id = ? AND month_start = ?",
            (tenant_id, month_start),
        ).fetchone()
        current_usage = row[0] if row else 0
        
        if current_usage + estimated_tokens > LLM_TOKEN_BUDGET_PER_TENANT:
            logger.warning(
                "Token budget exceeded for tenant %s: %d/%d",
                tenant_id,
                current_usage + estimated_tokens,
                LLM_TOKEN_BUDGET_PER_TENANT,
            )
            return False
        return True
    finally:
        conn.close()


def _record_token_usage(tenant_id: str, tokens_used: int):
    """Record token usage for budget tracking."""
    from datetime import datetime
    
    conn = get_conn()
    try:
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
        conn.execute(
            """INSERT INTO llm_usage (tenant_id, month_start, tokens_used, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(tenant_id, month_start) DO UPDATE SET tokens_used = tokens_used + ?""",
            (tenant_id, month_start, tokens_used, now_iso(), tokens_used),
        )
        conn.commit()
    finally:
        conn.close()


def _semantic_cache_key(prompt: str) -> str:
    """Generate semantic cache key from prompt."""
    content = json.dumps(prompt, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def _get_semantic_cache(prompt: str) -> Optional[str]:
    """Check semantic cache for similar prompts."""
    cache_k = cache_key("llm_semantic", _semantic_cache_key(prompt))
    return get(cache_k)


def _set_semantic_cache(prompt: str, response: str):
    """Store response in semantic cache."""
    cache_k = cache_key("llm_semantic", _semantic_cache_key(prompt))
    set(cache_k, response, LLM_SEMANTIC_CACHE_TTL)


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


def _call_llm_with_fallback(prompt: str, estimated_tokens: int) -> Optional[str]:
    """Call LLM with model fallback chain."""
    for model in LLM_MODEL_FALLBACK_CHAIN:
        try:
            client = _client()
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                timeout=60,
            )
            text = resp.choices[0].message.content
            usage = getattr(resp, 'usage', None)
            if usage:
                _record_token_usage(_get_tenant_id(get_conn()), usage.total_tokens)
            logger.info("LLM call successful with model: %s", model)
            return text
        except Exception as e:
            logger.warning("LLM model %s failed: %s", model, e)
            continue
    return None


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
        # Check token budget
        estimated_tokens = 500  # rough estimate for digest
        if _check_token_budget(tenant_id, estimated_tokens):
            # Check semantic cache
            prompt = (
                "Create a concise daily digest for a personal dashboard. "
                "Summarize free games available and notable dev/HN/GitHub items. "
                "Keep under 200 words.\n\n"
                f"Free games: {games}\n\nDev items: {dev}"
            )
            cached_response = _get_semantic_cache(prompt)
            if cached_response:
                logger.info("Semantic cache hit for digest")
                text = cached_response
            else:
                text = _call_llm_with_fallback(prompt, estimated_tokens)
                if text:
                    _set_semantic_cache(prompt, text)
        else:
            logger.warning("Token budget exceeded for tenant %s", tenant_id)
    
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
