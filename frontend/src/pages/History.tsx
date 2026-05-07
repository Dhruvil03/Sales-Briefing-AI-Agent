// frontend/src/pages/History.tsx
/**
 * History dashboard — lists all past research sessions.
 *
 * Each card shows: company + prospect name, date, completion badges.
 * Clicking a card expands it into tabs: Company / Prospect / Report.
 */

import { useCallback, useEffect, useRef, useState } from "react"
import { Link } from "react-router-dom"
import ReactMarkdown from "react-markdown"
import type { Components } from "react-markdown"
import { useStream } from "../hooks/useStream"
import { exportToPdf } from "../lib/exportPdf"

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000")
  .toString()
  .replace(/\/$/, "")

// ── Markdown renderer (same as Research.tsx) ─────────────────────────────────

const MD: Components = {
  h1: ({ children }) => <h1 className="text-base font-bold text-white mt-4 mb-1.5">{children}</h1>,
  h2: ({ children }) => <h2 className="text-sm font-bold text-white mt-4 mb-1.5">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold text-gray-200 mt-3 mb-1">{children}</h3>,
  p:  ({ children }) => <p className="text-gray-300 text-sm leading-relaxed mb-2">{children}</p>,
  ul: ({ children }) => <ul className="ml-4 mb-2 space-y-1">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal ml-4 mb-2 space-y-1">{children}</ol>,
  li: ({ children }) => (
    <li className="text-gray-300 text-sm flex gap-2">
      <span className="text-indigo-400 mt-1 shrink-0">·</span>
      <span>{children}</span>
    </li>
  ),
  strong: ({ children }) => <strong className="text-gray-100 font-semibold">{children}</strong>,
  em:     ({ children }) => <em className="text-gray-400 italic">{children}</em>,
  hr:     ()             => <hr className="border-white/10 my-3" />,
  code:   ({ children }) => (
    <code className="bg-white/10 px-1.5 py-0.5 rounded text-indigo-300 text-xs font-mono">{children}</code>
  ),
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface SearchResult {
  session_id:    number
  company_name:  string | null
  prospect_name: string | null
  created_at:    string
  score:         number
  excerpt:       string
}

type CallOutcome = "booked" | "follow-up" | "not-interested" | "no-show"

interface SessionListItem {
  id:              number
  company_name:    string | null
  prospect_name:   string | null
  company_url:     string | null
  created_at:      string
  call_outcome:    CallOutcome | null
  has_company:     boolean
  has_prospect:    boolean
  has_report:      boolean
  company_preview:  string | null
  prospect_preview: string | null
  report_preview:   string | null
}

interface SessionDetail extends SessionListItem {
  call_outcome: CallOutcome | null
  company_summary:     string | null
  prospect_insights:   string | null
  report_md:           string | null
  followup_email:      string | null
  sources_searched:    string[] | null
  aggregated_text_len: number | null
}

type TabId = "company" | "prospect" | "report" | "followup"

// ── Small components ──────────────────────────────────────────────────────────

function Badge({ label, active }: { label: string; active: boolean }) {
  return (
    <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${
      active
        ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
        : "bg-white/[0.06] text-gray-600 border-white/[0.08]"
    }`}>
      {label}
    </span>
  )
}

function TabButton({
  label, active, onClick,
}: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`text-xs font-medium px-3 py-1.5 rounded-lg transition-colors ${
        active
          ? "bg-indigo-600/30 text-indigo-300 border border-indigo-500/30"
          : "text-gray-500 hover:text-gray-300"
      }`}
    >
      {label}
    </button>
  )
}

function EmptyTab({ label }: { label: string }) {
  return (
    <p className="text-sm text-gray-600 italic py-4">
      No {label} generated for this session.
    </p>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000) }}
      className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
    >
      {copied ? "✓ Copied" : "Copy"}
    </button>
  )
}

function FollowUpPanel({ sessionId, existingEmail }: { sessionId: number; existingEmail: string | null }) {
  const [notes, setNotes]         = useState("")
  const [email, setEmail]         = useState(existingEmail ?? "")
  const stream = useStream(`/api/sessions/${sessionId}/followup`)
  const notesRef = useRef<HTMLTextAreaElement>(null)

  async function handleGenerate() {
    if (!notes.trim()) return
    setEmail("")
    stream.reset()
    const { content } = await stream.start({ call_notes: notes.trim() })
    if (content) setEmail(content)
  }

  return (
    <div className="space-y-3 py-2">
      {email && !stream.isStreaming ? (
        <>
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] font-medium text-gray-500 uppercase tracking-widest">Follow-up Email</span>
            <div className="flex gap-3">
              <button
                onClick={() => { setEmail(""); stream.reset() }}
                className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
              >
                Regenerate
              </button>
              <CopyButton text={email} />
            </div>
          </div>
          <div className="rounded-xl bg-black/30 border border-white/[0.06] p-4">
            <ReactMarkdown components={MD}>{email}</ReactMarkdown>
          </div>
        </>
      ) : (
        <>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">
            Call Notes
            <span className="ml-1 text-gray-600 font-normal">— what happened on the call?</span>
          </label>
          <textarea
            ref={notesRef}
            className="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-3.5 py-2.5
                       text-sm text-gray-200 placeholder-gray-600 h-24 resize-none
                       focus:outline-none focus:border-indigo-500/60 focus:bg-white/[0.07] transition-colors"
            placeholder="e.g. Showed strong interest in automation. Pain point: manual reporting takes 3 hrs/week. Wants demo next week."
            value={notes}
            onChange={e => setNotes(e.target.value)}
          />
          {stream.isStreaming && (
            <div className="rounded-xl bg-black/30 border border-white/[0.06] p-4">
              <div className="flex items-center gap-2 text-xs text-indigo-300 mb-2">
                <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                </svg>
                Writing email…
              </div>
              <ReactMarkdown components={MD}>{stream.content}</ReactMarkdown>
            </div>
          )}
          {stream.error && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              {stream.error}
            </p>
          )}
          <div className="flex justify-end">
            <button
              onClick={handleGenerate}
              disabled={!notes.trim() || stream.isStreaming}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all
                ${!notes.trim() || stream.isStreaming
                  ? "bg-indigo-600/30 text-indigo-400/50 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-900/40"}`}
            >
              {stream.isStreaming ? "Writing…" : "Generate Email →"}
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ── Outcome picker ────────────────────────────────────────────────────────────

const OUTCOMES: { value: CallOutcome; label: string; color: string }[] = [
  { value: "booked",         label: "Booked",        color: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" },
  { value: "follow-up",      label: "Follow-up",     color: "bg-indigo-500/20  text-indigo-300  border-indigo-500/30"  },
  { value: "not-interested", label: "Not interested", color: "bg-red-500/20    text-red-300     border-red-500/30"     },
  { value: "no-show",        label: "No-show",        color: "bg-yellow-500/20 text-yellow-300  border-yellow-500/30"  },
]

function OutcomePicker({
  sessionId, current, onChange,
}: { sessionId: number; current: CallOutcome | null; onChange: (v: CallOutcome | null) => void }) {
  const [saving, setSaving] = useState(false)

  async function pick(value: CallOutcome | null) {
    setSaving(true)
    try {
      await fetch(`${API_BASE}/api/history/${sessionId}/outcome`, {
        method:  "PATCH",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ outcome: value }),
      })
      onChange(value)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-center gap-1.5 flex-wrap mt-2">
      <span className="text-[10px] text-gray-600 mr-0.5">Call outcome:</span>
      {OUTCOMES.map(o => (
        <button
          key={o.value}
          disabled={saving}
          onClick={() => pick(current === o.value ? null : o.value)}
          className={`text-[10px] px-2 py-0.5 rounded-full border transition-all ${
            current === o.value
              ? o.color
              : "bg-white/[0.06] text-gray-500 border-white/10 hover:border-white/20"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

// ── Session card ──────────────────────────────────────────────────────────────

function SessionCard({
  item, onDelete,
}: {
  item: SessionListItem
  onDelete: (id: number) => void
}) {
  const [expanded,  setExpanded]  = useState(false)
  const [detail,    setDetail]    = useState<SessionDetail | null>(null)
  const [loading,   setLoading]   = useState(false)
  const [activeTab, setActiveTab] = useState<TabId>("company")
  const [deleting,  setDeleting]  = useState(false)
  const [outcome,   setOutcome]   = useState<CallOutcome | null>(item.call_outcome)
  const reportPdfRef = useRef<HTMLDivElement>(null)

  async function handleExpand() {
    if (expanded) { setExpanded(false); return }
    setExpanded(true)
    if (detail) return   // already loaded
    setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/api/history/${item.id}`)
      if (r.ok) setDetail(await r.json())
    } finally {
      setLoading(false)
    }
    // default to first completed tab
    if (!item.has_company && item.has_prospect) setActiveTab("prospect")
    else if (!item.has_company && !item.has_prospect) setActiveTab("report")
  }

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation()
    if (!confirm(`Delete research for "${item.prospect_name ?? item.company_name}"?`)) return
    setDeleting(true)
    try {
      await fetch(`${API_BASE}/api/history/${item.id}`, { method: "DELETE" })
      onDelete(item.id)
    } finally {
      setDeleting(false)
    }
  }

  const date = new Date(item.created_at).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  })

  const availableTabs: TabId[] = [
    ...(item.has_company  ? ["company"  as TabId] : []),
    ...(item.has_prospect ? ["prospect" as TabId] : []),
    ...(item.has_report   ? ["report"   as TabId] : []),
    ...(item.has_prospect ? ["followup" as TabId] : []),  // only if we have prospect context
  ]

  return (
    <div className={`rounded-2xl border transition-all duration-300 overflow-hidden ${
      expanded
        ? "bg-white/[0.05] border-indigo-500/25"
        : "bg-white/[0.05] border-white/[0.08] hover:border-white/[0.14]"
    }`}>

      {/* ── Header row ── */}
      <div
        className="flex items-center justify-between px-5 py-4 cursor-pointer"
        onClick={handleExpand}
      >
        <div className="flex items-center gap-3 min-w-0">
          {/* Avatar / initials */}
          <div className="w-8 h-8 rounded-full bg-indigo-600/30 border border-indigo-500/30
                          flex items-center justify-center text-xs font-bold text-indigo-300 shrink-0">
            {(item.prospect_name ?? item.company_name ?? "?")[0].toUpperCase()}
          </div>

          <div className="min-w-0">
            <p className="text-sm font-medium text-gray-200 truncate">
              {item.prospect_name ?? "—"}
              {item.company_name && (
                <span className="text-gray-500 font-normal"> · {item.company_name}</span>
              )}
            </p>
            <p className="text-xs text-gray-600 mt-0.5">{date}</p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0 ml-3">
          <Badge label="Company"  active={item.has_company} />
          <Badge label="Prospect" active={item.has_prospect} />
          <Badge label="Report"   active={item.has_report} />
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="ml-2 text-gray-700 hover:text-red-400 transition-colors text-xs"
            title="Delete"
          >
            {deleting ? "…" : "✕"}
          </button>
          <span className={`text-gray-600 text-xs ml-1 transition-transform duration-200 ${
            expanded ? "rotate-180" : ""
          }`}>▾</span>
        </div>
      </div>

      {/* ── Outcome picker (always visible below header) ── */}
      <div className="px-5 pb-3" onClick={e => e.stopPropagation()}>
        <OutcomePicker sessionId={item.id} current={outcome} onChange={setOutcome} />
      </div>

      {/* ── Expanded detail ── */}
      {expanded && (
        <div className="border-t border-white/[0.06] px-5 pb-5">

          {loading ? (
            <div className="flex items-center gap-2 py-6 text-xs text-gray-500">
              <svg className="animate-spin h-3.5 w-3.5 text-indigo-400" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Loading…
            </div>
          ) : (
            <>
              {/* Tab bar */}
              {availableTabs.length > 0 && (
                <div className="flex items-center gap-1 pt-4 pb-3">
                  {availableTabs.map(tab => (
                    <TabButton
                      key={tab}
                      label={tab === "followup" ? "Follow-up Email" : tab.charAt(0).toUpperCase() + tab.slice(1)}
                      active={activeTab === tab}
                      onClick={() => setActiveTab(tab)}
                    />
                  ))}
                  {detail?.sources_searched && detail.sources_searched.length > 0 && (
                    <span className="ml-auto text-[10px] text-gray-600">
                      {detail.sources_searched.length} source{detail.sources_searched.length !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              )}

              {/* Tab content */}
              <div className="max-h-[400px] overflow-y-auto pr-1 scrollbar-thin">
                {activeTab === "company" && (
                  detail?.company_summary
                    ? <ReactMarkdown components={MD}>{detail.company_summary}</ReactMarkdown>
                    : <EmptyTab label="company research" />
                )}
                {activeTab === "prospect" && (
                  detail?.prospect_insights
                    ? <ReactMarkdown components={MD}>{detail.prospect_insights}</ReactMarkdown>
                    : <EmptyTab label="prospect research" />
                )}
                {activeTab === "report" && (
                  detail?.report_md
                    ? (
                      <>
                        <div className="flex justify-end mb-2">
                          <button
                            onClick={() => {
                              if (reportPdfRef.current) {
                                const title = item.prospect_name
                                  ? `${item.prospect_name} — Pre-Call Report`
                                  : "Pre-Call Report"
                                exportToPdf(reportPdfRef.current, title)
                              }
                            }}
                            className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1"
                          >
                            ↓ Download PDF
                          </button>
                        </div>
                        <div ref={reportPdfRef}>
                          <ReactMarkdown components={MD}>{detail.report_md}</ReactMarkdown>
                        </div>
                      </>
                    )
                    : <EmptyTab label="pre-call report" />
                )}
                {activeTab === "followup" && detail && (
                  <FollowUpPanel
                    sessionId={item.id}
                    existingEmail={detail.followup_email ?? null}
                  />
                )}
              </div>

              {availableTabs.length === 0 && (
                <p className="text-sm text-gray-600 italic py-4">
                  No content generated for this session yet.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

// ── Search bar ────────────────────────────────────────────────────────────────

function SearchBar({
  value, onChange, searching,
}: { value: string; onChange: (v: string) => void; searching: boolean }) {
  return (
    <div className="relative">
      <div className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-500">
        {searching
          ? <svg className="animate-spin h-3.5 w-3.5 text-indigo-400" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
          : <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z"/>
            </svg>
        }
      </div>
      <input
        type="text"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder="Search by role, company, interests, pain points…"
        className="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl
                   pl-9 pr-9 py-2.5 text-sm text-gray-200 placeholder-gray-600
                   focus:outline-none focus:border-indigo-500/60 focus:bg-white/[0.07] transition-colors"
      />
      {value && (
        <button
          onClick={() => onChange("")}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400 transition-colors text-xs"
        >
          ✕
        </button>
      )}
    </div>
  )
}

function SearchResultCard({ result }: { result: SearchResult }) {
  const date = new Date(result.created_at).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric",
  })
  const pct = Math.round(result.score * 100)

  return (
    <div className="rounded-2xl bg-white/[0.05] border border-white/[0.08] px-5 py-4 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-full bg-indigo-600/30 border border-indigo-500/30
                          flex items-center justify-center text-[11px] font-bold text-indigo-300 shrink-0">
            {(result.prospect_name ?? result.company_name ?? "?")[0].toUpperCase()}
          </div>
          <div>
            <p className="text-sm font-medium text-gray-200">
              {result.prospect_name ?? "—"}
              {result.company_name && <span className="text-gray-500 font-normal"> · {result.company_name}</span>}
            </p>
            <p className="text-xs text-gray-600">{date}</p>
          </div>
        </div>
        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${
          pct >= 70 ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
          : pct >= 50 ? "bg-indigo-500/15 text-indigo-400 border-indigo-500/30"
          : "bg-white/[0.05] text-gray-500 border-white/[0.10]"
        }`}>
          {pct}% match
        </span>
      </div>
      <p className="text-xs text-gray-500 leading-relaxed pl-9 line-clamp-2">{result.excerpt}</p>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function History() {
  const [sessions,       setSessions]       = useState<SessionListItem[]>([])
  const [loading,        setLoading]        = useState(true)
  const [error,          setError]          = useState<string | null>(null)
  const [query,          setQuery]          = useState("")
  const [searchResults,  setSearchResults]  = useState<SearchResult[] | null>(null)
  const [searching,      setSearching]      = useState(false)
  const [searchError,    setSearchError]    = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/history`)
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then(setSessions)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  const runSearch = useCallback(async (q: string) => {
    if (!q.trim()) { setSearchResults(null); setSearchError(null); return }
    setSearching(true)
    setSearchError(null)
    try {
      const r = await fetch(`${API_BASE}/api/history/search?q=${encodeURIComponent(q.trim())}&limit=8`)
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }))
        throw new Error(err.detail ?? r.statusText)
      }
      setSearchResults(await r.json())
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : String(e))
      setSearchResults(null)
    } finally {
      setSearching(false)
    }
  }, [])

  function handleQueryChange(v: string) {
    setQuery(v)
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!v.trim()) { setSearchResults(null); setSearchError(null); return }
    debounceRef.current = setTimeout(() => runSearch(v), 400)
  }

  function handleDelete(id: number) {
    setSessions(prev => prev.filter(s => s.id !== id))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24 text-gray-500 text-sm gap-2">
        <svg className="animate-spin h-4 w-4 text-indigo-400" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        Loading history…
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-20 text-red-400 text-sm">
        Failed to load history: {error}
      </div>
    )
  }

  const isSearchMode = query.trim().length > 0

  return (
    <div className="max-w-2xl mx-auto pb-16 space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between pt-4 pb-2">
        <div>
          <h1 className="text-2xl font-bold text-white">History</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {sessions.length} session{sessions.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link
          to="/research"
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500
                     text-white text-sm font-medium rounded-xl transition-colors"
        >
          + New Research
        </Link>
      </div>

      {/* Search bar — only shown when there are sessions */}
      {sessions.length > 0 && (
        <SearchBar value={query} onChange={handleQueryChange} searching={searching} />
      )}

      {/* Search mode */}
      {isSearchMode && (
        <div className="space-y-3">
          {searchError && (
            <div className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20
                            rounded-xl px-4 py-3">
              {searchError.includes("No embeddings") || searchResults?.length === 0
                ? "No indexed sessions yet — run prospect research first to build the search index."
                : searchError}
            </div>
          )}
          {!searching && searchResults !== null && searchResults.length === 0 && (
            <div className="rounded-2xl bg-white/[0.05] border border-white/[0.08] p-8 text-center">
              <p className="text-sm text-gray-500">No matching sessions found.</p>
              <p className="text-xs text-gray-600 mt-1">
                Try different terms, or run more prospect research to grow the index.
              </p>
            </div>
          )}
          {searchResults?.map(r => (
            <SearchResultCard key={r.session_id} result={r} />
          ))}
        </div>
      )}

      {/* Browse mode */}
      {!isSearchMode && (
        sessions.length === 0 ? (
          <div className="rounded-2xl bg-white/[0.05] border border-white/[0.08] p-12 text-center">
            <p className="text-gray-500 text-sm mb-4">No research sessions yet.</p>
            <Link
              to="/research"
              className="text-indigo-400 hover:text-indigo-300 text-sm transition-colors"
            >
              Start your first research →
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {sessions.map(s => (
              <SessionCard key={s.id} item={s} onDelete={handleDelete} />
            ))}
          </div>
        )
      )}
    </div>
  )
}
