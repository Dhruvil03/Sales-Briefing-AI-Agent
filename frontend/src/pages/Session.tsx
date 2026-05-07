// frontend/src/pages/Session.tsx
/**
 * Full session detail view at /session/:id
 *
 * Features:
 *   - Company News signals
 *   - ICP fit scoring (1-10) with breakdown
 *   - HubSpot CRM export
 *   - Tabs: Company | Prospect | Report | Follow-up Email | Transcript
 *   - Follow-up tab: Gmail mailto: shortcut
 *   - Transcript tab: paste meeting transcript → AI extracts next steps + drafts email
 *   - PDF export, delete session, outcome picker
 */

import { useCallback, useEffect, useRef, useState } from "react"
import { useNavigate, useParams } from "react-router-dom"
import ReactMarkdown from "react-markdown"
import type { Components } from "react-markdown"
import { useStream } from "../hooks/useStream"
import { exportToPdf } from "../lib/exportPdf"

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000")
  .toString()
  .replace(/\/$/, "")

// ── Auth ──────────────────────────────────────────────────────────────────────

function authHeaders(): HeadersInit {
  const stored = localStorage.getItem("sc_auth")
  const token = stored ? (JSON.parse(stored) as { token?: string }).token : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}
function authJsonHeaders(): HeadersInit {
  return { ...authHeaders(), "Content-Type": "application/json" }
}

// ── Markdown ──────────────────────────────────────────────────────────────────

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

type CallOutcome = "booked" | "follow-up" | "not-interested" | "no-show"
type TabId = "company" | "prospect" | "report" | "followup" | "notes" | "transcript"

interface SessionDetail {
  id:                  number
  company_name:        string | null
  prospect_name:       string | null
  company_url:         string | null
  created_at:          string
  call_outcome:        CallOutcome | null
  has_company:         boolean
  has_prospect:        boolean
  has_report:          boolean
  company_summary:     string | null
  prospect_insights:   string | null
  report_md:           string | null
  followup_email:      string | null
  call_notes_text:     string | null
  sources_searched:    string[] | null
  aggregated_text_len: number | null
}

interface NewsItem {
  title: string; url: string; source: string; published_at: string; description: string
}

interface ICPScore {
  score:     number
  breakdown: Record<string, number> | null
  reasoning: string | null
}

// ── Outcome picker ────────────────────────────────────────────────────────────

