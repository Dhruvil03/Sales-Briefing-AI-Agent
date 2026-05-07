# backend/app/services/prospect_search.py
"""
Prospect research via public web sources.

Flow:
  1. Two DuckDuckGo searches (general + content-focused)
  2. Concurrent async scraping of top non-blocked URLs
  3. Aggregate into a single text blob with source attribution

No LinkedIn. No Twitter. No login-walled sites.
Only public, freely-scrapable content.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
import trafilatura

TAVILY_API_KEY    = os.getenv("TAVILY_API_KEY", "")
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")

# Domains that require login or actively block scrapers
_BLOCKED_DOMAINS = frozenset({
    "linkedin.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "youtube.com",
    "reddit.com",
    "glassdoor.com",
    "indeed.com",
    "ziprecruiter.com",
    "angel.co",
    "wellfound.com",
})

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}
_TIMEOUT = httpx.Timeout(15.0, connect=10.0)

# Minimum extracted text length to be worth keeping
_MIN_CHARS = 200


@dataclass
class ProspectData:
    name: str
    company_name: str
    sources_searched: list[str] = field(default_factory=list)
    aggregated_text: str = ""

    @property
    def total_chars(self) -> int:
        return len(self.aggregated_text)

    @property
    def is_empty(self) -> bool:
        return self.total_chars < 100


# ── helpers ───────────────────────────────────────────────────────────────────

def _is_blocked(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
        return any(
            host == d or host.endswith("." + d)
            for d in _BLOCKED_DOMAINS
        )
    except Exception:
        return True


async def _tavily_search(query: str, n: int) -> list[dict]:
    """Tavily search — better quality than DDG for named individuals."""
    if not TAVILY_API_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            r = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key":        TAVILY_API_KEY,
                    "query":          query,
                    "search_depth":   "basic",
                    "max_results":    n,
                    "exclude_domains": list(_BLOCKED_DOMAINS),
                },
            )
            r.raise_for_status()
            results = r.json().get("results", [])
            # Normalize to same shape as DDG results
            return [
                {"href": r["url"], "title": r["title"], "body": r.get("content", "")}
                for r in results
            ]
    except Exception as exc:
        print(f"[prospect_search] Tavily failed, will fall back to DDG: {repr(exc)}")
        return []


def _ddg_search_sync(query: str, max_results: int) -> list[dict]:
    """Synchronous DDG search — always call via run_in_executor."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # type: ignore[no-redef]
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as exc:
        print(f"[prospect_search] DDG failed for {query!r}: {repr(exc)}")
        return []


async def _fetch_and_extract(url: str) -> tuple[str, str]:
    """
    Fetch a URL and extract readable text with Trafilatura.
    Returns (url, text). Returns (url, '') on any failure.
    """
    if _is_blocked(url):
        return url, ""
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=_TIMEOUT,
            headers=_HEADERS,
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
            text = trafilatura.extract(r.text, favor_recall=True) or ""
            return url, text
    except Exception as exc:
        print(f"[prospect_search] Scrape failed for {url}: {repr(exc)}")
        return url, ""


async def _firecrawl_scrape(url: str) -> str:
    """
    Scrape a URL via Firecrawl API (500 pages/month free).
    Returns clean markdown text or '' on failure.
    """
    if not FIRECRAWL_API_KEY:
        return ""
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0)) as client:
            r = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {FIRECRAWL_API_KEY}"},
                json={"url": url, "formats": ["markdown"]},
            )
            r.raise_for_status()
            return r.json().get("data", {}).get("markdown", "")
    except Exception as exc:
        print(f"[prospect_search] Firecrawl failed for {url}: {repr(exc)}")
        return ""


# ── public API ────────────────────────────────────────────────────────────────

