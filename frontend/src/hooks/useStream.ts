// frontend/src/hooks/useStream.ts
/**
 * React hook for consuming Server-Sent Events from FastAPI streaming endpoints.
 *
 * Uses fetch() + ReadableStream (not EventSource) so we can POST JSON bodies.
 *
 * SSE protocol (matches backend/app/services/sse.py):
 *   {"type":"status","data":"message"}   progress message
 *   {"type":"meta",  "data":{...}}       metadata — sent before first token
 *   {"type":"token", "data":"text"}      LLM output token
 *   {"type":"done"}                      stream finished
 *   {"type":"error", "data":"message"}   terminal error
 *
 * start() returns { content, meta } so callers can read session_id etc.
 * immediately after the stream without relying on React state batching.
 */

import { useCallback, useRef, useState } from "react"

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000")
  .toString()
  .replace(/\/$/, "")

interface SSEEvent {
  type: "status" | "meta" | "token" | "done" | "error"
  data?: unknown
}

export interface StreamResult<TMeta> {
  content: string
  meta: TMeta | null
}

export interface StreamState<TMeta = Record<string, unknown>> {
  content:     string
  status:      string
  meta:        TMeta | null
  isStreaming: boolean
  error:       string | null
  start:  (body: unknown) => Promise<StreamResult<TMeta>>
  reset:  () => void
  abort:  () => void
}

export function useStream<TMeta = Record<string, unknown>>(
  path: string
): StreamState<TMeta> {
  const [content,     setContent]     = useState("")
  const [status,      setStatus]      = useState("")
  const [meta,        setMeta]        = useState<TMeta | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [error,       setError]       = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const reset = useCallback(() => {
    setContent(""); setStatus(""); setMeta(null)
    setIsStreaming(false); setError(null)
  }, [])

  const abort = useCallback(() => {
    abortRef.current?.abort()
    setIsStreaming(false)
  }, [])

  const start = useCallback(
    async (body: unknown): Promise<StreamResult<TMeta>> => {
      reset()
      setIsStreaming(true)

      const controller = new AbortController()
      abortRef.current = controller

      let accumulated  = ""
      let capturedMeta: TMeta | null = null

      try {
        // Attach JWT if present
        const stored = localStorage.getItem("sc_auth")
        const token  = stored ? (JSON.parse(stored) as { token?: string }).token : null
        const headers: Record<string, string> = { "Content-Type": "application/json" }
        if (token) headers["Authorization"] = `Bearer ${token}`

        const res = await fetch(`${API_BASE}${path}`, {
          method:  "POST",
          headers,
          body:    JSON.stringify(body),
          signal:  controller.signal,
        })

        if (!res.ok) {
          const text = await res.text().catch(() => `HTTP ${res.status}`)
          try   { throw new Error((JSON.parse(text) as {detail?:string}).detail ?? text) }
          catch { throw new Error(text) }
        }

        if (!res.body) throw new Error("No response body")

        const reader  = res.body.getReader()
        const decoder = new TextDecoder()
        let   buffer  = ""

        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const parts = buffer.split("\n\n")
          buffer = parts.pop() ?? ""

          for (const part of parts) {
            if (!part.startsWith("data: ")) continue
            const raw = part.slice(6).trim()
            if (!raw) continue

            let evt: SSEEvent
            try { evt = JSON.parse(raw) as SSEEvent }
            catch { continue }

            if (evt.type === "status") {
              setStatus(evt.data as string)
            } else if (evt.type === "meta") {
              capturedMeta = evt.data as TMeta
              setMeta(capturedMeta)
            } else if (evt.type === "token") {
              const tok = evt.data as string
              accumulated += tok
              setContent(prev => prev + tok)
            } else if (evt.type === "done") {
              setIsStreaming(false)
              return { content: accumulated, meta: capturedMeta }
            } else if (evt.type === "error") {
              throw new Error(evt.data as string)
            }
          }
        }
      } catch (err: unknown) {
        if (!(err instanceof Error && err.name === "AbortError")) {
          const msg = err instanceof Error ? err.message : String(err)
          setError(msg)
        }
      } finally {
        setIsStreaming(false)
      }

      return { content: accumulated, meta: capturedMeta }
    },
    [path, reset]
  )

  return { content, status, meta, isStreaming, error, start, reset, abort }
}
