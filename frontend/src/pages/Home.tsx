// frontend/src/pages/Home.tsx
import { Link } from "react-router-dom"
import { useAuth } from "../context/AuthContext"

const FEATURES = [
  {
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 1 1 5 11a6 6 0 0 1 12 0z" />
      </svg>
    ),
    title: "Deep Prospect Research",
    desc: "Aggregates public web data — news, profiles, company pages — into a single crisp brief in under 60 seconds.",
    color: "text-indigo-400",
    bg: "bg-indigo-500/10 border-indigo-500/20",
  },
  {
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
    title: "Batch CSV Research",
    desc: "Upload your entire pipeline as a CSV. Research all prospects in parallel — results in minutes, not hours.",
    color: "text-violet-400",
    bg: "bg-violet-500/10 border-violet-500/20",
  },
  {
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.562.562 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" />
      </svg>
    ),
    title: "ICP Fit Scoring",
    desc: "Define your Ideal Customer Profile once. Every prospect gets a 1–10 score with a breakdown by criterion.",
    color: "text-amber-400",
    bg: "bg-amber-500/10 border-amber-500/20",
  },
  {
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
      </svg>
    ),
    title: "AI Follow-up Emails",
    desc: "Three tones — warm follow-up, cold outreach, re-engagement. Personalised from your call notes and the prospect profile.",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10 border-emerald-500/20",
  },
  {
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 18.75a6 6 0 006-6v-1.5m-6 7.5a6 6 0 01-6-6v-1.5m6 7.5v3.75m-3.75 0h7.5M12 15.75a3 3 0 01-3-3V4.5a3 3 0 116 0v8.25a3 3 0 01-3 3z" />
      </svg>
    ),
    title: "Transcript Analysis",
    desc: "Paste a Zoom or Fireflies transcript. Get meeting summary, sentiment, pain points, objections, and next steps extracted instantly.",
    color: "text-sky-400",
    bg: "bg-sky-500/10 border-sky-500/20",
  },
  {
    icon: (
      <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 2.625c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125m16.5 5.625c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" />
      </svg>
    ),
    title: "RAG + Semantic Search",
    desc: "Every research session is chunked and embedded. Search your entire history with natural language — \"SaaS companies worried about churn\".",
    color: "text-rose-400",
    bg: "bg-rose-500/10 border-rose-500/20",
  },
]

const HOW_IT_WORKS = [
  { step: "01", title: "Enter a company URL + prospect name", desc: "Or upload a CSV to research your whole pipeline at once." },
  { step: "02", title: "AI scrapes and synthesises", desc: "Company summary, prospect profile, news signals, and a full pre-call briefing — streamed live." },
  { step: "03", title: "Walk in ready", desc: "Talking points, personalisation hooks, likely objections, and a suggested CTA — all grounded in real data." },
]

export default function Home() {
  const { user } = useAuth()

  return (
    <div className="max-w-4xl mx-auto px-6 py-12 pb-24 space-y-20">

      {/* ── Hero ──────────────────────────────────────────────────────────────── */}
      <div className="text-center space-y-6">
        <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 text-xs font-medium px-3 py-1.5 rounded-full">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
          Powered by Groq · LLaMA 3.3 70B
        </div>

        <h1 className="text-4xl sm:text-5xl font-bold text-white leading-tight tracking-tight">
          Know your prospect<br />
          <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-violet-400">
            before you dial.
          </span>
        </h1>

        <p className="text-gray-400 text-base leading-relaxed max-w-xl mx-auto">
          Sales Copilot researches any company and prospect in seconds — giving you a
          full briefing, personalised talking points, and AI-drafted follow-ups,
          so every call is your best call.
        </p>

        <div className="flex items-center justify-center gap-3 pt-2">
          {user ? (
            <Link
              to="/research"
              className="inline-flex items-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold rounded-xl transition-all shadow-lg shadow-indigo-900/40 hover:shadow-indigo-900/60"
            >
              Start New Research
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
              </svg>
            </Link>
          ) : (
            <>
              <Link
                to="/signup"
                className="inline-flex items-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold rounded-xl transition-all shadow-lg shadow-indigo-900/40"
              >
                Get started free
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
                </svg>
              </Link>
              <Link
                to="/login"
                className="px-5 py-3 text-sm text-gray-400 hover:text-gray-200 border border-white/[0.10] hover:border-white/20 rounded-xl transition-all"
              >
                Sign in
              </Link>
            </>
          )}
        </div>
      </div>

      {/* ── Features grid ────────────────────────────────────────────────────── */}
      <div>
        <p className="text-xs font-semibold text-gray-600 uppercase tracking-widest text-center mb-8">
          Everything your pipeline needs
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map(f => (
            <div
              key={f.title}
              className="rounded-2xl bg-white/[0.03] border border-white/[0.08] p-5 space-y-3 hover:bg-white/[0.05] hover:border-white/[0.12] transition-all duration-200"
            >
              <div className={`w-9 h-9 rounded-xl border flex items-center justify-center ${f.bg} ${f.color}`}>
                {f.icon}
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-200">{f.title}</p>
                <p className="text-xs text-gray-500 leading-relaxed mt-1">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── How it works ─────────────────────────────────────────────────────── */}
      <div className="rounded-2xl bg-white/[0.03] border border-white/[0.08] px-8 py-8 space-y-6">
        <p className="text-xs font-semibold text-gray-600 uppercase tracking-widest">How it works</p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          {HOW_IT_WORKS.map(({ step, title, desc }) => (
            <div key={step} className="space-y-2">
              <span className="text-2xl font-bold text-indigo-500/30 font-mono">{step}</span>
              <p className="text-sm font-semibold text-gray-200">{title}</p>
              <p className="text-xs text-gray-500 leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Social proof / stat strip ─────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-4 text-center">
        {[
          { stat: "< 60s",   label: "Full prospect brief" },
          { stat: "6+",      label: "AI-powered features" },
          { stat: "100%",    label: "Built on public data" },
        ].map(({ stat, label }) => (
          <div key={label} className="rounded-2xl bg-white/[0.03] border border-white/[0.08] py-6 px-4">
            <p className="text-2xl font-bold text-white">{stat}</p>
            <p className="text-xs text-gray-500 mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* ── Bottom CTA ───────────────────────────────────────────────────────── */}
      {!user && (
        <div className="text-center rounded-2xl bg-gradient-to-br from-indigo-600/20 to-violet-600/10 border border-indigo-500/20 py-12 px-6 space-y-5">
          <h2 className="text-2xl font-bold text-white">Ready to walk into every call prepared?</h2>
          <p className="text-gray-400 text-sm max-w-sm mx-auto">
            Free to use. No credit card. Your first research session takes 60 seconds.
          </p>
          <Link
            to="/signup"
            className="inline-flex items-center gap-2 px-6 py-3 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold rounded-xl transition-all shadow-lg shadow-indigo-900/40"
          >
            Create free account →
          </Link>
        </div>
      )}

    </div>
  )
}
