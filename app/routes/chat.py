
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

router = APIRouter()


class ChatIn(BaseModel):
    messages: list[dict]
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    system_prompt: str | None = None
    timeout: int | None = None


def resolve_llm(base_url=None, api_key=None, model=None):
    return (
        base_url or LLM_BASE_URL,
        (api_key if api_key is not None else LLM_API_KEY) or "",
        model or LLM_MODEL,
    )


@router.post("/chat")
def chat(payload: ChatIn):
    try:
        from openai import OpenAI

        base_url, api_key, model = resolve_llm(payload.base_url, payload.api_key, payload.model)
        client = OpenAI(base_url=base_url, api_key=api_key or "dummy")
        messages = list(payload.messages or [])
        if payload.system_prompt:
            messages = [{"role": "system", "content": payload.system_prompt}] + messages
        kwargs = {"model": model, "messages": messages, "timeout": payload.timeout or 60}
        if payload.temperature is not None:
            kwargs["temperature"] = payload.temperature
        if payload.max_tokens is not None:
            kwargs["max_tokens"] = payload.max_tokens
        resp = client.chat.completions.create(**kwargs)
        return {"reply": resp.choices[0].message.content or ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
