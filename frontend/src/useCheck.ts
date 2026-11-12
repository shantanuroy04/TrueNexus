import { useEffect, useRef, useState } from 'react'
import type { Outcome } from './api'

/** One check at a time: a new submission or leaving the page cancels the one in flight. */
export function useCheck<T>() {
  const [outcome, setOutcome] = useState<Outcome<T> | null>(null)
  const [pending, setPending] = useState(false)
  const active = useRef<AbortController | null>(null)

  useEffect(() => () => active.current?.abort(), [])

  async function run(request: (signal: AbortSignal) => Promise<Outcome<T>>) {
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    setPending(true)
    setOutcome(null)
    try {
      const next = await request(controller.signal)
      if (active.current === controller) {
        setOutcome(next)
        setPending(false)
      }
    } catch {
      // Aborted: the request that replaced this one owns the state now.
    }
  }

  return { outcome, pending, run }
}
