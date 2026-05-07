# backend/app/services/news.py
"""
Company news via NewsAPI (free tier: 100 req/day in dev mode).
Returns [] silently when NEWS_API_KEY is not set.
Sign up at https://newsapi.org (free, no credit card).
"""
from __future__ import annotations

import os
import httpx

NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")


async def get_company_news(company_name: str, max_results: int = 6) -> list[dict]:
    if not NEWS_API_KEY or not company_name.strip():
        return []
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            r = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q":        f'"{company_name}"',
                    "sortBy":   "publishedAt",
                    "pageSize": max_results,
                    "language": "en",
                    "apiKey":   NEWS_API_KEY,
                },
            )
            if not r.is_success:
                return []
            articles = r.json().get("articles", [])
            return [
                {
                    "title":        a["title"],
                    "url":          a["url"],
                    "source":       a["source"]["name"],
                    "published_at": (a.get("publishedAt") or "")[:10],
                    "description":  (a.get("description") or "")[:200],
                }
                for a in articles
                if a.get("title") and "[Removed]" not in a.get("title", "")
            ]
    except Exception as exc:
        print(f"[news] fetch failed: {repr(exc)}")
        return []
