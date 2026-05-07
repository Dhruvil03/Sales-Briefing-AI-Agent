// frontend/src/pages/BatchResearch.tsx
/**
 * Batch CSV Research — upload a CSV of prospects, research all of them.
 * Polls /api/batch/:id every 3 s until status is done/partial.
 *
 * CSV format (flexible column names):
 *   name, company, url   (or variations like prospect_name, company_name, website)
 */

import { useCallback, useEffect, useRef, useState } from "react"
import { Link, useLocation } from "react-router-dom"

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000")
  .toString()
  .replace(/\/$/, "")

function authHeaders(): HeadersInit {
  const stored = localStorage.getItem("sc_auth")
  const token = stored ? (JSON.parse(stored) as { token?: string }).token : null
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// ── Types ─────────────────────────────────────────────────────────────────────

interface BatchRow {
  id:            number
  row_index:     number
  prospect_name: string | null
  company_name:  string | null
  company_url:   string | null
  status:        "queued" | "running" | "done" | "failed"
  session_id:    number | null
  error_msg:     string | null
}

interface BatchJob {
  id:         number
  status:     "running" | "done" | "partial"
  total_rows: number
  created_at: string
  rows:       BatchRow[]
}

// ── Status pill ───────────────────────────────────────────────────────────────

const STATUS_STYLES: Record<string, string> = {
  queued:  "bg-white/[0.05] text-gray-500  border-white/[0.09]",
  running: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30 animate-pulse",
  done:    "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  failed:  "bg-red-500/15 text-red-300 border-red-500/30",
}

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${STATUS_STYLES[status] ?? STATUS_STYLES.queued}`}>
      {status}
    </span>
  )
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function ProgressBar({ rows }: { rows: BatchRow[] }) {
  const total   = rows.length
  const done    = rows.filter(r => r.status === "done").length
  const failed  = rows.filter(r => r.status === "failed").length
  const running = rows.filter(r => r.status === "running").length
  const pct     = total > 0 ? Math.round(((done + failed) / total) * 100) : 0

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>{done} / {total} complete {failed > 0 ? `· ${failed} failed` : ""} {running > 0 ? `· ${running} running` : ""}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-1.5 bg-white/[0.07] rounded-full overflow-hidden">
        <div
          className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function BatchResearch() {
  const location     = useLocation()
  const [dragging,   setDragging]   = useState(false)
  const [uploading,  setUploading]  = useState(false)
  const [job,        setJob]        = useState<BatchJob | null>(null)
  const [error,      setError]      = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const pollRef      = useRef<ReturnType<typeof setInterval> | null>(null)

  const startPolling = useCallback((jobId: number) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${API_BASE}/api/batch/${jobId}`, { headers: authHeaders() })
        if (r.ok) {
          const data: BatchJob = await r.json()
          setJob(data)
          if (data.status === "done" || data.status === "partial") {
            clearInterval(pollRef.current!)
          }
        }
      } catch {
        // silently ignore poll errors
      }
    }, 3000)
  }, [])

  // On mount: reload the last batch job from localStorage so navigating
  // away and back doesn't wipe the results.
  // Skip if the user clicked the sidebar "Batch" link (fresh: true) —
  // that means they want a new batch, not the previous one.
  useEffect(() => {
    const isFresh = (location.state as { fresh?: boolean } | null)?.fresh
    if (isFresh) return
    const saved = localStorage.getItem("sc_last_batch_id")
    if (!saved) return
    const jobId = parseInt(saved, 10)
    if (isNaN(jobId)) return
    fetch(`${API_BASE}/api/batch/${jobId}`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then((data: BatchJob | null) => {
        if (data) {
          setJob(data)
          if (data.status === "running") startPolling(data.id)
        }
      })
      .catch(() => {})
  }, [location.state, startPolling])

  async function handleFile(file: File) {
    if (!file.name.endsWith(".csv")) {
      setError("File must be a .csv")
      return
    }
    setError(null)
    setUploading(true)
    setJob(null)

    try {
      const form = new FormData()
      form.append("file", file)
      const r = await fetch(`${API_BASE}/api/batch`, {
        method: "POST",
        headers: authHeaders(),
        body: form,
      })
      const data = await r.json()
      if (!r.ok) {
        setError(data.detail ?? "Upload failed")
        return
      }
      setJob(data as BatchJob)
      localStorage.setItem("sc_last_batch_id", String(data.id))
      if (data.status === "running") {
        startPolling(data.id)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed")
    } finally {
      setUploading(false)
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  const doneCount   = job?.rows.filter(r => r.status === "done").length   ?? 0
  const failedCount = job?.rows.filter(r => r.status === "failed").length ?? 0

  return (
    <div className="max-w-3xl mx-auto px-6 py-6 pb-20 space-y-6">

      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-white">Batch Research</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Upload a CSV to research your entire pipeline at once
        </p>
      </div>

      {/* CSV format guide */}
      <div className="rounded-xl bg-white/[0.05] border border-white/[0.08] px-4 py-3 text-xs text-gray-500 space-y-1">
        <p className="font-medium text-gray-400">CSV format</p>
        <p>Required: <code className="text-indigo-400 bg-white/[0.07] px-1 rounded">name</code> and/or <code className="text-indigo-400 bg-white/[0.07] px-1 rounded">company</code> columns.
          Optional: <code className="text-indigo-400 bg-white/[0.07] px-1 rounded">url</code> column for company websites.</p>
        <p className="text-gray-600">Max 100 rows per batch. Flexible column names: name / prospect / full_name, company / company_name, url / website.</p>
      </div>

      {/* Drop zone */}
      {!job && (
        <div
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`
            relative rounded-2xl border-2 border-dashed cursor-pointer transition-all duration-200
            flex flex-col items-center justify-center gap-3 py-12 px-6
            ${dragging
              ? "border-indigo-500/60 bg-indigo-500/10"
              : "border-white/[0.12] bg-white/[0.02] hover:border-white/[0.20] hover:bg-white/[0.06]"
            }
          `}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleInputChange}
          />

          {uploading ? (
            <div className="flex items-center gap-3 text-sm text-indigo-300">
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
              </svg>
              Uploading and starting batch…
            </div>
          ) : (
            <>
              <svg className="h-10 w-10 text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <div className="text-center">
                <p className="text-sm font-medium text-gray-300">Drop CSV here or click to browse</p>
                <p className="text-xs text-gray-600 mt-1">name, company, url columns</p>
              </div>
              <span className="text-xs text-indigo-400 border border-indigo-500/30 rounded-lg px-3 py-1.5 bg-indigo-500/10">
                Choose file
              </span>
            </>
          )}
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 rounded-xl bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-300">
          <span className="shrink-0">✕</span>
          <span>{error}</span>
        </div>
      )}

      {/* Results */}
      {job && (
        <div className="space-y-4">
          {/* Summary header */}
          <div className="rounded-2xl bg-white/[0.05] border border-white/[0.08] px-5 py-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-gray-200">
                  Batch #{job.id}
                  <span className={`ml-2 text-xs px-2 py-0.5 rounded-full border font-medium ${
                    job.status === "done"    ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                    : job.status === "partial" ? "bg-yellow-500/15 text-yellow-300 border-yellow-500/30"
                    : "bg-indigo-500/15 text-indigo-300 border-indigo-500/30 animate-pulse"
                  }`}>
                    {job.status === "running" ? "Researching…" : job.status}
                  </span>
                </h2>
                <p className="text-xs text-gray-600 mt-0.5">
                  {new Date(job.created_at).toLocaleString()}
                </p>
              </div>
              <button
                onClick={() => { setJob(null); setError(null); localStorage.removeItem("sc_last_batch_id") }}
                className="text-xs text-gray-600 hover:text-gray-400 transition-colors"
              >
                New batch
              </button>
            </div>
            <ProgressBar rows={job.rows} />
          </div>

          {/* Summary stats */}
          {(job.status === "done" || job.status === "partial") && (
            <div className="flex items-center gap-3 text-sm">
              <span className="text-emerald-400 font-medium">{doneCount} researched</span>
              {failedCount > 0 && <span className="text-red-400">{failedCount} failed</span>}
              <span className="text-gray-600">·</span>
              <span className="text-gray-500">Click any row to open the full session</span>
            </div>
          )}

          {/* Row table */}
          <div className="rounded-2xl bg-white/[0.05] border border-white/[0.08] overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-white/[0.07]">
                  <th className="text-left px-4 py-3 text-gray-600 font-medium">#</th>
                  <th className="text-left px-4 py-3 text-gray-600 font-medium">Prospect</th>
                  <th className="text-left px-4 py-3 text-gray-600 font-medium">Company</th>
                  <th className="text-left px-4 py-3 text-gray-600 font-medium">Status</th>
                  <th className="text-left px-4 py-3 text-gray-600 font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.05]">
                {job.rows.map(row => (
                  <tr key={row.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-4 py-3 text-gray-600">{row.row_index + 1}</td>
                    <td className="px-4 py-3 text-gray-300 font-medium">
                      {row.prospect_name ?? <span className="text-gray-600 italic">—</span>}
                    </td>
                    <td className="px-4 py-3 text-gray-400">
                      <div>
                        {row.company_name ?? <span className="text-gray-600 italic">—</span>}
                        {row.company_url && (
                          <p className="text-gray-600 truncate max-w-[160px]">
                            {row.company_url.replace("https://", "").replace("http://", "")}
                          </p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="space-y-1">
                        <StatusPill status={row.status} />
                        {row.error_msg && (
                          <p className="text-[10px] text-red-400 max-w-[200px] truncate" title={row.error_msg}>
                            {row.error_msg}
                          </p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {row.session_id ? (
                        <Link
                          to={`/session/${row.session_id}`}
                          className="text-indigo-400 hover:text-indigo-300 transition-colors font-medium"
                        >
                          View →
                        </Link>
                      ) : (
                        <span className="text-gray-700">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
