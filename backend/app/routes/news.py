# backend/app/routes/news.py
"""
GET /api/news?company=<name>&limit=6
Returns recent news articles for a company via NewsAPI.
Returns [] when NEWS_API_KEY is not configured.
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.news import get_company_news

router = APIRouter()


class NewsItem(BaseModel):
    title:        str
    url:          str
    source:       str
    published_at: str
    description:  str


@router.get("/news", response_model=list[NewsItem])
async def company_news(company: str, limit: int = 6):
    return await get_company_news(company.strip(), max_results=min(limit, 10))
