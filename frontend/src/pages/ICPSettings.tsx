// frontend/src/pages/ICPSettings.tsx
/**
 * Define your Ideal Customer Profile.
 * Saved to the backend and used to score every prospect 1-10.
 */

import { useEffect, useState } from "react"

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000")
  .toString()
  .replace(/\/$/, "")

function authHeaders(): HeadersInit {
  const stored = localStorage.getItem("sc_auth")
  const token = stored ? (JSON.parse(stored) as { token?: string }).token : null
  return token
    ? { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }
    : { "Content-Type": "application/json" }
}

interface ICPProfile {
  industry:     string | null
  company_size: string | null
  roles:        string | null
  pain_points:  string | null
  signals:      string | null
}

const inputCls = `
  w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-3.5 py-2.5
  text-sm text-gray-200 placeholder-gray-600
  focus:outline-none focus:border-indigo-500/60 focus:bg-white/[0.07]
  transition-colors duration-200
`

export default function ICPSettings() {
  const [form, setForm] = useState<ICPProfile>({
    industry: "", company_size: "", roles: "", pain_points: "", signals: "",
  })
  const [loading, setLoading] = useState(true)
  const [saving,  setSaving]  = useState(false)
  const [saved,   setSaved]   = useState(false)
  const [error,   setError]   = useState<string | null>(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/icp`, { headers: authHeaders() })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data) setForm({
          industry:     data.industry     ?? "",
          company_size: data.company_size ?? "",
          roles:        data.roles        ?? "",
          pain_points:  data.pain_points  ?? "",
          signals:      data.signals      ?? "",
        })
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  function update(field: keyof ICPProfile, value: string) {
    setForm(prev => ({ ...prev, [field]: value }))
    setSaved(false)
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    try {
      const r = await fetch(`${API_BASE}/api/icp`, {
        method:  "POST",
        headers: authHeaders(),
        body:    JSON.stringify(form),
      })
      if (!r.ok) {
        const d = await r.json().catch(() => ({}))
        throw new Error(d.detail ?? "Save failed")
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-gray-500 gap-2">
        <svg className="animate-spin h-4 w-4 text-indigo-400" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
        Loading…
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-6 py-6 pb-20 space-y-6">

      <div>
        <h1 className="text-xl font-bold text-white">ICP Settings</h1>
        <p className="text-sm text-gray-500 mt-0.5">
          Define your Ideal Customer Profile. Every prospect will be scored 1–10 against it.
        </p>
      </div>

      <div className="rounded-2xl bg-white/[0.05] border border-white/[0.08] p-5 space-y-5">

        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">
            Target Industries
          </label>
          <input
            className={inputCls}
            placeholder="e.g. SaaS, B2B Tech, Financial Services"
            value={form.industry ?? ""}
            onChange={e => update("industry", e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">
            Company Size
          </label>
          <input
            className={inputCls}
            placeholder="e.g. 50-500 employees, Series A-C, $5M-$100M ARR"
            value={form.company_size ?? ""}
            onChange={e => update("company_size", e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">
            Target Roles / Titles
          </label>
          <input
            className={inputCls}
            placeholder="e.g. VP Sales, CRO, Head of Revenue, Director of Sales Ops"
            value={form.roles ?? ""}
            onChange={e => update("roles", e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">
            Pain Points Your Product Solves
          </label>
          <textarea
            className={`${inputCls} h-20 resize-none`}
            placeholder="e.g. Manual reporting taking 3+ hours/week, sales forecasting inaccuracy, rep ramp time over 90 days"
            value={form.pain_points ?? ""}
            onChange={e => update("pain_points", e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-gray-400 mb-1.5">
            Positive Buying Signals
          </label>
          <textarea
            className={`${inputCls} h-20 resize-none`}
            placeholder="e.g. Recent funding, headcount growth, new sales leader hire, using Salesforce, competitor mentioned in blog"
            value={form.signals ?? ""}
            onChange={e => update("signals", e.target.value)}
          />
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-white/[0.06]">
          {error && (
            <p className="text-xs text-red-400">{error}</p>
          )}
          {saved && (
            <p className="text-xs text-emerald-400 flex items-center gap-1">
              <span className="w-4 h-4 rounded-full bg-emerald-500 text-white text-[10px] flex items-center justify-center">✓</span>
              Saved
            </p>
          )}
          {!error && !saved && <div />}

          <button
            onClick={handleSave}
            disabled={saving}
            className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all
              ${saving
                ? "bg-indigo-600/40 text-indigo-300/50 cursor-not-allowed"
                : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-900/40"
              }`}
          >
            {saving ? "Saving…" : "Save ICP"}
          </button>
        </div>
      </div>

      <div className="rounded-xl bg-amber-500/[0.07] border border-amber-500/20 px-4 py-3 text-xs text-amber-400/80 space-y-1">
        <p className="font-medium text-amber-400">How scoring works</p>
        <p>After running prospect research, open any session and click "Score vs ICP". The AI reads the prospect profile and your ICP, then returns a 1–10 score with a per-criterion breakdown.</p>
      </div>
    </div>
  )
}
