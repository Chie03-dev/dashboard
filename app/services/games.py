import logging
from datetime import datetime, timedelta, timezone

from app.cache import cache_key, get, set
from app.config import CACHE_TTL_GAMES, FETCH_TIMEOUT
from app.db import get_conn, now_iso
from app.http_clients import get_epic_client, get_gamerpower_client

logger = logging.getLogger(__name__)

GAMERPOWER_PATH = "/api/giveaways?platform=pc&sort-by=date"
EPIC_PATH = "/freeGamesPromotions?locale=en-US&country=US&allowCountries=US"


def _parse_gp_date(s):
    if not s or s == "N/A":
        return None
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.isoformat()
        except Exception:
            return None


def fetch_gamerpower():
    out = []
    cache_k = cache_key("games", "gamerpower")
    cached = get(cache_k)
    if cached is not None:
        logger.debug("Cache hit for gamerpower")
        return cached
    try:
        client = get_gamerpower_client()
        r = client.get(GAMERPOWER_PATH)
        data = r.json()
        if not isinstance(data, list):
            return out
        for item in data:
            try:
                if item.get("type") not in (None, "Game"):
                    pass
                out.append(
                    {
                        "source": "gamerpower",
                        "external_id": str(item.get("id")),
                        "title": item.get("title", ""),
                        "platform": item.get("platforms", ""),
                        "url": item.get("open_giveaway_url") or item.get("gamerpower_url"),
                        "thumbnail": item.get("thumbnail") or item.get("image"),
                        "category": item.get("type") or "Game",
                        "end_date": _parse_gp_date(item.get("end_date")),
                    }
                )
            except Exception as e:
                logger.warning("gamerpower item parse error", error=str(e))
        set(cache_k, out, CACHE_TTL_GAMES)
    except Exception as e:
        logger.error("gamerpower fetch failed", error=str(e))
    return out


def _epic_slug(el):
    for key in ("catalogNs",):
        mappings = (el.get(key) or {}).get("mappings") or []
        for m in mappings:
            if m.get("pageSlug"):
                return m["pageSlug"]
    for m in el.get("offerMappings") or []:
        if m.get("pageSlug"):
            return m["pageSlug"]
    return None


def _flatten_promos(groups):
    out = []
    for g in groups or []:
        for po in (g.get("promotionalOffers") or []):
            out.append(po)
    return out


def fetch_epic():
    out = []
    cache_k = cache_key("games", "epic")
    cached = get(cache_k)
    if cached is not None:
        logger.debug("Cache hit for epic")
        return cached
    try:
        client = get_epic_client()
        r = client.get(EPIC_PATH)
        data = r.json()
        elements = (((data.get("data") or {}).get("Catalog") or {}).get("searchStore") or {}).get("elements") or []
        for el in elements:
            try:
                price = ((el.get("price") or {}).get("totalPrice") or {}).get("discountPrice")
                price = 0 if price is None else price
                promos = el.get("promotions") or {}
                current = _flatten_promos(promos.get("promotionalOffers"))
                upcoming = _flatten_promos(promos.get("upcomingPromotionalOffers"))
                has_100 = any(
                    (po.get("discountSetting") or {}).get("discountPercentage") == 100
                    for po in (current + upcoming)
                )
                if not (price == 0 or has_100):
                    continue

                end = None
                hundred_current = [po for po in current if (po.get("discountSetting") or {}).get("discountPercentage") == 100]
                hundred_upcoming = [po for po in upcoming if (po.get("discountSetting") or {}).get("discountPercentage") == 100]
                candidates = hundred_current or (current if price == 0 else []) or hundred_upcoming
                if candidates:
                    end = candidates[0].get("endDate")
                if not end:
                    for lo in (el.get("price") or {}).get("lineOffers") or []:
                        for r in lo.get("appliedRules") or []:
                            if r.get("endDate"):
                                end = r["endDate"]
                                break
                        if end:
                            break
                if not end:
                    end = el.get("expiryDate")
                if end:
                    try:
                        dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
                        end = dt.isoformat()
                    except Exception:
                        pass

                slug = _epic_slug(el)
                url = f"https://store.epicgames.com/en-US/p/{slug}" if slug else None
                thumbnail = None
                for ki in el.get("keyImages") or []:
                    if ki.get("type") in ("OfferImageTall", "Thumbnail", "OfferImageWide"):
                        thumbnail = ki.get("url")
                        break
                offer_type = el.get("offerType") or "BASE_GAME"
                category_map = {"BASE_GAME": "Game", "ADD_ON": "DLC", "BUNDLE": "Bundle"}
                category = category_map.get(offer_type, offer_type)
                out.append(
                    {
                        "source": "epic",
                        "external_id": str(el.get("id")),
                        "title": el.get("title", ""),
                        "platform": "PC (Epic)",
                        "url": url,
                        "thumbnail": thumbnail,
                        "category": category,
                        "end_date": end,
                    }
                )
            except Exception as e:
                logger.warning("epic item parse error", error=str(e))
        set(cache_k, out, CACHE_TTL_GAMES)
    except Exception as e:
        logger.error("epic fetch failed", error=str(e))
    return out


