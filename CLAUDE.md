# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the project

### Infrastructure (PostgreSQL + Redis)
```bash
cd infra && docker-compose up -d
```

### Backend
```bash
cd backend
.venv/bin/python3 -m uvicorn app.main:app --reload --port 8000
# Note: always use the full venv path — pyenv shims override shell activation
```

First-time setup:
```bash
cd backend
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY and JWT_SECRET
.venv/bin/python3 app/create_tables.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev        # http://localhost:5173
npm run build
npm run lint
```

## Architecture

### Tech stack
- **Backend**: FastAPI + SQLAlchemy async + PostgreSQL (asyncpg) + Redis
- **LLM**: Groq API (llama-3.3-70b-versatile) — streaming via SSE
- **Embeddings**: SentenceTransformer `all-MiniLM-L6-v2` — runs locally via PyTorch
- **Vector store**: PostgreSQL JSON column (primary) + Pinecone (optional, wired in automatically when `PINECONE_API_KEY` is set)
- **Frontend**: React 19 + Vite + Tailwind CSS v4 + react-router-dom v7

### Request flow — all AI features follow the same SSE pattern
```
React page
  → fetch() POST with JSON body
  → FastAPI route validates input (Pydantic)
  → web scrape / search (httpx + trafilatura / ddgs)
  → stream LLM tokens via Groq API
  → persist to PostgreSQL
  → return StreamingResponse (text/event-stream)
Frontend useStream hook
  → reads SSE events: status | meta | token | done | error
  → accumulates tokens into content string
  → returns { content, meta } to caller
```

### SSE event protocol (`backend/app/services/sse.py`)
```
{"type":"status","data":"message"}   — progress update
{"type":"meta",  "data":{...}}       — metadata (session_id, source_id, etc.)
{"type":"token", "data":"text"}      — LLM output token
{"type":"done"}                      — stream finished
{"type":"error", "data":"message"}   — terminal error
```

**Critical rule**: the async generator in each route MUST `yield` a status event before any blocking I/O. FastAPI won't send a 200 OK until the first yield.

### RAG pipeline
Embeddings run in a background `asyncio.create_task()` — NOT in the request path — because PyTorch holds the GIL during CPU inference and would freeze the event loop.

```
prospect research completes
  → asyncio.create_task(_embed_source_in_background)
  → chunks text (900 chars, 120-char overlap)
  → SentenceTransformer embeddings via run_in_executor
  → saves to chunks.embedding (JSON float list) in PostgreSQL
  → if PINECONE_API_KEY set: also upserts to Pinecone

history/search query
  → embeds query text
  → tries Pinecone first (if configured), falls back to local dot-product
  → groups by session, returns top-k with excerpt
```

### Auth
- JWT (HS256, 30-day expiry) via `python-jose`
- Passwords hashed with `bcrypt` directly (not passlib — incompatible with bcrypt 4.x)
- Two FastAPI dependencies: `get_current_user` (raises 401) and `get_optional_user` (returns None)
- Frontend stores `{user_id, email, full_name, token}` in `localStorage` as `sc_auth`
- `useStream.ts` reads `sc_auth` and attaches `Authorization: Bearer <token>` to every request

### Caching (Redis)
- Company website text: `company_text:<url>` — 24h TTL
- Prospect search results: `prospect_search:<name>:<company>` — 12h TTL
- Cache is silently skipped when Redis is unavailable (graceful degradation)

### Database models (`backend/app/models.py`)
```
ResearchSession          — top-level entity per (company + prospect) pair
  ├── CompanyResearch    — crawled text + LLM summary
  ├── ProspectResearch   — DDG search results + LLM insights + source_id → RAG
  ├── PreCallReport      — LLM pre-call briefing
  ├── CallNotes          — rep's post-call notes
  └── FollowUpEmail      — LLM-generated follow-up email

Source                   — scraped web resource (raw_text)
  └── Chunk              — fixed-size segments with embedding vector (JSON)

User                     — auth user (email + bcrypt hash)
```

### Key files

| File | Purpose |
|---|---|
| `backend/app/main.py` | FastAPI app, CORS, all router includes |
| `backend/app/routes/company.py` | POST /api/company/summary — crawl + summarize |
| `backend/app/routes/prospect.py` | POST /api/research/prospect — DDG search + profile |
| `backend/app/routes/history.py` | GET/DELETE/PATCH /api/history/* + semantic search |
| `backend/app/routes/followup.py` | POST /api/sessions/{id}/followup — follow-up email |
| `backend/app/routes/auth.py` | POST /api/auth/signup|login, GET /api/auth/me |
| `backend/app/services/auth.py` | JWT + bcrypt utilities + FastAPI dependencies |
| `backend/app/services/cache.py` | Redis async wrapper (graceful no-op when Redis down) |
| `backend/app/services/embeddings.py` | SentenceTransformer wrapper |
| `backend/app/services/vector_store.py` | Pinecone client + upsert/query |
| `backend/app/services/prospect_search.py` | DuckDuckGo search + scrape pipeline |
| `frontend/src/hooks/useStream.ts` | SSE consumer hook — returns {content, meta} |
| `frontend/src/context/AuthContext.tsx` | Auth state + localStorage persistence |
| `frontend/src/pages/Research.tsx` | 3-step wizard: Company → Prospect → Report |
| `frontend/src/pages/History.tsx` | Session list + semantic search + outcome picker |
| `frontend/src/lib/exportPdf.ts` | DOM-based PDF export via window.print() |

## Adding a new feature

1. Create `backend/app/routes/feature.py` — Pydantic input model + async route
2. Register with `app.include_router(router, prefix="/api")` in `main.py`
3. If streaming: follow the SSE pattern — first yield before any I/O
4. Add page under `frontend/src/pages/` + route in `App.tsx`
5. Use `useStream` hook for SSE endpoints

## Known gotchas

- **Always run uvicorn via `.venv/bin/python3 -m uvicorn`** — pyenv shims override shell venv activation and the reloader subprocess picks the wrong Python
- **`asyncio.create_task()` not `BackgroundTasks`** for tasks inside StreamingResponse generators — FastAPI checks for background tasks before the generator runs
- **`bcrypt` used directly** — `passlib` raises `ValueError` with bcrypt >= 4.0 during its wrap-bug detection
- **Search route before path param route** — `GET /api/history/search` must be defined before `GET /api/history/{session_id}` or FastAPI tries to cast "search" as an integer
