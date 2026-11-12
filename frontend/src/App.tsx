import { useEffect, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { getHealth, getMe, logout, type Health, type User } from './api'
import About from './pages/About'
import AccountPage from './pages/AccountPage'
import AuthPage from './pages/AuthPage'
import EmailPage from './pages/EmailPage'
import Home from './pages/Home'
import HowItWorks from './pages/HowItWorks'
import UrlPage from './pages/UrlPage'

function ThemeToggle() {
  function toggle() {
    const root = document.documentElement
    const current = root.dataset.theme ?? (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    root.dataset.theme = current === 'dark' ? 'light' : 'dark'
  }
  return (
    <button type="button" onClick={toggle} className="border border-rule px-2.5 py-1 font-mono text-xs hover:border-ink">
      Theme
    </button>
  )
}

const navClass = ({ isActive }: { isActive: boolean }) =>
  `border-b-2 py-1 font-semibold ${isActive ? 'border-ink' : 'border-transparent hover:border-rule'}`

export default function App() {
  const [health, setHealth] = useState<Health | null | undefined>(undefined)
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then((h) => {
      if (!controller.signal.aborted) setHealth(h)
    })
    getMe(controller.signal).then((u) => {
      if (!controller.signal.aborted) setUser(u)
    })
    return () => controller.abort()
  }, [])

  async function signOut() {
    await logout()
    setUser(null)
  }

  return (
    <div className="mx-auto flex min-h-dvh max-w-[90rem] flex-col px-4 sm:px-6 lg:px-10">
      <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-ink py-4">
        <NavLink to="/" className="font-display text-2xl">
          TrueNexus
        </NavLink>
        <nav aria-label="Sections" className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <NavLink to="/url" className={navClass}>
            URL
          </NavLink>
          <NavLink to="/email" className={navClass}>
            Email
          </NavLink>
          <NavLink to="/how-it-works" className={navClass}>
            How it works
          </NavLink>
          <NavLink to="/about" className={navClass}>
            About
          </NavLink>
          {user ? (
            <>
              <NavLink to="/account" className="text-sm text-ink-soft hover:underline">
                Signed in as <span className="font-semibold text-ink">{user.name}</span>
              </NavLink>
              <button type="button" onClick={signOut} className="font-semibold hover:underline">
                Log out
              </button>
            </>
          ) : (
            <>
              <NavLink to="/login" className={navClass}>
                Log in
              </NavLink>
              <NavLink to="/signup" className="bg-ink px-3 py-1 font-semibold text-on-ink hover:opacity-85">
                Sign up
              </NavLink>
            </>
          )}
          <ThemeToggle />
        </nav>
      </header>
      <main className="flex-1 py-8 lg:py-10">
        <Routes>
          <Route path="/" element={<Home health={health} />} />
          <Route path="/url" element={<UrlPage />} />
          <Route path="/email" element={<EmailPage />} />
          <Route path="/login" element={<AuthPage mode="login" onAuth={setUser} />} />
          <Route path="/signup" element={<AuthPage mode="signup" onAuth={setUser} />} />
          <Route path="/how-it-works" element={<HowItWorks />} />
          <Route path="/about" element={<About />} />
          <Route path="/account" element={<AccountPage user={user} onDeleted={() => setUser(null)} />} />
        </Routes>
      </main>
      <footer className="border-t border-rule py-4 text-xs text-ink-soft">
        Final-year B.Tech project, KIIT University. Results are advisory.
      </footer>
    </div>
  )
}
