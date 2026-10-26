from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_conn
from app.services.games import sync_games

router = APIRouter()


class WishlistIn(BaseModel):
    name: str


@router.get("/games")
def list_games():
    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM games ORDER BY created_at DESC").fetchall()]
    finally:
        conn.close()
    return rows


@router.post("/refresh")
def refresh():
    try:
        sync_games()
    except Exception:
        pass
    from app.services.devfeed import sync_dev
    try:
        sync_dev()
    except Exception:
        pass
    return {"ok": True}


@router.get("/wishlist")
def list_wishlist():
    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM wishlist ORDER BY created_at DESC").fetchall()]
    finally:
        conn.close()
    return rows


@router.post("/wishlist")
def add_wishlist(item: WishlistIn):
    name = (item.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    conn = get_conn()
    try:
        conn.execute("INSERT OR IGNORE INTO wishlist (name, created_at) VALUES (?, ?)", (name, __import__("datetime").datetime.utcnow().isoformat()))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "name": name}


@router.delete("/wishlist/{item_id}")
def delete_wishlist(item_id: int):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM wishlist WHERE id=?", (item_id,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
