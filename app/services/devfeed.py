import logging

import httpx

from app.config import FETCH_TIMEOUT, GITHUB_TOKEN, HN_LIMIT
from app.db import get_conn, now_iso

logger = logging.getLogger(__name__)

HN_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"
GH_NOTIF = "https://api.github.com/notifications"


def fetch_hn():
    out = []
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT) as c:
            r = c.get(HN_TOP)
            r.raise_for_status()
            ids = r.json() or []
            for sid in ids[:HN_LIMIT]:
                try:
                    ir = c.get(HN_ITEM.format(sid))
                    ir.raise_for_status()
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
                    logger.warning("hn item %s failed: %s", sid, e)
    except Exception as e:
        logger.error("hn fetch failed: %s", e)
    return out


def fetch_github():
    out = []
    if not GITHUB_TOKEN:
        logger.info("GITHUB_TOKEN not set; skipping github notifications")
        return out
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT) as c:
            r = c.get(
                GH_NOTIF,
                headers={
                    "Authorization": f"token {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github+json",
                },
            )
            r.raise_for_status()
            data = r.json() or []
            for n in data:
                try:
                    subject = n.get("subject") or {}
                    title = subject.get("title") or n.get("id")
                    url = subject.get("url")
                    # convert API url to html-ish? keep as is
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
                    logger.warning("github item parse error: %s", e)
    except Exception as e:
        logger.error("github fetch failed: %s", e)
    return out


def fetch_all_dev():
    return fetch_hn() + fetch_github()


def sync_dev():
    items = fetch_all_dev()
    conn = get_conn()
    try:
        for it in items:
            row = conn.execute(
                "SELECT id FROM dev_items WHERE source=? AND external_id=?",
                (it["source"], it["external_id"]),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO dev_items (source, external_id, title, url, fetched_at) VALUES (?,?,?,?,?)",
                    (it["source"], it["external_id"], it["title"], it["url"], now_iso()),
                )
            else:
                conn.execute(
                    "UPDATE dev_items SET title=?, url=?, fetched_at=? WHERE source=? AND external_id=?",
                    (it["title"], it["url"], now_iso(), it["source"], it["external_id"]),
                )
        conn.commit()
    finally:
        conn.close()
    return items

fetch_dev = sync_dev
