# backend/app/services/llm.py
"""
LLM abstraction layer.

Reads LLM_PROVIDER from env:
  groq   → Groq cloud API  (free tier, llama-3.3-70b, ~300ms first token)
  ollama → local Ollama     (private, no internet, slower)

Public API — use these two functions everywhere:
  stream_completion(prompt)  → AsyncGenerator[str, None]   (token by token)
  complete(prompt)           → str                          (full response)
"""
from __future__ import annotations

import json
import os
from typing import AsyncGenerator

import httpx

# ── config (read once at import time) ────────────────────────────────────────

LLM_PROVIDER  = os.getenv("LLM_PROVIDER",  "groq")
GROQ_API_KEY  = os.getenv("GROQ_API_KEY",  "")
GROQ_MODEL    = os.getenv("GROQ_MODEL",    "llama-3.3-70b-versatile")
OLLAMA_BASE   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL  = os.getenv("OLLAMA_MODEL",  "llama3:8b")


# ── public API ────────────────────────────────────────────────────────────────

async def stream_completion(prompt: str) -> AsyncGenerator[str, None]:
    """
    Yield text tokens one at a time.
    Use this for SSE streaming endpoints.
    """
    if LLM_PROVIDER == "groq":
        async for token in _stream_groq(prompt):
            yield token
    else:
        async for token in _stream_ollama(prompt):
            yield token


async def complete(prompt: str) -> str:
    """
    Return the full completion as a single string.
    Uses non-streaming API call internally for efficiency.
    """
    if LLM_PROVIDER == "groq":
        return await _complete_groq(prompt)
    return await _complete_ollama(prompt)


# ── Groq ──────────────────────────────────────────────────────────────────────

def _groq_client():
    try:
        from groq import AsyncGroq  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "groq package not installed. Run: pip install groq"
        ) from exc

    if not GROQ_API_KEY or GROQ_API_KEY == "your_groq_api_key_here":
        raise RuntimeError(
            "GROQ_API_KEY is not set. "
            "Get a free key at https://console.groq.com/keys and add it to backend/.env"
        )
    return AsyncGroq(api_key=GROQ_API_KEY)


async def _stream_groq(prompt: str) -> AsyncGenerator[str, None]:
    client = _groq_client()
    stream = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
        max_tokens=2048,
        temperature=0.3,
    )
    async for chunk in stream:
        token = chunk.choices[0].delta.content
        if token:
            yield token


async def _complete_groq(prompt: str) -> str:
    client = _groq_client()
    response = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        stream=False,
        max_tokens=2048,
        temperature=0.3,
    )
    return (response.choices[0].message.content or "").strip()


# ── Ollama ────────────────────────────────────────────────────────────────────

async def _stream_ollama(prompt: str) -> AsyncGenerator[str, None]:
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream(
            "POST",
            f"{OLLAMA_BASE}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": True},
        ) as resp:
            if resp.status_code == 404:
                # Fallback to /api/chat (older Ollama versions)
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE}/api/chat",
                    json={
                        "model": OLLAMA_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "stream": True,
                    },
                ) as chat_resp:
                    chat_resp.raise_for_status()
                    async for line in chat_resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            token = (data.get("message") or {}).get("content", "")
                            if token:
                                yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
                return

            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        yield token
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue


async def _complete_ollama(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(
            f"{OLLAMA_BASE}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        )
        if r.status_code == 404:
            r = await client.post(
                f"{OLLAMA_BASE}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
        r.raise_for_status()
        data = r.json()
    return (
        data.get("response")
        or (data.get("message") or {}).get("content")
        or ""
    ).strip()