const OUTCOMES: { value: CallOutcome; label: string; color: string }[] = [
  { value: "booked",         label: "Booked",         color: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30" },
  { value: "follow-up",      label: "Follow-up",      color: "bg-indigo-500/20  text-indigo-300  border-indigo-500/30"  },
  { value: "not-interested", label: "Not interested", color: "bg-red-500/20     text-red-300     border-red-500/30"     },
  { value: "no-show",        label: "No-show",        color: "bg-yellow-500/20  text-yellow-300  border-yellow-500/30"  },
]

function OutcomePicker({
  sessionId, current, onChange,
}: { sessionId: number; current: CallOutcome | null; onChange: (v: CallOutcome | null) => void }) {
  const [saving, setSaving] = useState(false)
  async function pick(value: CallOutcome | null) {
    setSaving(true)
    try {
      await fetch(`${API_BASE}/api/history/${sessionId}/outcome`, {
        method: "PATCH",
        headers: authJsonHeaders(),
        body: JSON.stringify({ outcome: value }),
      })
      onChange(value)
    } finally { setSaving(false) }
  }
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      <span className="text-[10px] text-gray-600 mr-0.5">Call outcome:</span>
      {OUTCOMES.map(o => (
        <button key={o.value} disabled={saving}
          onClick={() => pick(current === o.value ? null : o.value)}
          className={`text-[10px] px-2.5 py-1 rounded-full border transition-all ${
            current === o.value ? o.color
              : "bg-white/[0.06] text-gray-500 border-white/10 hover:border-white/20 hover:text-gray-300"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

// ── ICP Score badge + panel ───────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 8) return "text-emerald-300 border-emerald-500/40 bg-emerald-500/15"
  if (score >= 6) return "text-indigo-300  border-indigo-500/40  bg-indigo-500/15"
  if (score >= 4) return "text-yellow-300  border-yellow-500/40  bg-yellow-500/15"
  return              "text-red-300     border-red-500/40     bg-red-500/15"
}

function ICPScorePanel({ sessionId }: { sessionId: number }) {
  const [score,   setScore]   = useState<ICPScore | null>(null)
  const [loading, setLoading] = useState(true)
  const [scoring, setScoring] = useState(false)
  const [error,   setError]   = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/sessions/${sessionId}/icp-score`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(data => { if (data) setScore(data) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [sessionId])

  async function handleScore() {
    setScoring(true)
    setError(null)
    try {
      const r = await fetch(`${API_BASE}/api/sessions/${sessionId}/icp-score`, {
        method: "POST",
        headers: authHeaders(),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail ?? "Scoring failed")
      setScore(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Scoring failed")
    } finally {
      setScoring(false)
    }
  }

  if (loading) return null

  return (
    <div className="rounded-2xl bg-white/[0.05] border border-white/[0.08] overflow-hidden">
      <div className="px-4 py-3 flex items-center gap-3 border-b border-white/[0.06]">
        <span className="text-xs font-semibold text-gray-300">ICP Fit Score</span>

        {score ? (
          <span className={`text-sm font-bold px-2.5 py-0.5 rounded-full border ${scoreColor(score.score)}`}>
            {score.score}/10
          </span>
        ) : null}

        <button
          onClick={handleScore}
          disabled={scoring}
          className={`ml-auto text-xs px-3 py-1.5 rounded-lg font-medium transition-all flex items-center gap-1.5 ${
            scoring
              ? "bg-white/[0.05] text-gray-500 cursor-not-allowed"
              : "bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/30"
          }`}
        >
          {scoring && (
            <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
            </svg>
          )}
          {scoring ? "Scoring…" : score ? "Re-score" : "Score vs ICP"}
        </button>
      </div>

      {error && (
        <p className="px-4 py-2 text-xs text-red-400 bg-red-500/10">{error}</p>
      )}

      {score && (
        <div className="px-4 py-3 space-y-3">
          {/* Breakdown bars */}
          {score.breakdown && (
            <div className="space-y-2">
              {Object.entries(score.breakdown).map(([key, val]) => (
                <div key={key} className="flex items-center gap-3">
                  <span className="text-[11px] text-gray-500 w-28 shrink-0 capitalize">
                    {key.replace(/_/g, " ")}
                  </span>
                  <div className="flex-1 h-1.5 bg-white/[0.07] rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${
                        val >= 8 ? "bg-emerald-500" : val >= 5 ? "bg-indigo-500" : "bg-yellow-500"
                      }`}
                      style={{ width: `${val * 10}%` }}
                    />
                  </div>
                  <span className={`text-[11px] font-medium w-6 text-right ${
                    val >= 8 ? "text-emerald-400" : val >= 5 ? "text-indigo-400" : "text-yellow-400"
                  }`}>{val}</span>
                </div>
              ))}
            </div>
          )}
          {score.reasoning && (
            <p className="text-xs text-gray-500 leading-relaxed border-t border-white/[0.05] pt-2">{score.reasoning}</p>
          )}
        </div>
      )}
    </div>
  )
}

// ── HubSpot export button ─────────────────────────────────────────────────────

function HubSpotButton({ sessionId }: { sessionId: number }) {
  const [status,    setStatus]    = useState<"idle" | "loading" | "done" | "error">("idle")
  const [msg,    setMsg]    = useState("")

  async function handleExport() {
    setStatus("loading")
    try {
      const r = await fetch(`${API_BASE}/api/sessions/${sessionId}/export/hubspot`, {
        method: "POST",
        headers: authHeaders(),
      })
      const data = await r.json()
      if (!r.ok) throw new Error(data.detail ?? "Export failed")
      setStatus("done")
      const fields: string[] = data.fields_set ?? []
      const summary = fields.length
        ? fields.map((f: string) => f.replace(/_/g, " ")).join(", ")
        : "name only"
      setMsg(`${data.action === "updated" ? "Updated" : "Created"} · ${summary}`)
      setTimeout(() => setStatus("idle"), 5000)
    } catch (e) {
      setStatus("error")
      setMsg(e instanceof Error ? e.message : "Export failed")
      setTimeout(() => setStatus("idle"), 5000)
    }
  }

  return (
    <button
      onClick={handleExport}
      disabled={status === "loading"}
      title="Push to HubSpot CRM"
      className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg border transition-all ${
        status === "done"  ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
        : status === "error" ? "bg-red-500/15 text-red-300 border-red-500/30"
        : status === "loading" ? "bg-white/[0.05] text-gray-500 border-white/10 cursor-not-allowed"
        : "bg-orange-500/10 hover:bg-orange-500/20 text-orange-300 border-orange-500/30"
      }`}
    >
      {status === "loading" && (
        <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
      )}
      {status === "done"  ? `✓ ${msg}` :
       status === "error" ? `✕ ${msg}` :
       status === "loading" ? "Pushing…" : "Push to HubSpot"}
    </button>
  )
}

// ── News signals ──────────────────────────────────────────────────────────────

function NewsSignals({ companyName }: { companyName: string }) {
  const [news,    setNews]    = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch(`${API_BASE}/api/news?company=${encodeURIComponent(companyName)}&limit=5`)
      .then(r => r.ok ? r.json() : Promise.resolve([]))
      .then(setNews)
      .catch(() => setNews([]))
      .finally(() => setLoading(false))
  }, [companyName])

  if (loading || news.length === 0) return null

  return (
    <div className="rounded-2xl bg-white/[0.05] border border-white/[0.08] overflow-hidden">
      <div className="px-4 py-3 border-b border-white/[0.06] flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        <span className="text-xs font-semibold text-gray-300">Recent Company News</span>
        <span className="ml-auto text-[10px] text-gray-600">{news.length} articles</span>
      </div>
      <div className="divide-y divide-white/[0.05]">
        {news.map((item, i) => (
          <a key={i} href={item.url} target="_blank" rel="noopener noreferrer"
            className="flex flex-col gap-1 px-4 py-3 hover:bg-white/[0.05] transition-colors group"
          >
            <div className="flex items-start justify-between gap-3">
              <p className="text-xs font-medium text-gray-200 leading-snug group-hover:text-white transition-colors line-clamp-2">
                {item.title}
              </p>
              <svg className="h-3 w-3 text-gray-600 shrink-0 mt-0.5 group-hover:text-gray-400 transition-colors"
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </div>
            {item.description && <p className="text-[11px] text-gray-500 line-clamp-2">{item.description}</p>}
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[10px] text-gray-600">{item.source}</span>
              <span className="text-[10px] text-gray-700">·</span>
              <span className="text-[10px] text-gray-600">{item.published_at}</span>
            </div>
          </a>
        ))}
      </div>
    </div>
  )
}

// ── Follow-up panel (with Gmail shortcut) ─────────────────────────────────────

function buildMailto(subject: string, body: string): string {
  return `mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`
}

const TONE_OPTIONS = [
  { value: "follow-up",     label: "Follow-up",      desc: "Post-call, warm & specific" },
  { value: "cold",          label: "Cold Outreach",  desc: "First touch, hook with insight" },
  { value: "re-engagement", label: "Re-engagement",  desc: "Revive a gone-cold lead" },
]

function FollowUpPanel({ sessionId, existingEmail, prospectName }: {
  sessionId: number
  existingEmail: string | null
  prospectName: string | null
}) {
  const [notes, setNotes] = useState("")
  const [tone,  setTone]  = useState("follow-up")
  const [email, setEmail] = useState(existingEmail ?? "")
  const stream = useStream(`/api/sessions/${sessionId}/followup`)

  async function handleGenerate() {
    if (!notes.trim()) return
    setEmail("")
    stream.reset()
    const { content } = await stream.start({ call_notes: notes.trim(), tone })
    if (content) setEmail(content)
  }

  // Extract subject line from email markdown if present
  const subject = (() => {
    const match = email.match(/\*\*Subject[:\s*]*\*\*\s*(.+)/i) ||
                  email.match(/Subject:\s*(.+)/i)
    return match ? match[1].trim() : `Follow-up — ${prospectName ?? "our conversation"}`
  })()

  return (
    <div className="space-y-3 py-1">
      {email && !stream.isStreaming ? (
        <>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-medium text-gray-500 uppercase tracking-widest">Follow-up Email</span>
            <div className="flex gap-2">
              <a
                href={buildMailto(subject, email.replace(/[*#`]/g, ""))}
                className="text-xs text-emerald-400 hover:text-emerald-300 transition-colors border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 rounded-lg"
                title="Open in Gmail / mail client"
              >
                Open in Gmail
              </a>
              <button onClick={() => { setEmail(""); stream.reset() }}
                className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
                Regenerate
              </button>
              <button onClick={() => navigator.clipboard.writeText(email)}
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors">
                Copy
              </button>
            </div>
          </div>
          <div className="rounded-xl bg-black/30 border border-white/[0.06] p-4">
            <ReactMarkdown components={MD}>{email}</ReactMarkdown>
          </div>
        </>
      ) : (
        <>
          {/* Tone picker */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1.5">Email Type</label>
            <div className="flex gap-2 flex-wrap">
              {TONE_OPTIONS.map(t => (
                <button
                  key={t.value}
                  onClick={() => setTone(t.value)}
                  className={`flex flex-col items-start px-3 py-2 rounded-xl border text-left transition-all ${
                    tone === t.value
                      ? "bg-indigo-600/20 border-indigo-500/40 text-indigo-300"
                      : "bg-white/[0.04] border-white/[0.09] text-gray-500 hover:border-white/20 hover:text-gray-300"
                  }`}
                >
                  <span className="text-xs font-medium">{t.label}</span>
                  <span className="text-[10px] opacity-70 mt-0.5">{t.desc}</span>
                </button>
              ))}
            </div>
          </div>

          <label className="block text-xs font-medium text-gray-400 mb-1.5">
            Call Notes
            <span className="ml-1 text-gray-600 font-normal">— what happened on the call?</span>
          </label>
          <textarea
            className="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-3.5 py-2.5
                       text-sm text-gray-200 placeholder-gray-600 h-24 resize-none
                       focus:outline-none focus:border-indigo-500/60 transition-colors"
            placeholder="e.g. Strong interest in automation. Pain point: manual reporting. Wants demo next week."
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
          {stream.error && <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{stream.error}</p>}
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

// ── Transcript panel ──────────────────────────────────────────────────────────

function TranscriptPanel({ sessionId }: { sessionId: number }) {
  const [transcript, setTranscript] = useState("")
  const stream = useStream(`/api/sessions/${sessionId}/transcript`)

  async function handleAnalyze() {
    if (!transcript.trim()) return
    stream.reset()
    await stream.start({ transcript: transcript.trim() })
  }

  return (
    <div className="space-y-3 py-1">
      {stream.content ? (
        <>
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-medium text-gray-500 uppercase tracking-widest">Transcript Analysis</span>
            <div className="flex gap-2">
              {!stream.isStreaming && (
                <>
                  <button onClick={() => { stream.reset(); setTranscript("") }}
                    className="text-xs text-gray-600 hover:text-gray-400 transition-colors">
                    New transcript
                  </button>
                  <button onClick={() => navigator.clipboard.writeText(stream.content)}
                    className="text-xs text-gray-500 hover:text-gray-300 transition-colors">
                    Copy
                  </button>
                </>
              )}
              {stream.isStreaming && (
                <div className="flex items-center gap-1.5 text-xs text-indigo-300">
                  <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                  </svg>
                  Analysing…
                </div>
              )}
            </div>
          </div>
          <div className="rounded-xl bg-black/30 border border-white/[0.06] p-4">
            <ReactMarkdown components={MD}>{stream.content}</ReactMarkdown>
          </div>
        </>
      ) : (
        <>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">
            Meeting Transcript
            <span className="ml-1 text-gray-600 font-normal">— paste from Zoom, Fireflies, Otter, etc.</span>
          </label>
          <textarea
            className="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-3.5 py-2.5
                       text-sm text-gray-200 placeholder-gray-600 h-48 resize-none
                       focus:outline-none focus:border-indigo-500/60 transition-colors font-mono text-xs leading-relaxed"
            placeholder={"[00:00] Rep: Thanks for joining today...\n[00:15] Prospect: Sure, happy to chat..."}
            value={transcript}
            onChange={e => setTranscript(e.target.value)}
          />
          {stream.error && <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{stream.error}</p>}
          <div className="flex items-center justify-between">
            <p className="text-[10px] text-gray-600">{transcript.length} chars · min 50 required</p>
            <button
              onClick={handleAnalyze}
              disabled={transcript.trim().length < 50 || stream.isStreaming}
              className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all
                ${transcript.trim().length < 50 || stream.isStreaming
                  ? "bg-indigo-600/30 text-indigo-400/50 cursor-not-allowed"
                  : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-900/40"}`}
            >
              Analyse Transcript →
            </button>
          </div>
        </>
      )}
    </div>
  )
}

// ── Notes panel ───────────────────────────────────────────────────────────────

function NotesPanel({ sessionId, initialNotes }: { sessionId: number; initialNotes: string | null }) {
  const [notes,   setNotes]   = useState(initialNotes ?? "")
  const [saving,  setSaving]  = useState(false)
  const [saved,   setSaved]   = useState(false)
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  function scheduleAutoSave(text: string) {
    if (saveTimer.current) clearTimeout(saveTimer.current)
    saveTimer.current = setTimeout(() => doSave(text), 1200)
  }

  async function doSave(text: string) {
    setSaving(true)
    try {
      await fetch(`${API_BASE}/api/history/${sessionId}/notes`, {
        method: "PATCH",
        headers: authJsonHeaders(),
        body: JSON.stringify({ notes_text: text }),
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      // silently ignore
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-3 py-1">
      <div className="flex items-center justify-between mb-1">
        <label className="text-xs font-medium text-gray-400">
          Call Notes
          <span className="ml-1 text-gray-600 font-normal">— your observations, next steps, commitments</span>
        </label>
        <span className={`text-[10px] transition-opacity ${saving ? "text-gray-500 opacity-100" : saved ? "text-emerald-400 opacity-100" : "opacity-0"}`}>
          {saving ? "Saving…" : "Saved"}
        </span>
      </div>
      <textarea
        className="w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-3.5 py-2.5
                   text-sm text-gray-200 placeholder-gray-600 h-48 resize-none
                   focus:outline-none focus:border-indigo-500/60 transition-colors leading-relaxed"
        placeholder={"What happened on the call?\n\nPain points mentioned:\n\nNext steps agreed:\n\nFollow-up date:"}
        value={notes}
        onChange={e => { setNotes(e.target.value); setSaved(false); scheduleAutoSave(e.target.value) }}
      />
      <div className="flex justify-between items-center">
        <p className="text-[10px] text-gray-700">Auto-saved as you type</p>
        <button
          onClick={() => doSave(notes)}
          disabled={saving}
          className="text-xs px-3 py-1.5 rounded-lg border border-white/10 text-gray-500 hover:text-gray-300 hover:border-white/20 transition-all"
        >
          Save now
        </button>
      </div>
    </div>
  )
}

// ── Tab bar ───────────────────────────────────────────────────────────────────

function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={`text-xs font-medium px-3.5 py-2 rounded-lg transition-colors ${
        active
          ? "bg-indigo-600/30 text-indigo-300 border border-indigo-500/30"
          : "text-gray-500 hover:text-gray-300 hover:bg-white/[0.06]"
      }`}
    >
      {label}
    </button>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Session() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [session,   setSession]   = useState<SessionDetail | null>(null)
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>("report")
  const [outcome,   setOutcome]   = useState<CallOutcome | null>(null)
  const [deleting,  setDeleting]  = useState(false)

  const reportPdfRef = useRef<HTMLDivElement>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true); setError(null)
    try {
      const r = await fetch(`${API_BASE}/api/history/${id}`, { headers: authHeaders() })
      if (!r.ok) throw new Error(r.statusText)
      const data: SessionDetail = await r.json()
      setSession(data)
      setOutcome(data.call_outcome)
      if      (data.has_report)   setActiveTab("report")
      else if (data.has_prospect) setActiveTab("prospect")
      else if (data.has_company)  setActiveTab("company")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load session")
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  async function handleDelete() {
    if (!session) return
    if (!confirm(`Delete research for "${session.prospect_name ?? session.company_name}"?`)) return
    setDeleting(true)
    try {
      await fetch(`${API_BASE}/api/history/${session.id}`, { method: "DELETE", headers: authHeaders() })
      navigate("/research", { replace: true })
    } finally { setDeleting(false) }
  }

  if (loading) return (
    <div className="flex items-center justify-center h-64 gap-3 text-sm text-gray-500">
      <svg className="animate-spin h-4 w-4 text-indigo-400" viewBox="0 0 24 24" fill="none">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
      </svg>
      Loading session…
    </div>
  )

  if (error || !session) return (
    <div className="max-w-2xl mx-auto px-6 py-12 text-center">
      <p className="text-red-400 text-sm mb-4">{error ?? "Session not found"}</p>
      <button onClick={() => navigate("/research")} className="text-indigo-400 hover:text-indigo-300 text-sm transition-colors">
        ← New Research
      </button>
    </div>
  )

  const availableTabs: TabId[] = [
    ...(session.has_company  ? ["company"    as TabId] : []),
    ...(session.has_prospect ? ["prospect"   as TabId] : []),
    ...(session.has_report   ? ["report"     as TabId] : []),
    ...(session.has_prospect ? ["followup"   as TabId] : []),
    "notes" as TabId,
    ...(session.has_prospect ? ["transcript" as TabId] : []),
  ]

  const TAB_LABELS: Record<TabId, string> = {
    company:    "Company",
    prospect:   "Prospect",
    report:     "Report",
    followup:   "Follow-up Email",
    notes:      "Notes",
    transcript: "Transcript",
  }

  const date = new Date(session.created_at).toLocaleDateString("en-US", {
    weekday: "short", month: "short", day: "numeric", year: "numeric",
  })

  const companyDisplay = session.company_name ??
    (session.company_url
      ? (() => { try { return new URL(session.company_url!).hostname.replace("www.", "") } catch { return session.company_url! } })()
      : null)

  return (
    <div className="max-w-3xl mx-auto px-6 py-6 pb-20 space-y-5">

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-white leading-tight">
              {session.prospect_name ?? companyDisplay ?? "Untitled Session"}
            </h1>
            {session.prospect_name && companyDisplay && (
              <p className="text-sm text-gray-500 mt-0.5">{companyDisplay}</p>
            )}
            <p className="text-xs text-gray-600 mt-1">{date}</p>
          </div>

          <div className="flex items-center gap-2 shrink-0 mt-1 flex-wrap justify-end">
            {/* HubSpot export */}
            {session.has_prospect && <HubSpotButton sessionId={session.id} />}

            {/* Completion badges */}
            {session.has_company  && <span className="text-[10px] bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-2 py-1 rounded-full">Company</span>}
            {session.has_prospect && <span className="text-[10px] bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-2 py-1 rounded-full">Prospect</span>}
            {session.has_report   && <span className="text-[10px] bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 px-2 py-1 rounded-full">Report</span>}

            {/* Delete */}
            <button onClick={handleDelete} disabled={deleting}
              className="text-xs text-gray-600 hover:text-red-400 transition-colors ml-2 px-2 py-1 rounded-lg hover:bg-red-500/10"
            >
              {deleting ? "…" : "Delete"}
            </button>
          </div>
        </div>

        <OutcomePicker sessionId={session.id} current={outcome} onChange={setOutcome} />
      </div>

      {/* ── ICP Scoring ─────────────────────────────────────────────────────── */}
      {session.has_prospect && <ICPScorePanel sessionId={session.id} />}

      {/* ── Company news ────────────────────────────────────────────────────── */}
      {companyDisplay && <NewsSignals companyName={companyDisplay} />}

      {/* ── Tabs ────────────────────────────────────────────────────────────── */}
      <div className="rounded-2xl bg-white/[0.05] border border-white/[0.08] overflow-hidden">

        {availableTabs.length > 0 && (
          <div className="flex items-center gap-1 px-4 pt-4 pb-2 border-b border-white/[0.06] flex-wrap">
            {availableTabs.map(tab => (
              <TabButton key={tab} label={TAB_LABELS[tab]} active={activeTab === tab} onClick={() => setActiveTab(tab)} />
            ))}

            {activeTab === "report" && session.report_md && (
              <button
                onClick={() => {
                  if (reportPdfRef.current) {
                    exportToPdf(reportPdfRef.current, session.prospect_name ? `${session.prospect_name} — Pre-Call Report` : "Pre-Call Report")
                  }
                }}
                className="ml-auto text-xs text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1.5"
              >
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 10v6m0 0l-3-3m3 3l3-3M3 17a4 4 0 004 4h10a4 4 0 004-4v-3" />
                </svg>
                Download PDF
              </button>
            )}
          </div>
        )}

        <div className="px-5 py-4">
          {availableTabs.length === 0 && (
            <p className="text-sm text-gray-600 italic py-4 text-center">No content generated yet.</p>
          )}

          {activeTab === "company" && (
            session.company_summary
              ? <ReactMarkdown components={MD}>{session.company_summary}</ReactMarkdown>
              : <p className="text-sm text-gray-600 italic py-4">No company research for this session.</p>
          )}

          {activeTab === "prospect" && (
            <>
              {session.sources_searched && session.sources_searched.length > 0 && (
                <div className="flex flex-wrap gap-1.5 mb-4 pb-4 border-b border-white/[0.05]">
                  <span className="text-[10px] text-gray-600 self-center mr-1">Sources:</span>
                  {session.sources_searched.map(url => {
                    const host = (() => { try { return new URL(url).hostname.replace("www.", "") } catch { return url } })()
                    return (
                      <a key={url} href={url} target="_blank" rel="noopener noreferrer"
                        className="text-[10px] bg-white/[0.05] border border-white/[0.08] text-gray-500
                                   hover:text-indigo-400 hover:border-indigo-500/30 px-2 py-0.5 rounded-full transition-colors"
                      >{host}</a>
                    )
                  })}
                </div>
              )}
              {session.prospect_insights
                ? <ReactMarkdown components={MD}>{session.prospect_insights}</ReactMarkdown>
                : <p className="text-sm text-gray-600 italic py-4">No prospect research for this session.</p>
              }
            </>
          )}

          {activeTab === "report" && (
            session.report_md
              ? <div ref={reportPdfRef}><ReactMarkdown components={MD}>{session.report_md}</ReactMarkdown></div>
              : <p className="text-sm text-gray-600 italic py-4">No pre-call report for this session.</p>
          )}

          {activeTab === "followup" && (
            <FollowUpPanel sessionId={session.id} existingEmail={session.followup_email ?? null} prospectName={session.prospect_name} />
          )}

          {activeTab === "notes" && (
            <NotesPanel sessionId={session.id} initialNotes={session.call_notes_text ?? null} />
          )}

          {activeTab === "transcript" && (
            <TranscriptPanel sessionId={session.id} />
          )}
        </div>
      </div>
    </div>
  )
}
