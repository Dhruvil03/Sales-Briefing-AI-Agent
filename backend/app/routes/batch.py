# backend/app/routes/batch.py
"""
POST /api/batch         — upload CSV → start background batch research
GET  /api/batch/{id}   — poll batch status + per-row progress
DELETE /api/batch/{id} — delete batch + all rows
"""
from __future__ import annotations

import asyncio
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_session as get_db_session
from app.models import BatchJob, BatchRow, User
from app.services.auth import get_optional_user
from app.services.batch_runner import run_batch_row

router = APIRouter()


# ── Response models ───────────────────────────────────────────────────────────

class BatchRowOut(BaseModel):
    id:            int
    row_index:     int
    prospect_name: str | None
    company_name:  str | None
    company_url:   str | None
    status:        str
    session_id:    int | None
    error_msg:     str | None

    class Config:
        from_attributes = True


class BatchJobOut(BaseModel):
    id:         int
    status:     str
    total_rows: int
    created_at: str
    rows:       list[BatchRowOut]

    class Config:
        from_attributes = True


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_csv(content: bytes) -> list[dict]:
    """
    Parse a CSV with flexible column detection.
    Recognised columns (case-insensitive):
      name / prospect / prospect_name
      company / company_name
      url / website / company_url
    Returns a list of dicts with keys: name, company, url
    """
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row")

    cols = {c.lower().strip(): c for c in reader.fieldnames}

    def _col(*candidates: str) -> str | None:
        for c in candidates:
            if c in cols:
                return cols[c]
        return None

    name_col    = _col("name", "prospect", "prospect_name", "full_name")
    company_col = _col("company", "company_name", "organization")
    url_col     = _col("url", "website", "company_url", "domain")

    if not name_col and not company_col:
        raise ValueError(
            "CSV must have a 'name' column and/or a 'company' column. "
            f"Found columns: {list(reader.fieldnames)}"
        )

    rows = []
    for row in reader:
        name    = row[name_col].strip()    if name_col    and row.get(name_col)    else ""
        company = row[company_col].strip() if company_col and row.get(company_col) else ""
        url     = row[url_col].strip()     if url_col     and row.get(url_col)     else ""

        # Skip completely empty rows
        if not name and not company and not url:
            continue

        # Normalise URL
        if url and not url.startswith("http"):
            url = "https://" + url

        rows.append({"name": name, "company": company, "url": url})

    return rows


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/batch", response_model=BatchJobOut)
async def upload_batch(
    file: UploadFile = File(...),
    db:   AsyncSession = Depends(get_db_session),
    user: User | None  = Depends(get_optional_user),
):
    """
    Upload a CSV file with columns: name, company, url (any order, flexible names).
    Returns a BatchJob with all rows queued. Research runs in the background.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "File must be a .csv")

    content = await file.read()
    if len(content) > 1_000_000:  # 1 MB limit
        raise HTTPException(400, "CSV must be under 1 MB")

    try:
        parsed = _parse_csv(content)
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    if not parsed:
        raise HTTPException(400, "CSV contains no data rows")
    if len(parsed) > 100:
        raise HTTPException(400, "CSV must have at most 100 rows per batch")

    # Create BatchJob
    job = BatchJob(
        user_id=user.id if user else None,
        status="running",
        total_rows=len(parsed),
    )
    db.add(job)
    await db.flush()

    # Create BatchRow records
    rows: list[BatchRow] = []
    for i, p in enumerate(parsed):
        row = BatchRow(
            batch_id=job.id,
            row_index=i,
            prospect_name=p["name"]    or None,
            company_name= p["company"] or None,
            company_url=  p["url"]     or None,
            status="queued",
        )
        db.add(row)
        rows.append(row)

    await db.commit()
    await db.refresh(job)
    for r in rows:
        await db.refresh(r)

    # Launch background tasks (one per row, with concurrency cap of 3)
    async def _run_with_semaphore(sem: asyncio.Semaphore, row_id: int) -> None:
        async with sem:
            await run_batch_row(job.id, row_id)

    sem = asyncio.Semaphore(3)
    for r in rows:
        asyncio.create_task(_run_with_semaphore(sem, r.id))

    return BatchJobOut(
        id=job.id,
        status=job.status,
        total_rows=job.total_rows,
        created_at=job.created_at.isoformat(),
        rows=[
            BatchRowOut(
                id=r.id,
                row_index=r.row_index,
                prospect_name=r.prospect_name,
                company_name=r.company_name,
                company_url=r.company_url,
                status=r.status,
                session_id=r.session_id,
                error_msg=r.error_msg,
            )
            for r in rows
        ],
    )


@router.get("/batch/{batch_id}", response_model=BatchJobOut)
async def get_batch(
    batch_id: int,
    db: AsyncSession = Depends(get_db_session),
    user: User | None = Depends(get_optional_user),
):
    res = await db.execute(select(BatchJob).where(BatchJob.id == batch_id))
    job: BatchJob | None = res.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Batch not found")

    rows_res = await db.execute(
        select(BatchRow).where(BatchRow.batch_id == batch_id).order_by(BatchRow.row_index)
    )
    rows = rows_res.scalars().all()

    return BatchJobOut(
        id=job.id,
        status=job.status,
        total_rows=job.total_rows,
        created_at=job.created_at.isoformat(),
        rows=[
            BatchRowOut(
                id=r.id,
                row_index=r.row_index,
                prospect_name=r.prospect_name,
                company_name=r.company_name,
                company_url=r.company_url,
                status=r.status,
                session_id=r.session_id,
                error_msg=r.error_msg,
            )
            for r in rows
        ],
    )


@router.delete("/batch/{batch_id}", status_code=204)
async def delete_batch(
    batch_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    res = await db.execute(select(BatchJob).where(BatchJob.id == batch_id))
    job = res.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Batch not found")
    await db.delete(job)
    await db.commit()
