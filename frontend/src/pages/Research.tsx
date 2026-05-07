// frontend/src/pages/Research.tsx
/**
 * Unified Research Wizard
 *
 * Three-step flow — state passes forward automatically, zero copy-paste:
 *   Step 1  Company   → crawl website, stream summary
 *   Step 2  Prospect  → DuckDuckGo + scrape, stream insights
 *   Step 3  Report    → combine both, stream pre-call briefing
 *
 * Uses the useStream hook for all three SSE endpoints.
 */

import { useState, useRef } from "react"
import { useNavigate } from "react-router-dom"
import ReactMarkdown from "react-markdown"
import type { Components } from "react-markdown"
import { useStream } from "../hooks/useStream"
import { exportToPdf } from "../lib/exportPdf"

// ── Markdown renderer ──────────────────────────────────────────────────────────

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

// ── Small shared pieces ───────────────────────────────────────────────────────

function Spinner() {
  return (
    <svg className="animate-spin h-3.5 w-3.5 text-indigo-400" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  )
}

function StatusPill({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-2 text-xs text-indigo-300 py-1">
      <Spinner />
      <span>{text}</span>
    </div>
  )
}

function ErrorBanner({ msg }: { msg: string }) {
  return (
    <div className="flex items-start gap-2 rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2.5 text-xs text-red-300">
      <span className="shrink-0 mt-0.5">✕</span>
      <span>{msg}</span>
    </div>
  )
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000) }}
      className="text-xs text-gray-500 hover:text-gray-300 transition-colors flex items-center gap-1"
    >
      {copied ? "✓ Copied" : "Copy"}
    </button>
  )
}

