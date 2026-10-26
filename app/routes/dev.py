from fastapi import APIRouter, Query

from app.db import get_conn
from app.services.deals import fetch_deals
from app.services.weather import fetch_weather

router = APIRouter()


@router.get("/dev")
def list_dev():
    conn = get_conn()
    try:
        rows = [dict(r) for r in conn.execute("SELECT * FROM dev_items ORDER BY fetched_at DESC").fetchall()]
    finally:
        conn.close()
    return rows


@router.get("/deals")
def deals():
    return fetch_deals()


@router.get("/weather")
def weather(lat: float = Query(40.7128), lon: float = Query(-74.0060)):
    return fetch_weather(lat, lon)
