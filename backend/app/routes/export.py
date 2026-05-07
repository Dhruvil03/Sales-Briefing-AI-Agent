# backend/app/routes/export.py
"""
POST /api/sessions/{id}/export/hubspot  — push session to HubSpot CRM
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import get_session_full
from app.db import get_session as get_db_session
from app.models import User
from app.services.auth import get_current_user
from app.services.hubspot import export_to_hubspot

router = APIRouter()


@router.post("/sessions/{session_id}/export/hubspot")
async def export_hubspot(
    session_id: int,
    db:   AsyncSession = Depends(get_db_session),
    user: User         = Depends(get_current_user),
):
    session = await get_session_full(db, session_id, user_id=user.id)
    if session is None:
        raise HTTPException(404, "Session not found")

    prospect_name = session.prospect_name or "Unknown Prospect"
    company_name  = session.company_name  or "Unknown Company"

    prospect_profile = (
        session.prospect_research.insights
        if session.prospect_research
        else ""
    ) or ""

    if not prospect_profile:
        raise HTTPException(400, "No prospect profile to export. Run prospect research first.")

    company_summary = (
        session.company_research.summary if session.company_research else None
    )
    report_md = session.report.report_md if session.report else None

    try:
        result = await export_to_hubspot(
            prospect_name=prospect_name,
            company_name=company_name,
            prospect_profile=prospect_profile,
            company_url=session.company_url,
            company_summary=company_summary,
            report_md=report_md,
        )
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))

    action     = result.get("action", "created")
    fields_set = result.get("fields_set", [])
    return {
        "ok":         True,
        "contact_id": result["contact_id"],
        "action":     action,
        "fields_set": fields_set,
        "message":    f"Contact {action} · fields: {', '.join(fields_set) or 'name only'}",
    }
