import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { deleteAccount, type User } from '../api'
import { FieldError, INPUT } from '../components/Fields'

export default function AccountPage({ user, onDeleted }: { user: User | null; onDeleted: () => void }) {
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirmed, setConfirmed] = useState(false)
  const [error, setError] = useState<string>()
  const [pending, setPending] = useState(false)

  if (!user) {
    return (
      <div className="mx-auto max-w-md">
        <h1 className="font-display text-4xl">Your account</h1>
        <p className="mt-4">
          <Link to="/login" className="font-semibold underline">
            Log in
          </Link>{' '}
          to manage your account.
        </p>
      </div>
    )
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    setPending(true)
    setError(undefined)
    const problem = await deleteAccount(password)
    setPending(false)
    if (problem) {
      setError(problem)
    } else {
      onDeleted()
      navigate('/')
    }
  }

  return (
    <div className="mx-auto max-w-md space-y-8">
      <header>
        <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">Account</p>
        <h1 className="mt-1 font-display text-4xl">Your account</h1>
        <dl className="mt-5 space-y-1">
          <div>
            <dt className="inline text-ink-soft">Name: </dt>
            <dd className="inline font-semibold">{user.name}</dd>
          </div>
          <div>
            <dt className="inline text-ink-soft">Email: </dt>
            <dd className="inline font-semibold">{user.email}</dd>
          </div>
        </dl>
      </header>
      <form onSubmit={submit} noValidate className="space-y-4 border border-danger p-6">
        <h2 className="font-display text-2xl text-danger">Delete account</h2>
        <p>This removes your name, email and password hash. It cannot be undone.</p>
        <div>
          <label htmlFor="delete-password" className="mb-2 block font-semibold">
            Confirm with your password
          </label>
          <input
            id="delete-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            maxLength={128}
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'delete-error' : undefined}
            className={INPUT}
          />
          <FieldError id="delete-error" message={error} />
        </div>
        <label className="flex items-start gap-2">
          <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} className="mt-1" />
          <span>I understand this cannot be undone.</span>
        </label>
        <button
          type="submit"
          disabled={pending || !password || !confirmed}
          className="w-full bg-danger px-6 py-3 font-semibold text-sheet hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {pending ? 'Deleting…' : 'Delete my account'}
        </button>
      </form>
    </div>
  )
}
