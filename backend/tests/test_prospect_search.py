# backend/tests/test_prospect_search.py
"""
Integration smoke test — no DB required.

Tests:
  1. search_and_scrape() finds and scrapes public pages for a well-known person
  2. The LLM generates a non-empty prospect profile from the result

Run:
  cd backend
  source .venv/bin/activate
  python -m pytest tests/test_prospect_search.py -v -s
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import pytest


@pytest.mark.asyncio
async def test_search_returns_data():
    from app.services.prospect_search import search_and_scrape

    # Use a well-known public figure — guaranteed search results
    result = await search_and_scrape(
        name="Sam Altman",
        company_name="OpenAI",
    )

    print(f"\nSources found : {len(result.sources_searched)}")
    print(f"Total chars   : {result.total_chars:,}")
    print(f"Preview       : {result.aggregated_text[:300]!r}")

    assert result.total_chars > 100, "Expected non-empty aggregated text"


@pytest.mark.asyncio
async def test_full_pipeline_no_db():
    """Search + LLM without hitting the database."""
    from app.services.prospect_search import search_and_scrape
    from app.services.llm import complete

    result = await search_and_scrape(
        name="Sam Altman",
        company_name="OpenAI",
        extra_context="He is the CEO. We are pitching an enterprise AI safety audit tool.",
    )

    assert not result.is_empty

    prompt = f"""
Based on this context, give 3 bullet personalization hooks for a sales call.
PROSPECT: Sam Altman at OpenAI
CONTEXT:
{result.aggregated_text[:4000]}
"""
    insights = await complete(prompt)
    print(f"\nInsights preview:\n{insights[:500]}")
    assert len(insights) > 50
