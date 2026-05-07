// frontend/src/components/Sidebar.tsx
/**
 * ChatGPT-style persistent left sidebar.
 * Shows the session list with search, highlights the active session,
 * and navigates to /session/:id on click.
 *
 * Re-fetches the list whenever the pathname changes so newly-created
 * sessions appear immediately after Research redirects.
 */

import { useCallback, useEffect, useRef, useState } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000")
  .toString()
  .replace(/\/$/, "")

interface SidebarSession {
  id:              number
  prospect_name:   string | null
  company_name:    string | null
  created_at:      string
  call_outcome:    string | null
  has_report:      boolean
}

interface SearchResult {
  session_id:    number
  company_name:  string | null
  prospect_name: string | null
  created_at:    string
  score:         number
  excerpt:       string
}

const OUTCOME_DOTS: Record<string, string> = {
  "booked":         "bg-emerald-400",
  "follow-up":      "bg-indigo-400",
  "not-interested": "bg-red-400",
  "no-show":        "bg-yellow-400",
}

function relativeDate(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86_400_000)
  if (diffDays === 0) return "Today"
  if (diffDays === 1) return "Yesterday"
  if (diffDays < 7)  return `${diffDays}d ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" })
}

export default function Sidebar() {
  const { pathname } = useLocation()
  const navigate = useNavigate()

  const [sessions,      setSessions]      = useState<SidebarSession[]>([])
  const [query,         setQuery]         = useState("")
  const [loading,       setLoading]       = useState(true)
  const [searching,     setSearching]     = useState(false)
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null)
  const inputRef    = useRef<HTMLInputElement>(null)
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const load = useCallback(async () => {
    try {
      const stored = localStorage.getItem("sc_auth")
      const token = stored ? (JSON.parse(stored) as { token?: string }).token : null
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
      const r = await fetch(`${API_BASE}/api/history`, { headers })
      if (r.ok) setSessions(await r.json())
    } catch {
      // silently ignore
    } finally {
      setLoading(false)
    }
  }, [])

  // Re-fetch whenever the user navigates (catches newly created sessions)
  useEffect(() => { load() }, [load, pathname])

  // Debounced semantic search — fires 500ms after user stops typing
  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)

    const q = query.trim()
    if (!q) {
      setSearchResults(null)
      return
    }

    // Instant local filter for very short queries (< 3 chars)
    if (q.length < 3) {
      setSearchResults(null)
      return
    }

    searchTimer.current = setTimeout(async () => {
      setSearching(true)
      try {
        const stored = localStorage.getItem("sc_auth")
        const token  = stored ? (JSON.parse(stored) as { token?: string }).token : null
        const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {}
        const r = await fetch(`${API_BASE}/api/history/search?q=${encodeURIComponent(q)}&limit=8`, { headers })
        if (r.ok) {
          const data: SearchResult[] = await r.json()
          setSearchResults(data)
        }
      } catch {
        setSearchResults(null)
      } finally {
        setSearching(false)
      }
    }, 500)
  }, [query])

  const activeId = pathname.startsWith("/session/")
    ? parseInt(pathname.split("/")[2] ?? "", 10)
    : null

  // Local string filter for short queries; semantic results for longer ones
  const useSemanticResults = searchResults !== null
  const filtered = query.trim()
    ? useSemanticResults
      ? [] // replaced by search results section below
      : sessions.filter(s => {
          const q = query.toLowerCase()
          return (
            s.prospect_name?.toLowerCase().includes(q) ||
            s.company_name?.toLowerCase().includes(q)
          )
        })
    : sessions

  return (
    <aside
      className="flex flex-col w-60 shrink-0 bg-[#111111] border-r border-white/[0.07]
                 overflow-hidden h-full"
    >
      {/* Top: logo + new button */}
      <div className="px-3 pt-4 pb-3 shrink-0">
        <Link
          to="/"
          className="flex items-center gap-2 px-2 mb-3 group"
        >
          <span className="text-sm font-bold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-violet-400">
            Sales Copilot
          </span>
        </Link>

        <Link
          to="/research"
          className="flex items-center gap-2 w-full px-3 py-2 rounded-lg
                     bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium
                     transition-colors shadow-lg shadow-indigo-900/40"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New Research
        </Link>

        {/* Utility links */}
        <div className="flex gap-1 mt-1">
          <Link
            to="/batch"
            state={{ fresh: true }}
            className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg text-[11px] font-medium transition-colors
              ${pathname === "/batch"
                ? "bg-white/[0.08] text-gray-200"
                : "text-gray-500 hover:text-gray-300 hover:bg-white/[0.05]"}`}
            title="Batch CSV Research"
          >
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Batch
          </Link>
          <Link
            to="/icp"
            className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 rounded-lg text-[11px] font-medium transition-colors
              ${pathname === "/icp"
                ? "bg-white/[0.08] text-gray-200"
                : "text-gray-500 hover:text-gray-300 hover:bg-white/[0.05]"}`}
            title="ICP Settings"
          >
            <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            ICP
          </Link>
        </div>
      </div>

      {/* Search */}
      <div className="px-3 pb-2 shrink-0">
        <div className="relative">
          <svg
            className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-gray-600"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
          </svg>
          <input
            ref={inputRef}
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Search sessions…"
            className="w-full bg-white/[0.05] border border-white/[0.09] rounded-lg
                       pl-7 pr-6 py-1.5 text-xs text-gray-300 placeholder-gray-600
                       focus:outline-none focus:border-indigo-500/50 transition-colors"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-400 text-[10px]"
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto px-2 pb-4 space-y-0.5 scrollbar-thin">
        {loading ? (
          <div className="flex items-center justify-center py-8">
            <svg className="animate-spin h-4 w-4 text-indigo-400" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
        ) : useSemanticResults ? (
          /* ── Semantic search results ── */
          <>
            <div className="flex items-center gap-1.5 px-3 py-1.5">
              {searching ? (
                <svg className="animate-spin h-3 w-3 text-indigo-400 shrink-0" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              ) : (
                <span className="text-[9px] font-medium text-indigo-400/70 uppercase tracking-wider">
                  Semantic · {searchResults!.length} result{searchResults!.length !== 1 ? "s" : ""}
                </span>
              )}
            </div>
            {searchResults!.length === 0 && !searching && (
              <p className="text-xs text-gray-600 px-3 py-4 text-center">No matches found</p>
            )}
            {searchResults!.map(r => {
              const isActive = r.session_id === activeId
              const label = r.prospect_name ?? r.company_name ?? "Untitled"
              const sub   = r.prospect_name && r.company_name ? r.company_name : null
              return (
                <button
                  key={r.session_id}
                  onClick={() => navigate(`/session/${r.session_id}`)}
                  className={`
                    w-full text-left px-3 py-2.5 rounded-lg transition-colors duration-150
                    ${isActive
                      ? "bg-indigo-600/20 border border-indigo-500/30"
                      : "hover:bg-white/[0.05] border border-transparent"
                    }
                  `}
                >
                  <div className="flex items-start justify-between gap-1">
                    <span className={`text-xs font-medium truncate ${isActive ? "text-indigo-200" : "text-gray-300"}`}>
                      {label}
                    </span>
                    <span className="text-[10px] text-gray-600 shrink-0 mt-0.5">
                      {relativeDate(r.created_at)}
                    </span>
                  </div>
                  {sub && <p className="text-[10px] text-gray-600 truncate mt-0.5">{sub}</p>}
                  {r.excerpt && (
                    <p className="text-[10px] text-gray-600 mt-1 leading-relaxed line-clamp-2">
                      {r.excerpt}
                    </p>
                  )}
                </button>
              )
            })}
          </>
        ) : filtered.length === 0 ? (
          <p className="text-xs text-gray-600 px-3 py-6 text-center">
            {query ? "No matches" : "No sessions yet"}
          </p>
        ) : (
          filtered.map(s => {
            const isActive = s.id === activeId
            const label = s.prospect_name ?? s.company_name ?? "Untitled"
            const sub   = s.prospect_name && s.company_name ? s.company_name : null

            return (
              <button
                key={s.id}
                onClick={() => navigate(`/session/${s.id}`)}
                className={`
                  w-full text-left px-3 py-2.5 rounded-lg transition-colors duration-150 group
                  ${isActive
                    ? "bg-indigo-600/20 border border-indigo-500/30"
                    : "hover:bg-white/[0.05] border border-transparent"
                  }
                `}
              >
                <div className="flex items-start justify-between gap-1">
                  <div className="flex items-center gap-1.5 min-w-0">
                    {s.call_outcome && (
                      <span className={`w-1.5 h-1.5 rounded-full shrink-0 mt-1 ${OUTCOME_DOTS[s.call_outcome] ?? "bg-gray-500"}`} />
                    )}
                    <span className={`text-xs font-medium truncate ${isActive ? "text-indigo-200" : "text-gray-300"}`}>
                      {label}
                    </span>
                  </div>
                  <span className="text-[10px] text-gray-600 shrink-0 mt-0.5">
                    {relativeDate(s.created_at)}
                  </span>
                </div>
                {sub && (
                  <p className="text-[10px] text-gray-600 truncate pl-3 mt-0.5">{sub}</p>
                )}
              </button>
            )
          })
        )}
      </div>
    </aside>
  )
}
