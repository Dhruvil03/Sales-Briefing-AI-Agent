# backend/app/services/sse.py
"""
Server-Sent Events (SSE) helpers.

Protocol — every event is a JSON object:

  {"type": "status", "data": "Searching sources..."}   progress message
  {"type": "meta",   "data": {"session_id": 1, ...}}   metadata (always first)
  {"type": "token",  "data": "Hello "}                 LLM output token
  {"type": "done"}                                      stream finished
  {"type": "error",  "data": "Something went wrong"}   terminal error

Frontend reads these and accumulates "token" events into the full response text.
"""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from app.services.llm import stream_completion


def sse_event(payload: dict[str, Any]) -> str:
    """Encode a single SSE data line. Safe for tokens containing newlines."""
    return f"data: {json.dumps(payload)}\n\n"


def sse_status(message: str) -> str:
    return sse_event({"type": "status", "data": message})


def sse_meta(data: dict[str, Any]) -> str:
    return sse_event({"type": "meta", "data": data})


def sse_token(token: str) -> str:
    return sse_event({"type": "token", "data": token})


def sse_done() -> str:
    return sse_event({"type": "done"})


def sse_error(message: str) -> str:
    return sse_event({"type": "error", "data": message})


async def stream_prompt(
    prompt: str,
    *,
    meta: dict[str, Any] | None = None,
    status: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Convenience generator — yields SSE-encoded events for a single LLM prompt.

    Yields:
      meta event   (if meta provided)
      status event (if status provided)
      token events (from LLM stream)
      done event
      error event  (replaces done on exception)

    Usage:
        async def generate():
            async for chunk in stream_prompt(prompt, meta={"session_id": 1}):
                yield chunk
        return StreamingResponse(generate(), media_type="text/event-stream")
    """
    if meta is not None:
        yield sse_meta(meta)

    if status is not None:
        yield sse_status(status)

    try:
        async for token in stream_completion(prompt):
            yield sse_token(token)
    except RuntimeError as exc:
        # Misconfigured API key — surface clear message
        yield sse_error(str(exc))
        return
    except Exception as exc:
        yield sse_error(f"LLM error: {repr(exc)}")
        return

    yield sse_done()
