from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

router = APIRouter()


from typing import Optional

class ChatIn(BaseModel):
    messages: list[dict]
    model: Optional[str] = None


@router.post("/chat")
def chat(payload: ChatIn):
    try:
        from openai import OpenAI

        client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY or "dummy")
        model = payload.model or LLM_MODEL
        resp = client.chat.completions.create(
            model=model,
            messages=payload.messages,
            timeout=60,
        )
        return {"reply": resp.choices[0].message.content or ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
