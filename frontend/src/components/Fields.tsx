import type { ReactNode } from 'react'

export const INPUT = 'w-full border border-ink bg-sheet p-3 font-mono text-sm placeholder:text-ink-soft'
/** Laptop layout for both check pages: form on the left, result beside it. Stacks below lg. */
export const PANES = 'lg:grid lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:items-start lg:gap-14'

export function SectionHead({ mark, title, children }: { mark: string; title: string; children: ReactNode }) {
  return (
    <header className="mb-6">
      <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">Section {mark}</p>
      <h1 className="mt-1 font-display text-4xl sm:text-5xl lg:text-4xl">{title}</h1>
      <p className="mt-3 max-w-prose text-ink-soft">{children}</p>
    </header>
  )
}

export function Examples<T>({ items, label, onPick }: { items: T[]; label: (item: T) => string; onPick: (item: T) => void }) {
  return (
    <div>
      <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">Try an example</p>
      <div className="mt-2 flex flex-wrap gap-2">
        {items.map((item) => (
          <button
            key={label(item)}
            type="button"
            onClick={() => onPick(item)}
            className="max-w-full border border-rule bg-sheet px-2.5 py-1 text-left font-mono text-xs break-all hover:border-ink"
          >
            {label(item)}
          </button>
        ))}
      </div>
    </div>
  )
}

export function Submit({ pending, disabled }: { pending: boolean; disabled?: boolean }) {
  return (
    <button
      type="submit"
      disabled={pending || disabled}
      className="bg-ink px-6 py-3 font-semibold text-on-ink hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-50"
    >
      {pending ? 'Checking…' : 'Check'}
    </button>
  )
}

export function FieldError({ id, message }: { id: string; message?: string }) {
  if (!message) return null
  return (
    <p id={id} role="alert" className="mt-2 text-sm font-semibold text-danger">
      {message}
    </p>
  )
}