function StreamOutput({
  content, status, isStreaming, error, label,
}: {
  content: string; status: string; isStreaming: boolean; error: string | null; label: string
}) {
  if (!isStreaming && !content && !error && !status) return null
  return (
    <div className="mt-4 space-y-2">
      {(isStreaming || status) && !error && <StatusPill text={status || "Generating…"} />}
      {error && <ErrorBanner msg={error} />}
      {content && (
        <div className="rounded-xl bg-black/30 border border-white/[0.06] p-4">
          <div className="flex items-center justify-between mb-3">
            <span className="text-[10px] font-medium text-gray-500 uppercase tracking-widest">{label}</span>
            <div className="flex items-center gap-3">
              {isStreaming && (
                <span className="inline-block w-1.5 h-3.5 bg-indigo-400 rounded-sm animate-pulse" />
              )}
              {!isStreaming && <CopyButton text={content} />}
            </div>
          </div>
          <div className="overflow-y-auto max-h-[420px] pr-1 scrollbar-thin">
            <ReactMarkdown components={MD}>{content}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Step indicator ─────────────────────────────────────────────────────────────

const STEPS = ["Company", "Prospect", "Report"] as const
type StepId = 0 | 1 | 2

function StepIndicator({ current, done }: { current: StepId; done: Set<StepId> }) {
  return (
    <div className="flex items-center justify-center gap-0 mb-8 select-none">
      {STEPS.map((label, i) => {
        const idx = i as StepId
        const isDone    = done.has(idx)
        const isActive  = current === idx
        const isPending = !isDone && !isActive
        return (
          <div key={label} className="flex items-center">
            <div className={`
              flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium transition-all duration-300
              ${isDone    ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30" : ""}
              ${isActive  ? "bg-indigo-500/20  text-indigo-300  border border-indigo-500/40" : ""}
              ${isPending ? "bg-white/[0.06]   text-gray-500    border border-white/[0.08]"  : ""}
            `}>
              <span className={`
                w-4 h-4 rounded-full flex items-center justify-center text-[10px] font-bold
                ${isDone   ? "bg-emerald-500 text-white"  : ""}
                ${isActive ? "bg-indigo-500  text-white"  : ""}
                ${isPending? "bg-white/10    text-gray-400": ""}
              `}>
                {isDone ? "✓" : i + 1}
              </span>
              {label}
            </div>
            {i < STEPS.length - 1 && (
              <div className={`w-8 h-px mx-1 transition-colors duration-500
                ${done.has(idx) ? "bg-emerald-500/40" : "bg-white/[0.08]"}`}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Completed step card ────────────────────────────────────────────────────────

function CompletedCard({
  title, subtitle, content, onEdit,
}: {
  title: string; subtitle: string; content: string; onEdit: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className="rounded-2xl bg-emerald-500/[0.05] border border-emerald-500/20 p-4 mb-4 transition-all duration-300">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="w-5 h-5 rounded-full bg-emerald-500 text-white text-[10px] font-bold flex items-center justify-center shrink-0">✓</span>
          <div>
            <span className="text-sm font-medium text-gray-200">{title}</span>
            <span className="text-xs text-gray-500 ml-2">{subtitle}</span>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={() => setExpanded(e => !e)}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors">
            {expanded ? "Collapse" : "Expand"}
          </button>
          <button onClick={onEdit}
            className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
            ← Edit
          </button>
        </div>
      </div>
      {expanded && (
        <div className="mt-3 pt-3 border-t border-white/[0.06] max-h-48 overflow-y-auto">
          <ReactMarkdown components={MD}>{content}</ReactMarkdown>
        </div>
      )}
    </div>
  )
}

// ── Input primitives ───────────────────────────────────────────────────────────

const inputCls = `
  w-full bg-white/[0.05] border border-white/[0.10] rounded-xl px-3.5 py-2.5
  text-sm text-gray-200 placeholder-gray-600
  focus:outline-none focus:border-indigo-500/60 focus:bg-white/[0.07]
  transition-colors duration-200
`

function Label({ children }: { children: React.ReactNode }) {
  return <label className="block text-xs font-medium text-gray-400 mb-1.5">{children}</label>
}

function PrimaryButton({
  onClick, disabled, loading, children,
}: {
  onClick: () => void; disabled?: boolean; loading?: boolean; children: React.ReactNode
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={`
        flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200
        ${disabled || loading
          ? "bg-indigo-600/40 text-indigo-300/50 cursor-not-allowed"
          : "bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-900/40 hover:shadow-indigo-900/60"
        }
      `}
    >
      {loading && <Spinner />}
      {children}
    </button>
  )
}

function StepCard({ title, stepNum, children }: { title: string; stepNum: number; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl bg-white/[0.06] border border-indigo-500/25 shadow-xl shadow-black/20 overflow-hidden">
      <div className="px-6 py-4 border-b border-white/[0.06] flex items-center gap-3">
        <span className="w-6 h-6 rounded-full bg-indigo-600 text-white text-xs font-bold flex items-center justify-center shrink-0">
          {stepNum}
        </span>
        <h2 className="text-sm font-semibold text-gray-200">{title}</h2>
      </div>
      <div className="p-6">{children}</div>
    </div>
  )
}

// ── Meta types ─────────────────────────────────────────────────────────────────

interface CompanyMeta  { session_id: number; source_id: number }
interface ProspectMeta { session_id: number; source_id: number; sources_searched: string[]; used_rag: boolean }
interface ReportMeta   { session_id: number | null }

// ── Wizard ─────────────────────────────────────────────────────────────────────

export default function Research() {
  const navigate = useNavigate()

  // Step tracking
  const [currentStep, setCurrentStep] = useState<StepId>(0)
  const [doneSteps,   setDoneSteps]   = useState<Set<StepId>>(new Set())

  // Company
  const [companyUrl,     setCompanyUrl]     = useState("")
  const [companySummary, setCompanySummary] = useState("")
  const [sessionId,      setSessionId]      = useState<number | null>(null)

  // Prospect
  const [prospectName,    setProspectName]    = useState("")
  const [linkedinUrl,     setLinkedinUrl]     = useState("")
  const [extraContext,    setExtraContext]     = useState("")
  const [prospectInsights,setProspectInsights]= useState("")
  const [sourcesFound,    setSourcesFound]    = useState<string[]>([])

  // Report
  const [tone, setTone] = useState("concise, friendly, expert")

  // Streams
  const companyStream  = useStream<CompanyMeta> ("/api/company/summary")
  const prospectStream = useStream<ProspectMeta>("/api/research/prospect")
  const reportStream   = useStream<ReportMeta>  ("/api/report/precall")

  const scrollRef    = useRef<HTMLDivElement>(null)
  const reportPdfRef = useRef<HTMLDivElement>(null)
  const markDone = (step: StepId) =>
    setDoneSteps(prev => new Set([...prev, step]))

  // ── Handlers ────────────────────────────────────────────────────────────────

  async function handleCompanyResearch() {
    companyStream.reset()
    const { content, meta } = await companyStream.start({ url: companyUrl, bullets: 6 })
    if (!content) return   // error banner already shown by StreamOutput
    setCompanySummary(content)
    if (meta?.session_id) setSessionId(meta.session_id)
    markDone(0)
    setCurrentStep(1)
    setTimeout(() => scrollRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100)
  }

  async function handleProspectResearch() {
    prospectStream.reset()
    const { content, meta } = await prospectStream.start({
      name:          prospectName.trim(),
      company_name:  companyUrl
        ? (() => { try { return new URL(companyUrl).hostname.replace("www.", "") } catch { return companyUrl } })()
        : "the company",
      session_id:    sessionId,
      extra_context: extraContext.trim()  || undefined,
      linkedin_url:  linkedinUrl.trim()   || undefined,
    })
    if (!content) return   // error banner already shown by StreamOutput
    setProspectInsights(content)
    if (meta?.sources_searched) setSourcesFound(meta.sources_searched)
    markDone(1)
    setCurrentStep(2)
    setTimeout(() => scrollRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100)
  }

  async function handleGenerateReport() {
    reportStream.reset()
    const { content, meta } = await reportStream.start({
      company:    companySummary,
      prospect:   prospectInsights,
      tone:       tone,
      session_id: sessionId,
    })
    if (content) {
      markDone(2)
      // Navigate to the session detail view so the sidebar refreshes and
      // the user lands on the full session page.
      const sid = sessionId ?? (meta as ReportMeta | null)?.session_id
      if (sid) {
        setTimeout(() => navigate(`/session/${sid}`), 1200)
      }
    }
  }

  function handleReset() {
    companyStream.reset(); prospectStream.reset(); reportStream.reset()
    setCurrentStep(0); setDoneSteps(new Set())
    setCompanyUrl(""); setCompanySummary(""); setSessionId(null)
    setProspectName(""); setLinkedinUrl(""); setExtraContext(""); setProspectInsights("")
    setSourcesFound([])
    setTone("concise, friendly, expert")
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  const companyHostname = companyUrl
    ? (() => { try { return new URL(companyUrl).hostname.replace("www.", "") } catch { return companyUrl } })()
    : ""

  return (
    <div className="max-w-2xl mx-auto space-y-4 pb-16">

      {/* Header */}
      <div className="text-center pt-4 pb-2">
        <h1 className="text-2xl font-bold text-white mb-1">New Research</h1>
        <p className="text-sm text-gray-500">Company → Prospect → Pre-Call Report</p>
      </div>

      <StepIndicator current={currentStep} done={doneSteps} />

      {/* ── STEP 1: Company ─────────────────────────────────────────────────── */}
      {doneSteps.has(0) && (
        <CompletedCard
          title="Company Research" subtitle={companyHostname}
          content={companySummary}
          onEdit={() => { setCurrentStep(0); setDoneSteps(new Set()) }}
        />
      )}

      {currentStep === 0 && (
        <StepCard title="Research Company" stepNum={1}>
          <div className="space-y-4">
            <div>
              <Label>Company Website URL</Label>
              <input
                className={inputCls}
                placeholder="https://stripe.com"
                value={companyUrl}
                onChange={e => setCompanyUrl(e.target.value)}
                onKeyDown={e => {
                  if (e.key === "Enter" && companyUrl.trim() && !companyStream.isStreaming)
                    handleCompanyResearch()
                }}
              />
            </div>
            <div className="flex justify-end">
              <PrimaryButton
                onClick={handleCompanyResearch}
                disabled={!companyUrl.trim()}
                loading={companyStream.isStreaming}
              >
                Research Company →
              </PrimaryButton>
            </div>
            <StreamOutput
              content={companyStream.content}
              status={companyStream.status}
              isStreaming={companyStream.isStreaming}
              error={companyStream.error}
              label="Company Overview"
            />
          </div>
        </StepCard>
      )}

      {/* ── STEP 2: Prospect ────────────────────────────────────────────────── */}
      {doneSteps.has(1) && (
        <CompletedCard
          title="Prospect Research" subtitle={prospectName}
          content={prospectInsights}
          onEdit={() => { setCurrentStep(1); setDoneSteps(new Set([0])) }}
        />
      )}

      {currentStep === 1 && (
        <div ref={scrollRef}>
          <StepCard title="Research Prospect" stepNum={2}>
            <div className="space-y-4">
              <div>
                <Label>Prospect Full Name</Label>
                <input
                  className={inputCls}
                  placeholder="e.g. Patrick Collison"
                  value={prospectName}
                  onChange={e => setProspectName(e.target.value)}
                />
              </div>
              <div>
                <Label>
                  LinkedIn URL
                  <span className="ml-1 text-gray-600 font-normal">(optional — scrapes public profile via Firecrawl)</span>
                </Label>
                <input
                  className={inputCls}
                  placeholder="https://linkedin.com/in/name"
                  value={linkedinUrl}
                  onChange={e => setLinkedinUrl(e.target.value)}
                />
              </div>

              <div>
                <Label>
                  Extra Context
                  <span className="ml-1 text-gray-600 font-normal">(optional — paste anything you know)</span>
                </Label>
                <textarea
                  className={`${inputCls} h-20 resize-none`}
                  placeholder="Email signature, intro message, LinkedIn blurb, meeting notes…"
                  value={extraContext}
                  onChange={e => setExtraContext(e.target.value)}
                />
              </div>

              {sourcesFound.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {sourcesFound.slice(0, 5).map(url => {
                    const host = (() => { try { return new URL(url).hostname.replace("www.", "") } catch { return url } })()
                    return (
                      <span key={url} className="text-[10px] bg-white/[0.05] border border-white/[0.08] text-gray-500 px-2 py-0.5 rounded-full">
                        {host}
                      </span>
                    )
                  })}
                </div>
              )}

              <div className="flex justify-end">
                <PrimaryButton
                  onClick={handleProspectResearch}
                  disabled={!prospectName.trim()}
                  loading={prospectStream.isStreaming}
                >
                  Research Prospect →
                </PrimaryButton>
              </div>
              <StreamOutput
                content={prospectStream.content}
                status={prospectStream.status}
                isStreaming={prospectStream.isStreaming}
                error={prospectStream.error}
                label="Prospect Profile"
              />
            </div>
          </StepCard>
        </div>
      )}

      {/* ── STEP 3: Report ──────────────────────────────────────────────────── */}
      {currentStep === 2 && (
        <div ref={currentStep === 2 ? scrollRef : undefined}>
          <StepCard title="Generate Pre-Call Report" stepNum={3}>
            <div className="space-y-4">
              <div>
                <Label>
                  Tone
                  <span className="ml-1 text-gray-600 font-normal">(optional)</span>
                </Label>
                <input
                  className={inputCls}
                  value={tone}
                  onChange={e => setTone(e.target.value)}
                  placeholder="concise, friendly, expert"
                />
              </div>
              <div className="flex justify-end">
                <PrimaryButton
                  onClick={handleGenerateReport}
                  disabled={doneSteps.has(2)}
                  loading={reportStream.isStreaming}
                >
                  Generate Report →
                </PrimaryButton>
              </div>
              <div ref={reportPdfRef}>
                <StreamOutput
                  content={reportStream.content}
                  status={reportStream.status}
                  isStreaming={reportStream.isStreaming}
                  error={reportStream.error}
                  label="Pre-Call Report"
                />
              </div>
            </div>
          </StepCard>
        </div>
      )}

      {/* ── Done state ──────────────────────────────────────────────────────── */}
      {doneSteps.has(2) && !reportStream.isStreaming && (
        <div className="flex flex-col items-center gap-3 pt-4">
          <div className="text-sm text-emerald-400 font-medium flex items-center gap-2">
            <span className="w-5 h-5 rounded-full bg-emerald-500 text-white text-[10px] flex items-center justify-center">✓</span>
            Report saved to history
          </div>
          <div className="flex items-center gap-4">
            <button
              onClick={() => {
                if (reportPdfRef.current) {
                  const title = prospectName
                    ? `${prospectName} — Pre-Call Report`
                    : "Pre-Call Report"
                  exportToPdf(reportPdfRef.current, title)
                }
              }}
              className="text-sm text-indigo-400 hover:text-indigo-300 transition-colors flex items-center gap-1.5"
            >
              ↓ Download PDF
            </button>
            <button
              onClick={handleReset}
              className="text-sm text-gray-500 hover:text-gray-300 transition-colors underline underline-offset-2"
            >
              Start new research
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
