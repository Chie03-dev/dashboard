import logging

from app.cache import cache_key, get, set
from app.config import CACHE_TTL_GITHUB, CACHE_TTL_HN, GITHUB_TOKEN, HN_LIMIT
from app.db import get_conn, now_iso
from app.http_clients import get_github_client, get_hn_client

logger = logging.getLogger(__name__)

HN_TOP_PATH = "/v0/topstories.json"
HN_ITEM_PATH = "/v0/item/{}.json"
GH_NOTIF_PATH = "/notifications"


def fetch_hn():
    out = []
    cache_k = cache_key("dev", "hn")
    cached = get(cache_k)
    if cached is not None:
        logger.debug("Cache hit for hackernews")
        return cached
    try:
        client = get_hn_client()
        r = client.get(HN_TOP_PATH)
        ids = r.json() or []
        for sid in ids[:HN_LIMIT]:
            try:
                ir = client.get(HN_ITEM_PATH.format(sid))
                item = ir.json() or {}
                if not item.get("title"):
                    continue
                out.append(
                    {
                        "source": "hackernews",
                        "external_id": str(item.get("id")),
                        "title": item.get("title", ""),
                        "url": item.get("url") or f"https://news.ycombinator.com/item?id={item.get('id')}",
                    }
                )
            except Exception as e:
                logger.warning("hn item failed", item_id=sid, error=str(e))
        set(cache_k, out, CACHE_TTL_HN)
    except Exception as e:
        logger.error("hn fetch failed", error=str(e))
    return out


def fetch_github():
    out = []
    if not GITHUB_TOKEN:
        logger.info("GITHUB_TOKEN not set; skipping github notifications")
        return out
    cache_k = cache_key("dev", "github")
    cached = get(cache_k)
    if cached is not None:
        logger.debug("Cache hit for github")
        return cached
    try:
        client = get_github_client()
        r = client.get(
            GH_NOTIF_PATH,
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github+json",
            },
        )
        data = r.json() or []
        for n in data:
            try:
                subject = n.get("subject") or {}
                title = subject.get("title") or n.get("id")
                url = subject.get("url")
                if not url:
                    repo = n.get("repository") or {}
                    url = repo.get("html_url")
                out.append(
                    {
                        "source": "github",
                        "external_id": str(n.get("id")),
                        "title": title,
                        "url": url,
                    }
                )
            except Exception as e:
                logger.warning("github item parse error", error=str(e))
        set(cache_k, out, CACHE_TTL_GITHUB)
    except Exception as e:
        logger.error("github fetch failed", error=str(e))
    return out


def fetch_all_dev():
    return fetch_hn() + fetch_github()


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


def sync_dev():
    items = fetch_all_dev()
    conn = get_conn()
    try:
        tenant_id = _get_tenant_id(conn)
        for it in items:
            row = conn.execute(
                "SELECT id FROM dev_items WHERE tenant_id = ? AND source = ? AND external_id = ?",
                (tenant_id, it["source"], it["external_id"]),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO dev_items (tenant_id, source, external_id, title, url, fetched_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (tenant_id, it["source"], it["external_id"], it["title"], it["url"], now_iso()),
                )
            else:
                conn.execute(
                    "UPDATE dev_items SET title = ?, url = ?, fetched_at = ? WHERE tenant_id = ? AND source = ? AND external_id = ?",
                    (it["title"], it["url"], now_iso(), tenant_id, it["source"], it["external_id"]),
                )
        conn.commit()
    finally:
        conn.close()
    return items


fetch_dev = sync_dev