def fetch_all_games():
    return fetch_gamerpower() + fetch_epic()


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
        # SQLite - use default
    except Exception:
        pass
    from app.config import DEFAULT_TENANT_ID
    return DEFAULT_TENANT_ID


def sync_games():
    from app.services import notifier

    items = fetch_all_games()
    conn = get_conn()
    new_items = []
    try:
        tenant_id = _get_tenant_id(conn)
        for g in items:
            row = conn.execute(
                "SELECT id FROM games WHERE tenant_id = ? AND source = ? AND external_id = ?",
                (tenant_id, g["source"], g["external_id"]),
            ).fetchone()
            if row is None:
                conn.execute(
                    """INSERT INTO games (tenant_id, source, external_id, title, platform, url, thumbnail, category, end_date, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (tenant_id, g["source"], g["external_id"], g["title"], g["platform"], g["url"], g.get("thumbnail"), g.get("category"), g["end_date"], now_iso()),
                )
                new_items.append(g)
            else:
                conn.execute(
                    """UPDATE games SET title=?, platform=?, url=?, thumbnail=?, category=?, end_date=?
                       WHERE tenant_id = ? AND source=? AND external_id=?""",
                    (g["title"], g["platform"], g["url"], g.get("thumbnail"), g.get("category"), g["end_date"], tenant_id, g["source"], g["external_id"]),
                )
        conn.commit()
    finally:
        conn.close()

    for g in new_items:
        try:
            notifier.notify_new_game(g)
        except Exception as e:
            logger.error("notify_new_game failed", error=str(e))
        # mark notified
        try:
            conn = get_conn()
            conn.execute(
                "UPDATE games SET notified_at=? WHERE tenant_id = ? AND source=? AND external_id=?",
                (now_iso(), tenant_id, g["source"], g["external_id"]),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("mark notified failed", error=str(e))

    # wishlist matches
    try:
        conn = get_conn()
        names = [r["name"] for r in conn.execute("SELECT name FROM wishlist WHERE tenant_id = ?", (tenant_id,)).fetchall()]
        if names:
            rows = conn.execute(
                "SELECT source, external_id, title, platform, url, end_date, wishlist_notified_at FROM games WHERE tenant_id = ?",
                (tenant_id,),
            ).fetchall()
            for row in rows:
                if row["wishlist_notified_at"]:
                    continue
                title_l = (row["title"] or "").lower()
                if any(n.lower() in title_l for n in names):
                    game = {
                        "source": row["source"],
                        "external_id": row["external_id"],
                        "title": row["title"],
                        "platform": row["platform"],
                        "url": row["url"],
                        "end_date": row["end_date"],
                    }
                    notifier.notify_wishlist(game)
                    conn.execute(
                        "UPDATE games SET wishlist_notified_at=? WHERE tenant_id = ? AND source=? AND external_id=?",
                        (now_iso(), tenant_id, row["source"], row["external_id"]),
                    )
            conn.commit()
        conn.close()
    except Exception as e:
        logger.error("wishlist matching failed", error=str(e))

    # reminders
    try:
        _send_reminders(tenant_id)
    except Exception as e:
        logger.error("reminders failed", error=str(e))

    return items


fetch_games = sync_games


def _parse_end(end):
    if not end:
        return None
    try:
        dt = datetime.fromisoformat(str(end).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _send_reminders(tenant_id: str):
    from app.services import notifier
    from app.config import REMINDER_HOURS

    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT source, external_id, title, platform, url, end_date, reminder_sent_at FROM games WHERE tenant_id = ? AND reminder_sent_at IS NULL",
            (tenant_id,),
        ).fetchall()
    finally:
        conn.close()

    now = datetime.now(timezone.utc)
    window = now + timedelta(hours=REMINDER_HOURS)
    for row in rows:
        end = _parse_end(row["end_date"])
        if end is None:
            continue
        if now < end <= window:
            game = {
                "source": row["source"],
                "external_id": row["external_id"],
                "title": row["title"],
                "platform": row["platform"],
                "url": row["url"],
                "end_date": row["end_date"],
            }
            try:
                notifier.notify_reminder(game)
            except Exception as e:
                logger.error("notify_reminder failed", error=str(e))
                continue
            try:
                conn = get_conn()
                conn.execute(
                    "UPDATE games SET reminder_sent_at=? WHERE tenant_id = ? AND source=? AND external_id=?",
                    (now_iso(), tenant_id, row["source"], row["external_id"]),
                )
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error("mark reminder failed", error=str(e))