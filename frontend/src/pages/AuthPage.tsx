import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { login, signup, type User } from '../api'
import { FieldError, INPUT } from '../components/Fields'

export default function AuthPage({ mode, onAuth }: { mode: 'login' | 'signup'; onAuth: (user: User) => void }) {
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string>()
  const [pending, setPending] = useState(false)
  const signingUp = mode === 'signup'

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(undefined)
    const outcome = signingUp ? await signup(name, email, password) : await login(email, password)
    setPending(false)
    if (outcome.kind === 'ok') {
      onAuth(outcome.user)
      navigate('/')
    } else {
      setError(outcome.message)
    }
  }

  return (
    <div className="mx-auto max-w-md">
      <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">Account</p>
      <h1 className="mt-1 font-display text-4xl">{signingUp ? 'Create an account' : 'Log in'}</h1>
      <form onSubmit={submit} noValidate className="mt-8 space-y-5 border border-rule bg-sheet p-6 sm:p-8">
        {signingUp && (
          <div>
            <label htmlFor="name" className="mb-2 block font-semibold">
              Name
            </label>
            <input id="name" value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={80} className={INPUT} />
          </div>
        )}
        <div>
          <label htmlFor="email" className="mb-2 block font-semibold">
            Email
          </label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoComplete="email"
            maxLength={254}
            className={INPUT}
          />
        </div>
        <div>
          <label htmlFor="password" className="mb-2 block font-semibold">
            Password {signingUp && <span className="font-normal text-ink-soft">(at least 8 characters)</span>}
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={signingUp ? 'new-password' : 'current-password'}
            maxLength={128}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'auth-error' : undefined}
            className={INPUT}
          />
          <FieldError id="auth-error" message={error} />
        </div>
        <button
          type="submit"
          disabled={pending || !email.trim() || !password || (signingUp && !name.trim())}
          className="w-full bg-ink px-6 py-3 font-semibold text-on-ink hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? 'Please wait…' : signingUp ? 'Create account' : 'Log in'}
        </button>
      </form>
      <p className="mt-5 text-sm text-ink-soft">
        {signingUp ? 'Already have an account? ' : 'New here? '}
        <Link to={signingUp ? '/login' : '/signup'} className="font-semibold text-ink underline">
          {signingUp ? 'Log in' : 'Create an account'}
        </Link>
      </p>
    </div>
  )
}
