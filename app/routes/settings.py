import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from app.routes.chat import resolve_llm

router = APIRouter()


class LLMTestIn(BaseModel):
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    prompt: Optional[str] = None


@router.post("/llm/test")
def test_llm(payload: LLMTestIn):
    base_url, api_key, model = resolve_llm(payload.base_url, payload.api_key, payload.model)
    prompt = (payload.prompt or "Reply with OK.").strip() or "Reply with OK."
    if not api_key:
        return {"ok": False, "latency_ms": 0, "model": model, "error": "API key is required (set in settings or server env)."}
    start = time.perf_counter()
    try:
        from openai import OpenAI

        client = OpenAI(base_url=base_url, api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            timeout=30,
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        served = getattr(resp, "model", None) or model
        return {"ok": True, "latency_ms": latency_ms, "model": served, "error": None}
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        return {"ok": False, "latency_ms": latency_ms, "model": model, "error": str(e)}
