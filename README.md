# Sales Briefing AI Agent

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-v4-38BDF8?logo=tailwindcss&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

A full-stack GenAI tool that automates sales research. Given a company URL and a prospect name, it crawls the web, generates a prospect profile, writes a pre-call briefing, and drafts a follow-up email — all streamed token-by-token in real time.

Built to showcase end-to-end GenAI engineering: streaming LLMs, RAG, vector search, JWT auth, Redis caching, and a production-quality React frontend.

---

## Features

| Feature | Details |
|---|---|
| **Company Research** | Crawls any public website, extracts readable text, streams a bullet-point summary |
| **Prospect Research** | DuckDuckGo search + concurrent scraping, streams a structured prospect profile |
| **Pre-Call Report** | Combines both summaries into a sales briefing with talking points and objection handling |
| **Follow-up Email** | Generates a personalized post-call email from rep's notes + the prospect profile |
| **History Dashboard** | Browse all past sessions, expand to view each output, semantic search across sessions |
| **Semantic Search (RAG)** | Embeddings stored in PostgreSQL (+ optional Pinecone), searched via cosine similarity |
| **Call Outcome Tracking** | Mark sessions as Booked / Follow-up / Not interested / No-show |
| **PDF Export** | One-click "Download PDF" on any report or history entry |
| **Redis Caching** | Company pages cached 24h, prospect searches cached 12h |
| **JWT Auth** | Sign up / log in, all sessions scoped to the authenticated user |

---

## Tech Stack

**Backend**
- FastAPI + SQLAlchemy async + PostgreSQL (asyncpg)
- Groq API — `llama-3.3-70b-versatile` for LLM streaming
- SentenceTransformer `all-MiniLM-L6-v2` — local embeddings via PyTorch
- Pinecone — optional cloud vector store (graceful fallback to local)
- Redis — response caching
- bcrypt + python-jose — auth

**Frontend**
- React 19 + TypeScript + Vite
- Tailwind CSS v4
- Custom `useStream` hook — SSE consumer returning `{ content, meta }`
- react-markdown for rendered output

**Infrastructure**
- Docker Compose — PostgreSQL 15 + Redis 7

---

## Architecture

```
Browser
  └─ fetch() POST JSON
       └─ FastAPI StreamingResponse (text/event-stream)
            ├─ status events  → progress messages
            ├─ meta event     → session_id, source_id
            ├─ token events   → LLM output (streamed)
            └─ done event     → stream complete

After stream completes:
  asyncio.create_task()
    └─ chunk text → SentenceTransformer → save embeddings → (optional) Pinecone upsert

History search:
  query → embed → Pinecone (if configured) OR local dot-product → top-k sessions
```

---

## Prerequisites

