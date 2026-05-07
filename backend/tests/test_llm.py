# backend/tests/test_llm.py
"""
Smoke test for the LLM service.

Run with:
  cd backend
  source .venv/bin/activate
  python -m pytest tests/test_llm.py -v -s
"""
import asyncio
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


@pytest.mark.asyncio
async def test_complete_returns_string():
    from app.services.llm import complete
    result = await complete("Reply with only the word PONG and nothing else.")
    assert isinstance(result, str)
    assert len(result) > 0
    print(f"\nResponse: {result!r}")


@pytest.mark.asyncio
async def test_stream_yields_tokens():
    from app.services.llm import stream_completion
    tokens = []
    async for token in stream_completion("Count from 1 to 3, one number per line."):
        tokens.append(token)
    full = "".join(tokens)
    assert len(tokens) > 1, "Expected multiple streaming tokens"
    assert len(full) > 0
    print(f"\nToken count: {len(tokens)}")
    print(f"Full output: {full!r}")
