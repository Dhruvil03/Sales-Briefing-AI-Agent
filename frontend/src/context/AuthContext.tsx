// frontend/src/context/AuthContext.tsx
import { createContext, useCallback, useContext, useEffect, useState } from "react"

const API_BASE = (import.meta.env.VITE_API_URL || "http://localhost:8000")
  .toString().replace(/\/$/, "")

interface AuthUser {
  user_id:   number
  email:     string
  full_name: string | null
  token:     string
}

interface AuthContextValue {
  user:    AuthUser | null
  loading: boolean
  login:   (email: string, password: string) => Promise<void>
  signup:  (email: string, password: string, fullName?: string) => Promise<void>
  logout:  () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user,    setUser]    = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)

  // Rehydrate from localStorage on mount
  useEffect(() => {
    try {
      const raw = localStorage.getItem("sc_auth")
      if (raw) setUser(JSON.parse(raw))
    } catch { /* ignore */ }
    setLoading(false)
  }, [])

  const persist = (u: AuthUser | null) => {
    setUser(u)
    if (u) localStorage.setItem("sc_auth", JSON.stringify(u))
    else    localStorage.removeItem("sc_auth")
  }

  const login = useCallback(async (email: string, password: string) => {
    const r = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    })
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: "Login failed" }))
      throw new Error(err.detail ?? "Login failed")
    }
    const data = await r.json()
    persist({ user_id: data.user_id, email: data.email, full_name: data.full_name, token: data.access_token })
  }, [])

  const signup = useCallback(async (email: string, password: string, fullName?: string) => {
    const r = await fetch(`${API_BASE}/api/auth/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, full_name: fullName || null }),
    })
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: "Signup failed" }))
      throw new Error(err.detail ?? "Signup failed")
    }
    const data = await r.json()
    persist({ user_id: data.user_id, email: data.email, full_name: data.full_name, token: data.access_token })
  }, [])

  const logout = useCallback(() => persist(null), [])

  return (
    <AuthContext.Provider value={{ user, loading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider")
  return ctx
}