async def search_and_scrape(
    name: str,
    company_name: str,
    extra_context: str | None = None,
    cached_text: str | None = None,
    linkedin_url: str | None = None,
) -> ProspectData:
    """
    Search DuckDuckGo for the prospect, scrape the top results,
    and return aggregated text with source attribution.

    If cached_text is provided (from Redis), skip the web search entirely
    and return a ProspectData built from the cached content.

    extra_context (rep-provided) is always included as the highest-priority source.
    linkedin_url (optional) is scraped via Firecrawl for richer prospect data.
    """
    # ── Fast path: cache hit ──────────────────────────────────────────────────
    if cached_text:
        parts: list[str] = []
        if extra_context and extra_context.strip():
            parts.append(f"[DIRECT CONTEXT — provided by rep]\n{extra_context.strip()}")
        parts.append(cached_text)
        return ProspectData(
            name=name,
            company_name=company_name,
            sources_searched=["(cached)"],
            aggregated_text="\n\n---\n\n".join(parts),
        )

    loop = asyncio.get_event_loop()

    # Two query variants — cast a wide net
    q_general = f'"{name}" "{company_name}"'
    q_content  = f'"{name}" {company_name} interview OR article OR blog OR talk OR speaker'

    # Try Tavily first (better quality), fall back to DDG
    async def _search(query: str, n: int) -> list[dict]:
        # Tavily (async, no GIL issue)
        if TAVILY_API_KEY:
            results = await _tavily_search(query, n)
            if results:
                return results

        # DDG fallback (sync, run in executor)
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, _ddg_search_sync, query, n),
                timeout=15,
            )
        except (asyncio.TimeoutError, Exception) as exc:
            print(f"[prospect_search] DDG search timed out / failed: {repr(exc)}")
            return []

    results_a, results_b = await asyncio.gather(
        _search(q_general, 4),
        _search(q_content, 3),
    )

    all_results = results_a + results_b

    # Deduplicate URLs, preserve order
    seen: set[str] = set()
    candidate_urls: list[str] = []
    for r in all_results:
        url = r.get("href", "")
        if url and url not in seen:
            seen.add(url)
            candidate_urls.append(url)

    # Scrape up to 7 URLs concurrently
    scraped: list[tuple[str, str]] = await asyncio.gather(
        *[_fetch_and_extract(url) for url in candidate_urls[:7]]
    )

    # ── Firecrawl LinkedIn scrape (if provided + API key set) ────────────────
    linkedin_text = ""
    if linkedin_url and linkedin_url.strip():
        linkedin_text = await _firecrawl_scrape(linkedin_url.strip())

    # ── Build aggregated text ─────────────────────────────────────────────────
    parts: list[str] = []
    good_sources: list[str] = []

    # 1. Rep-provided context is highest priority
    if extra_context and extra_context.strip():
        parts.append(f"[DIRECT CONTEXT — provided by rep]\n{extra_context.strip()}")

    # 1b. LinkedIn profile (Firecrawl) — very high quality signal
    if linkedin_text and len(linkedin_text) >= _MIN_CHARS:
        parts.append(f"[LINKEDIN PROFILE — via Firecrawl]\n{linkedin_text[:5_000]}")
        good_sources.append(linkedin_url)  # type: ignore[arg-type]

    # 2. DDG search snippets — light signal, always include
    snippets = [
        f"- {r.get('title','').strip()}: {r.get('body','').strip()}"
        for r in all_results[:5]
        if r.get("body", "").strip()
    ]
    if snippets:
        parts.append("[SEARCH SNIPPETS — brief summaries from web search]\n" + "\n".join(snippets))

    # 3. Full scraped content from pages that had enough text
    for url, text in scraped:
        if len(text) >= _MIN_CHARS:
            domain = urlparse(url).hostname or url
            # Cap each source at 4 000 chars to stay balanced
            parts.append(f"[SOURCE: {domain}]\n{text[:4_000]}")
            good_sources.append(url)

    return ProspectData(
        name=name,
        company_name=company_name,
        sources_searched=good_sources,
        aggregated_text="\n\n---\n\n".join(parts),
    )
