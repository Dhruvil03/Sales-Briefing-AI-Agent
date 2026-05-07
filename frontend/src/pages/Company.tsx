import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import axios from "axios";

const api = axios.create({
  baseURL: (import.meta.env.VITE_API_URL || "http://localhost:8000").replace(/\/$/, "") + "/api",
});

export default function Company() {
  const [url, setUrl] = useState("");
  const [bullets, setBullets] = useState(6);

  const m = useMutation({
    mutationFn: async () => {
      const r = await api.post("/company/summary", { url, bullets });
      return r.data.summary as string;
    },
  });

  return (
    <div className="max-w-2xl mx-auto p-6 space-y-4">
      <h2 className="text-xl font-bold">Company Researcher</h2>
      <div className="flex gap-2">
        <input className="flex-1 border rounded-md p-2 bg-white"
               placeholder="https://company.com"
               value={url} onChange={e=>setUrl(e.target.value)} />
        <input type="number" min={3} max={12}
               className="w-24 border rounded-md p-2 bg-white"
               value={bullets} onChange={e=>setBullets(parseInt(e.target.value||"6"))} />
        <button className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md disabled:opacity-50"
                disabled={!url || m.isPending}
                onClick={()=>m.mutate()}>
          {m.isPending ? "Analyzing…" : "Analyze"}
        </button>
      </div>

      {m.data && (
        <div className="prose bg-white border rounded-md p-4">
          <ReactMarkdown>{m.data}</ReactMarkdown>
        </div>
      )}
      {m.error && <div className="text-sm text-red-600">{(m.error as Error).message}</div>}
    </div>
  );
}
