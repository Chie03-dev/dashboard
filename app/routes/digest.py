from fastapi import APIRouter

from app.services.ai import get_digest

router = APIRouter()


@router.get("/digest")
def digest():
    return get_digest()