- **Python** 3.11+
- **Node.js** 18+
- **Docker** + Docker Compose (for PostgreSQL and Redis)
- A free [Groq API key](https://console.groq.com) (required)
- A [Pinecone](https://www.pinecone.io) API key (optional — falls back to local vector search)

---

## Quick Start

### 1. Infrastructure
```bash
cd infra
docker-compose up -d    # starts PostgreSQL:5432 + Redis:6379
```

### 2. Backend
```bash
cd backend
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt

# Copy and fill in your environment variables
cp .env.example .env
# Required: GROQ_API_KEY, DATABASE_URL, JWT_SECRET
# Optional: PINECONE_API_KEY, PINECONE_INDEX, REDIS_URL

.venv/bin/python3 app/create_tables.py        # run once to create tables
.venv/bin/python3 -m uvicorn app.main:app --reload --port 8000
```

> **Note:** Always use `.venv/bin/python3 -m uvicorn` — pyenv shims can cause the reloader subprocess to pick up the wrong Python.

### 3. Frontend
```bash
cd frontend
npm install
npm run dev     # http://localhost:5173
```

---

## Environment Variables

```bash
# backend/.env

# LLM
GROQ_API_KEY=your_groq_key          # free at console.groq.com
GROQ_MODEL=llama-3.3-70b-versatile

# Database
DATABASE_URL=postgresql+asyncpg://sc:scpass@localhost:5432/salescopilot

# Auth
JWT_SECRET=change-this-before-deploying

# Redis (optional — caching degrades gracefully if unavailable)
REDIS_URL=redis://localhost:6379

# Pinecone (optional — falls back to local PostgreSQL embeddings)
PINECONE_API_KEY=your_pinecone_key
PINECONE_INDEX=sales-copilot
PINECONE_NAMESPACE=dev

# CORS
FRONTEND_ORIGIN=http://localhost:5173
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/signup` | Create account → JWT token |
| POST | `/api/auth/login` | Login → JWT token |
| GET | `/api/auth/me` | Current user profile |
| POST | `/api/company/summary` | Crawl URL + stream company summary |
| POST | `/api/research/prospect` | DDG search + stream prospect profile |
| POST | `/api/report/precall` | Stream pre-call briefing |
| POST | `/api/sessions/{id}/followup` | Stream follow-up email |
| GET | `/api/history` | List sessions (paginated) |
| GET | `/api/history/search?q=` | Semantic search across sessions |
| GET | `/api/history/{id}` | Full session detail |
| PATCH | `/api/history/{id}/outcome` | Set call outcome |
| DELETE | `/api/history/{id}` | Delete session |
| GET | `/api/health` | Health check |

---

## Project Structure

```
Sales-Briefing-AI-Agent/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app + router includes
│   │   ├── models.py                # SQLAlchemy models
│   │   ├── crud.py                  # DB helpers
│   │   ├── db.py                    # Async engine + session
│   │   ├── routes/
│   │   │   ├── auth.py              # signup / login / me
│   │   │   ├── company.py           # company summary (SSE)
│   │   │   ├── prospect.py          # prospect research (SSE + background embed)
│   │   │   ├── report.py            # pre-call report (SSE)
│   │   │   ├── followup.py          # follow-up email (SSE)
│   │   │   └── history.py           # history CRUD + semantic search
│   │   └── services/
│   │       ├── auth.py              # JWT + bcrypt
│   │       ├── cache.py             # Redis wrapper
│   │       ├── embeddings.py        # SentenceTransformer
│   │       ├── llm.py               # Groq streaming
│   │       ├── prospect_search.py   # DuckDuckGo + scraper
│   │       ├── sse.py               # SSE event helpers
│   │       └── vector_store.py      # Pinecone client
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── context/AuthContext.tsx  # JWT auth state + localStorage
│       ├── hooks/useStream.ts       # SSE consumer hook
│       ├── lib/
│       │   ├── api.ts               # axios instance
│       │   └── exportPdf.ts         # DOM → print window → PDF
│       └── pages/
│           ├── Research.tsx         # 3-step wizard
│           └── History.tsx          # session list + search + outcomes
└── infra/
    └── docker-compose.yml           # PostgreSQL + Redis
```

---

## Key Engineering Decisions

**SSE streaming over WebSockets** — simpler for one-way server-to-client token streaming; `fetch()` + `ReadableStream` instead of `EventSource` to support POST bodies.

**Background embeddings via `asyncio.create_task()`** — PyTorch holds the GIL during CPU inference. Running it in the request path would freeze the entire event loop. Using `create_task()` (not FastAPI's `BackgroundTasks`) because background tasks added inside a `StreamingResponse` generator are never executed — FastAPI checks for tasks before the generator runs.

**Local-first vector search** — embeddings stored as JSON float lists in PostgreSQL, searched with cosine similarity (dot product on L2-normalized vectors). Pinecone is wired in as an optional enhancement: if the API key is set, chunks are upserted to Pinecone after embedding and queries hit Pinecone first.

**Redis caching** — implemented as a transparent wrapper that silently no-ops when Redis is unavailable, so the app works in environments without Redis.

---

## License

[MIT](LICENSE)
