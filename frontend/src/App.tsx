import { Routes, Route, Link, useNavigate, Navigate } from "react-router-dom"
import Home           from "./pages/Home"
import Research        from "./pages/Research"
import Session         from "./pages/Session"
import BatchResearch   from "./pages/BatchResearch"
import ICPSettings     from "./pages/ICPSettings"
import Company         from "./pages/Company"
import Prospect        from "./pages/Prospect"
import Report          from "./pages/Report"
import Summarizer      from "./features/summarize"
import Login           from "./pages/Login"
import Signup          from "./pages/Signup"
import Sidebar         from "./components/Sidebar"
import { AuthProvider, useAuth } from "./context/AuthContext"

// ── User menu (top-right) ─────────────────────────────────────────────────────

function UserMenu() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  if (!user) {
    return (
      <div className="flex items-center gap-3">
        <Link to="/login"  className="text-sm text-gray-400 hover:text-gray-200 transition-colors">Sign in</Link>
        <Link to="/signup" className="text-sm px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition-colors">
          Sign up
        </Link>
      </div>
    )
  }

  const initials = user.full_name
    ? user.full_name.split(" ").map(w => w[0]).join("").slice(0, 2).toUpperCase()
    : user.email.slice(0, 2).toUpperCase()

  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-500 hidden sm:block">{user.email}</span>
      <button
        onClick={() => { logout(); navigate("/") }}
        className="flex items-center gap-2 text-sm text-gray-400 hover:text-gray-200 transition-colors"
        title="Sign out"
      >
        <span className="w-7 h-7 rounded-full bg-indigo-700 flex items-center justify-center text-xs font-bold text-white">
          {initials}
        </span>
        <span className="text-xs hidden sm:block">Sign out</span>
      </button>
    </div>
  )
}

// ── Protected route ───────────────────────────────────────────────────────────

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (!user) return <Navigate to="/login" replace />
  return <>{children}</>
}

// ── App shell ─────────────────────────────────────────────────────────────────

function AppShell() {
  const { user } = useAuth()

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#0c0c0c]">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="shrink-0 z-20 bg-[#111111] border-b border-white/[0.07]">
        <div className="px-4 py-3 flex items-center justify-between">
          {/* Logo — only show when no sidebar (unauthenticated) */}
          {!user && (
            <Link to="/" className="text-base font-bold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-violet-400">
              Sales Copilot
            </Link>
          )}
          {/* Spacer when sidebar is shown */}
          {user && <div />}
          <UserMenu />
        </div>
      </header>

      {/* ── Content area ──────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Sidebar — only for authenticated users */}
        {user && <Sidebar />}

        {/* Main content */}
        <main className="flex-1 overflow-y-auto">
          <Routes>
            <Route path="/"           element={<Home />} />
            <Route path="/login"      element={<Login />} />
            <Route path="/signup"     element={<Signup />} />
            <Route path="/research"    element={<ProtectedRoute><Research /></ProtectedRoute>} />
            <Route path="/session/:id" element={<ProtectedRoute><Session /></ProtectedRoute>} />
            <Route path="/batch"       element={<ProtectedRoute><BatchResearch /></ProtectedRoute>} />
            <Route path="/icp"         element={<ProtectedRoute><ICPSettings /></ProtectedRoute>} />
            {/* /history redirects to /research — sidebar replaces the list view */}
            <Route path="/history"     element={<Navigate to="/research" replace />} />
            {/* Legacy routes */}
            <Route path="/summarize"  element={<Summarizer />} />
            <Route path="/company"    element={<Company />} />
            <Route path="/prospect"   element={<Prospect />} />
            <Route path="/report"     element={<Report />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  )
}
