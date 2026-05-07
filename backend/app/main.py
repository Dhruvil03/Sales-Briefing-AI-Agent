from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.auth           import router as auth_router
from app.routes.health         import router as health_router
from app.routes.summarize      import router as summarize_router
from app.routes.company        import router as company_router
from app.routes.upload         import router as upload_router       # legacy
from app.routes.prospect       import router as prospect_router     # new
from app.routes.report         import router as report_router
from app.routes.history        import router as history_router
from app.routes.followup       import router as followup_router
from app.routes.ingest         import router as ingest_router
from app.routes.ingest_read    import router as ingest_read_router
from app.routes.embed          import router as embed_router
from app.routes.search         import router as search_router
from app.routes.pinecone_search import router as pinecone_search_router
from app.routes.news            import router as news_router
from app.routes.batch           import router as batch_router
from app.routes.icp             import router as icp_router
from app.routes.export          import router as export_router
from app.routes.transcript      import router as transcript_router

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

app = FastAPI(title="Sales Copilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin"],
)

# ── routes ────────────────────────────────────────────────────────────────────

app.include_router(auth_router,            prefix="/api")
app.include_router(health_router,          prefix="/api")
app.include_router(summarize_router,       prefix="/api")
app.include_router(company_router,         prefix="/api")
app.include_router(upload_router,          prefix="/api")   # legacy: /api/prospect/upload
app.include_router(prospect_router,        prefix="/api")   # new:    /api/research/prospect
app.include_router(report_router,          prefix="/api")
app.include_router(history_router,         prefix="/api")
app.include_router(followup_router,        prefix="/api")
app.include_router(ingest_router,          prefix="/api")
app.include_router(ingest_read_router,     prefix="/api")
app.include_router(embed_router,           prefix="/api")
app.include_router(search_router,          prefix="/api")
app.include_router(pinecone_search_router, prefix="/api")
app.include_router(news_router,            prefix="/api")
app.include_router(batch_router,           prefix="/api")
app.include_router(icp_router,             prefix="/api")
app.include_router(export_router,          prefix="/api")
app.include_router(transcript_router,      prefix="/api")
