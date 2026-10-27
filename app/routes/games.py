from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from app.auth import get_current_tenant
from app.db import get_conn
from app.services.games import sync_games

router = APIRouter()


class WishlistIn(BaseModel):
    name: str


def _get_tenant_id():
    """Get tenant_id from current request context."""
    from app.auth import current_tenant_id_var
    return current_tenant_id_var.get()


@router.get("/games")
def list_games(tenant_id: str = Depends(get_current_tenant)):
    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM games WHERE tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall()]
    finally:
        conn.close()
    return rows


@router.post("/refresh")
def refresh(tenant_id: str = Depends(get_current_tenant)):
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
def list_wishlist(tenant_id: str = Depends(get_current_tenant)):
    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM wishlist WHERE tenant_id = ? ORDER BY created_at DESC",
            (tenant_id,),
        ).fetchall()]
    finally:
        conn.close()
    return rows


@router.post("/wishlist")
def add_wishlist(item: WishlistIn, tenant_id: str = Depends(get_current_tenant)):
    name = (item.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO wishlist (tenant_id, name, created_at) VALUES (?, ?, ?)",
            (tenant_id, name, __import__("datetime").datetime.utcnow().isoformat()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "name": name}


@router.delete("/wishlist/{item_id}")
def delete_wishlist(item_id: int, tenant_id: str = Depends(get_current_tenant)):
    conn = get_conn()
    try:
        conn.execute("DELETE FROM wishlist WHERE id = ? AND tenant_id = ?", (item_id, tenant_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
