import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";

// --- API base: use env if provided, otherwise localhost:8000
const API_BASE =
  (import.meta.env.VITE_API_URL || "http://localhost:8000")
    .toString()
    .replace(/\/$/, "");

// Common prompt prefix to steer LLM
const PREFIX = `Extract prospect insights in concise bullets:
- Role & seniority
- Interests / recent focus
- Possible pains
- 1–2 personalized hooks for outreach
Return 5–7 bullet points.
----
`;

// --- Upload helper (use fetch + FormData, DO NOT set Content-Type manually)
async function uploadPdf(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API_BASE}/api/prospect/upload`, {
    method: "POST",
    body: form,
    credentials: "include",
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Upload failed with status ${res.status}`);
  }

  const data = (await res.json()) as { summary: string };
  return data.summary;
}

// --- Summarize pasted text via backend
async function summarizeText(text: string, bullets: number): Promise<string> {
  const res = await fetch(`${API_BASE}/api/summarize`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: PREFIX + text, bullets }),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `Summarize failed with status ${res.status}`);
  }

  const data = (await res.json()) as { summary: string };
  return data.summary;
}

export default function Prospect() {
  const [text, setText] = useState("");
  const [bullets, setBullets] = useState(6);

  const [pdfSummary, setPdfSummary] = useState<string>("");
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string>("");

  // React Query mutation for pasted text flow
  const textMutation = useMutation({
    mutationFn: async () => summarizeText(text, bullets),
  });

  const looksLikeLinkedIn = /^https?:\/\/(www\.)?linkedin\.com/i.test(text);
  const tooShort = text.trim().length < 80;

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-6">
      <h2 className="text-xl font-bold">Prospect Researcher</h2>

      {/* --- PDF Upload (LinkedIn export) --- */}
      <section className="space-y-2">
        <label className="text-sm font-medium">Upload LinkedIn profile PDF (optional)</label>
        <input
          type="file"
          accept="application/pdf"
          className="block text-sm"
          onChange={async (e) => {
            const f = e.target.files?.[0];
            if (!f) return;
            setPdfError("");
            setPdfSummary("");
            setPdfLoading(true);
            try {
              const summary = await uploadPdf(f);
              setPdfSummary(summary);
            } catch (err: any) {
              setPdfError(err?.message || "Upload failed");
            } finally {
              setPdfLoading(false);
            }
          }}
        />
        <p className="text-xs text-gray-500">
          Tip: LinkedIn → Settings & Privacy → Data privacy → Get a copy of your data → Profile as PDF.
        </p>
        {pdfLoading && <div className="text-sm text-gray-600">Processing PDF…</div>}
        {pdfError && <div className="text-sm text-red-600">{pdfError}</div>}
      </section>

      {pdfSummary && (
        <section className="prose bg-white border rounded-md p-4">
          <h3 className="mt-0">Summary (from PDF)</h3>
          <ReactMarkdown>{pdfSummary}</ReactMarkdown>
        </section>
      )}

      {/* --- Pasted Text Flow --- */}
      <section className="space-y-3">
        <label className="text-sm font-medium">Paste profile text</label>
        <textarea
          className="w-full h-48 border rounded-md p-3 bg-white"
          placeholder="Paste About/Experience text or notes about the person…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        {looksLikeLinkedIn && (
          <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-md p-2">
            LinkedIn URLs can’t be fetched directly. Please paste the profile text or upload the PDF export.
          </div>
        )}

        <div className="flex items-center gap-3">
          <label className="text-sm text-gray-700">Bullets</label>
          <input
            type="number"
            min={3}
            max={12}
            className="w-24 border rounded-md p-2 bg-white"
            value={bullets}
            onChange={(e) => setBullets(parseInt(e.target.value || "6"))}
          />

          <button
            className="ml-auto px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md transition disabled:opacity-50"
            disabled={tooShort || textMutation.isPending || !text}
            onClick={() => textMutation.mutate()}
          >
            {textMutation.isPending ? "Summarizing…" : "Summarize"}
          </button>
        </div>

        {tooShort && (
          <div className="text-xs text-amber-700">
            Add more profile content for a useful summary (at least a few sentences).
          </div>
        )}
      </section>

      {textMutation.data && (
        <section className="prose bg-white border rounded-md p-4">
          <h3 className="mt-0">Summary (from pasted text)</h3>
          <ReactMarkdown>{textMutation.data}</ReactMarkdown>
        </section>
      )}

      {textMutation.error && (
        <div className="text-sm text-red-600">
          {(textMutation.error as Error).message}
        </div>
      )}
    </div>
  );
}
