from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx, os

from app.db import get_session
from app.crud import create_run
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

router = APIRouter()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3:8b-instrcut")


class SummarizeBody(BaseModel):
    text: str
    bullets: int = 5

@router.post("/summarize")

# async def summarize(body: SummarizeBody):
async def summarize(body: SummarizeBody, db: AsyncSession = Depends(get_session)):
    prompt = (
        f"Summarize the following text in {body.bullets} bullet points. "
        "Be concise and factual.\n\n" + body.text
    )
    # try:
    #     async with httpx.AsyncClient(timeout=60) as client: 
    #         # Ollama generate API (non-stream)
    #         r = await client.post(
    #             f"{OLLAMA_BASE_URL}/api/generate",
    #             json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
    #         )
    #         r.raise_for_status()
    #         data = r.json()
    #         return {"summary": data.get("response", "").strip()}
    # except httpx.HTTPError as e:
    #     raise HTTPException(status_code=502, detail=f"Model error: {e}")



    try:
            # Try /api/generate first
        async with httpx.AsyncClient(timeout=60) as client: 

            r = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
            )
            if r.status_code == 404:
                # Fall back to /api/chat for Ollama builds without /generate
                r = await client.post(
                    f"{OLLAMA_BASE_URL}/api/chat",
                    json={
                        "model": OLLAMA_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": False,
                    },
                )
            r.raise_for_status()
    except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail="Model server unreachable. Start `ollama serve` on 127.0.0.1:11434.",
            )
    except httpx.ReadTimeout:
            raise HTTPException(
                status_code=504,
                detail="Model timed out while summarizing. Try shorter input.",
            )
    except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=f"Model error: {e.response.text}")

    data = r.json()
    summary = (data.get("response") or data.get("message", {}).get("content") or "").strip()
    if not summary:
        raise HTTPException(status_code=502, detail="Model returned an empty response.")
    # return {"summary": summary}

    # await create_run(db, run_type="summarize", input_text=body.text[:20000], output_text=summary, source=None)
    try:
        await create_run(db, run_type="summarize", input_text=body.text[:20000], output_text=summary, source=None)
    except Exception as e:
        print("Warning: persist failed (summarize):", e)
    return {"summary": summary}