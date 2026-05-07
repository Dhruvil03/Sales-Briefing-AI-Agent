import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import api from "../lib/api";
import ReactMarkdown from "react-markdown";

export default function Summarizer() {
  const [text, setText] = useState("");
  const mutation = useMutation({
    mutationFn: async () => {
      const res = await api.post("/summarize", { text, bullets: 5 });
      return res.data.summary as string;
    },
  });

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div className="text-center space-y-3">
        <h1 className="text-3xl font-bold gradient-text">Text Summarizer</h1>
        <p className="text-gray-600">
          Paste any text to get a concise, bullet-point summary
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">Input Text</label>
            <span className="text-xs text-gray-500">
              {text.length} characters
            </span>
          </div>
          <textarea
            className="w-full h-[400px] rounded-lg border border-gray-200 p-4 
                     shadow-sm focus:border-indigo-500 focus:ring-2 
                     focus:ring-indigo-200 transition resize-none"
            placeholder="Paste your text here..."
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <button
            className={`w-full py-3 px-4 rounded-lg font-medium transition
                     ${!text || mutation.isPending
                ? "bg-gray-100 text-gray-400 cursor-not-allowed"
                : "bg-indigo-600 text-white hover:bg-indigo-700"
              }`}
            disabled={!text || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? (
              <span className="flex items-center justify-center gap-2">
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                  />
                </svg>
                Summarizing...
              </span>
            ) : (
              "Summarize Text"
            )}
          </button>
        </div>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-gray-700">Summary</label>
            {mutation.data && (
              <button 
                className="text-xs text-indigo-600 hover:text-indigo-800"
                onClick={() => navigator.clipboard.writeText(mutation.data)}
              >
                Copy to clipboard
              </button>
            )}
          </div>
          <div className={`h-[400px] rounded-lg border border-gray-200 p-4 
                        bg-gray-50 overflow-y-auto ${
                          mutation.data ? "bg-white" : ""
                        }`}>
            {mutation.data ? (
              <div className="prose prose-sm max-w-none">
                <ReactMarkdown>{mutation.data}</ReactMarkdown>
              </div>
            ) : (
              <div className="h-full flex items-center justify-center text-gray-400 text-sm">
                Summary will appear here
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}