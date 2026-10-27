from fastapi import APIRouter, Query, Depends

from app.auth import get_current_tenant
from app.db import get_conn
from app.services.deals import fetch_deals
from app.services.weather import fetch_weather

router = APIRouter()


@router.get("/dev")
def list_dev(tenant_id: str = Depends(get_current_tenant)):
    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM dev_items WHERE tenant_id = ? ORDER BY fetched_at DESC",
            (tenant_id,),
        ).fetchall()]
    finally:
        conn.close()
    return rows


@router.get("/deals")
def deals(tenant_id: str = Depends(get_current_tenant)):
    return fetch_deals()


@router.get("/weather")
def weather(lat: float = Query(40.7128), lon: float = Query(-74.0060), tenant_id: str = Depends(get_current_tenant)):
    return fetch_weather(lat, lon)
