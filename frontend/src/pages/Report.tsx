import { useState } from "react";
import ReactMarkdown from "react-markdown";

const API_BASE =
  (import.meta.env.VITE_API_URL || "http://localhost:8000")
    .toString()
    .replace(/\/$/, "");

export default function Report() {
  const [company, setCompany] = useState("");
  const [prospect, setProspect] = useState("");
  const [tone, setTone] = useState("concise, friendly, expert");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string>("");
  const [report, setReport] = useState<string>("");

  async function generate() {
    setErr(""); setReport(""); setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/report/precall`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ company, prospect, tone }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = (await res.json()) as { report_md: string };
      setReport(data.report_md);
    } catch (e: any) {
      setErr(e?.message || "Failed to generate report");
    } finally {
      setLoading(false);
    }
  }

  const disabled = company.trim().length < 20 || prospect.trim().length < 20 || loading;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-4">
      <h2 className="text-xl font-bold">Pre-Call Report</h2>

      <label className="text-sm font-medium">Company summary</label>
      <textarea
        className="w-full h-36 border rounded-md p-3 bg-white"
        placeholder="Paste company summary or notes…"
        value={company}
        onChange={(e) => setCompany(e.target.value)}
      />

      <label className="text-sm font-medium">Prospect insights</label>
      <textarea
        className="w-full h-36 border rounded-md p-3 bg-white"
        placeholder="Paste prospect insights (from PDF or notes)…"
        value={prospect}
        onChange={(e) => setProspect(e.target.value)}
      />

      <div className="flex items-center gap-3">
        <label className="text-sm text-gray-700">Tone</label>
        <input
          className="flex-1 border rounded-md p-2 bg-white"
          value={tone}
          onChange={(e) => setTone(e.target.value)}
          placeholder="e.g., concise, friendly, expert"
        />
        <button
          className="ml-auto px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md disabled:opacity-50"
          disabled={disabled}
          onClick={generate}
        >
          {loading ? "Generating…" : "Generate Report"}
        </button>
      </div>

      {err && <div className="text-sm text-red-600 whitespace-pre-wrap">{err}</div>}

      {report && (
        <div className="prose bg-white border rounded-md p-4">
          <ReactMarkdown>{report}</ReactMarkdown>
        </div>
      )}
    </div>
  );
}
