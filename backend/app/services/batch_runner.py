# backend/app/services/batch_runner.py
"""
Non-streaming research pipeline used by batch CSV upload.

For each BatchRow:
  1. Scrape company website  (httpx + trafilatura, Redis-cached)
  2. Summarize company       (LLM complete(), non-streaming)
  3. Search + scrape prospect (existing search_and_scrape)
  4. Generate prospect insights (LLM complete())
  5. Persist all to DB, update BatchRow status → done / failed
"""
from __future__ import annotations

import trafilatura
import httpx

from app.db import AsyncSessionLocal
from app.models import BatchJob, BatchRow, Source
from app.crud import (
    create_session as crud_create_session,
    upsert_company_research,
    upsert_prospect_research,
    update_session_meta,
)
from app.services.cache import cache
from app.services.llm import complete
from app.services.prospect_search import search_and_scrape
from sqlalchemy import select

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

_COMPANY_PROMPT = """\
Summarize this company's website in 5 concise bullet points.
Cover: what they do, ideal customer, key products/services, pricing signals, tech stack.
Be specific. Avoid generic statements.

COMPANY URL: {url}
WEBSITE CONTENT:
{context}
"""

_PROSPECT_PROMPT = """\
You are a sales intelligence analyst preparing a B2B sales rep for a discovery call.
Based only on the public web content below, build a concise, actionable prospect profile.
Do not invent facts. If something is not in the sources, write "Not found in public sources."

Structure your response with these headings:
**Role & Seniority** | **Background** | **Focus & Interests** | **Likely Pain Points** | **Personalization Hooks**

PROSPECT: {name} at {company_name}
CONTEXT:
{context}
"""


async def _get_or_create_source(db, url: str, raw_text: str) -> Source:
    res = await db.execute(select(Source).where(Source.url == url).limit(1))
    existing = res.scalar_one_or_none()
    if existing:
        return existing
    source = Source(url=url, raw_text=raw_text[:200_000])
    db.add(source)
    await db.flush()
    await db.commit()
    return source


async def run_batch_row(batch_id: int, row_id: int) -> None:
    """
    Process a single BatchRow. Opens its own DB session.
    Updates BatchRow.status to 'running' → 'done' or 'failed'.
    When all rows are done, marks BatchJob.status → 'done' or 'partial'.
    """
    async with AsyncSessionLocal() as db:
        # Load row
        res = await db.execute(select(BatchRow).where(BatchRow.id == row_id))
        row: BatchRow | None = res.scalar_one_or_none()
        if row is None:
            return

        # Mark running
        row.status = "running"
        await db.commit()

        try:
            prospect_name = row.prospect_name or ""
            company_name  = row.company_name  or ""
            company_url   = row.company_url   or ""

            # ── 1. Company scrape (cached) ────────────────────────────────────
            company_text = ""
            company_summary = ""
            source_id: int | None = None

            if company_url:
                cache_key = f"company_text:{company_url}"
                company_text = await cache.get(cache_key) or ""
                if not company_text:
                    try:
                        async with httpx.AsyncClient(
                            follow_redirects=True,
                            timeout=httpx.Timeout(25.0, connect=10.0),
                            headers=_HEADERS,
                        ) as client:
                            r = await client.get(company_url)
                            r.raise_for_status()
                            company_text = trafilatura.extract(r.text, favor_recall=True) or ""
                        if company_text:
                            await cache.set(cache_key, company_text, ttl=86_400)
                    except Exception as exc:
                        print(f"[batch] Company scrape failed for {company_url}: {repr(exc)}")

                if company_text:
                    try:
                        company_summary = await complete(
                            _COMPANY_PROMPT.format(url=company_url, context=company_text[:10_000])
                        )
                    except Exception as exc:
                        print(f"[batch] Company summarize failed: {repr(exc)}")

            # ── 2. Prospect search + scrape ───────────────────────────────────
            prospect_insights = ""
            sources_searched: list[str] = []
            aggregated_text = ""

            if prospect_name and (company_name or company_url):
                cn = company_name or company_url
                try:
                    prospect_data = await search_and_scrape(
                        name=prospect_name,
                        company_name=cn,
                    )
                    aggregated_text  = prospect_data.aggregated_text
                    sources_searched = prospect_data.sources_searched

                    if not prospect_data.is_empty:
                        prospect_insights = await complete(
                            _PROSPECT_PROMPT.format(
                                name=prospect_name,
                                company_name=cn,
                                context=aggregated_text[:10_000],
                            )
                        )
                except Exception as exc:
                    print(f"[batch] Prospect research failed for {prospect_name}: {repr(exc)}")

            # ── 3. Persist to DB ──────────────────────────────────────────────
            session = await crud_create_session(
                db,
                company_url=company_url or None,
                company_name=company_name or None,
                prospect_name=prospect_name or None,
                user_id=None,  # batch rows are not user-scoped individually
            )

            if company_text or company_summary:
                source = await _get_or_create_source(db, company_url or f"batch:{row_id}", company_text)
                source_id = source.id
                await upsert_company_research(
                    db, session.id,
                    raw_text=company_text[:50_000],
                    summary=company_summary,
                    source_id=source_id,
                )

            if aggregated_text or prospect_insights:
                source_key = f"prospect:{prospect_name}:{company_name}".lower().replace(" ", "-")
                p_source = await _get_or_create_source(db, source_key, aggregated_text)
                await upsert_prospect_research(
                    db, session.id,
                    sources_searched=sources_searched,
                    aggregated_text=aggregated_text[:50_000],
                    insights=prospect_insights,
                    source_id=p_source.id,
                )

            # ── 4. Mark row done ──────────────────────────────────────────────
            row.status     = "done"
            row.session_id = session.id
            await db.commit()

        except Exception as exc:
            row.status    = "failed"
            row.error_msg = str(exc)[:900]
            await db.commit()
            print(f"[batch] Row {row_id} failed: {repr(exc)}")

        finally:
            # Check if all rows for this batch are finished
            await _maybe_finalize_batch(db, batch_id)


async def _maybe_finalize_batch(db, batch_id: int) -> None:
    """Mark the BatchJob done/partial once every row is no longer queued/running."""
    res = await db.execute(select(BatchJob).where(BatchJob.id == batch_id))
    job: BatchJob | None = res.scalar_one_or_none()
    if not job:
        return

    rows_res = await db.execute(select(BatchRow).where(BatchRow.batch_id == batch_id))
    rows = rows_res.scalars().all()

    pending = [r for r in rows if r.status in ("queued", "running")]
    if pending:
        return

    failed = [r for r in rows if r.status == "failed"]
    job.status = "partial" if failed else "done"
    await db.commit()
