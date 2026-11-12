import { useState, type ReactNode } from 'react'
import type { EmailResult, Outcome, UrlResult, UrlThresholds } from '../api'
import { UNAVAILABLE, URL_VERDICTS, emailVerdict, type Tone, type Verdict } from '../verdicts'

// Written here on purpose: the model's own `note` claims "Calibrated" and ends with a word R2 keeps off the page.
const EMAIL_DISCLAIMER = 'Advisory only. A low phishing score is not a safety guarantee.'
const NO_RULE_MATCHED = 'No strong URL-pattern indicators found'
const CHARACTER_PATTERNS = "The model's score comes from character patterns in this address, which have no plain-language explanation."

export const TONE_TEXT: Record<Tone, string> = {
  danger: 'text-danger',
  warning: 'text-warning',
  'warning-muted': 'text-warning-muted',
  neutral: 'text-neutral',
  unavailable: 'text-unavailable',
}

const TONE_BG: Record<Tone, string> = {
  danger: 'bg-danger',
  warning: 'bg-warning',
  'warning-muted': 'bg-warning-muted',
  neutral: 'bg-neutral',
  unavailable: 'bg-unavailable',
}

export const TONE_ICON: Record<Tone, ReactNode> = {
  danger: <path d="M8.3 2h7.4L22 8.3v7.4L15.7 22H8.3L2 15.7V8.3zM12 7v6m0 3.5v.5" />,
  warning: <path d="M12 3 22 20H2zM12 10v5m0 2.5v.5" />,
  'warning-muted': <path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .8-1 1.7m0 3v.5" />,
  neutral: <path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zM8 12h8" />,
  unavailable: <path d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zM5.6 5.6l12.8 12.8" />,
}

export function Headline({ verdict }: { verdict: Verdict }) {
  return (
    <div className={`flex items-start gap-3 ${TONE_TEXT[verdict.tone]}`}>
      <svg viewBox="0 0 24 24" aria-hidden="true" className="mt-0.5 size-8 shrink-0 fill-none stroke-current stroke-2">
        {TONE_ICON[verdict.tone]}
      </svg>
      <div>
        <h2 className="font-display text-2xl leading-tight sm:text-3xl">{verdict.badge}</h2>
        {verdict.subtext && <p className="mt-1 text-ink">{verdict.subtext}</p>}
      </div>
    </div>
  )
}

export function Sheet({ children, tone }: { children: ReactNode; tone: Tone }) {
  return (
    <article className="reveal border border-rule bg-sheet">
      <div aria-hidden="true" className={`h-1.5 ${TONE_BG[tone]}`} />
      <div className="space-y-6 p-5 sm:p-7">{children}</div>
    </article>
  )
}

function Footer({ version, text }: { version?: string; text?: string }) {
  return (
    <footer className="border-t border-rule pt-4 text-sm text-ink-soft">
      {version && <p className="font-mono text-xs">{version}</p>}
      {text && <p className="mt-1">{text}</p>}
    </footer>
  )
}

export function Label({ children }: { children: ReactNode }) {
  return <h3 className="mb-2 font-mono text-xs tracking-widest text-ink-soft uppercase">{children}</h3>
}

function Bar({ label, percent, unit, tone, marks = [] }: { label: string; percent: number; unit: string; tone: Tone; marks?: number[] }) {
  return (
    <div>
      <div className="flex justify-between font-mono text-sm">
        <span>{label}</span>
        <span>
          {percent.toFixed(1)}
          {unit}
        </span>
      </div>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        className="relative mt-1 h-3 border border-rule bg-paper"
      >
        <div className={`fill h-full ${TONE_BG[tone]}`} style={{ width: `${percent}%` }} />
        {marks.map((mark) => (
          <div key={mark} data-testid="band-mark" className="absolute -inset-y-1 w-0.5 bg-ink ring-1 ring-sheet" style={{ left: `${mark}%` }} />
        ))}
      </div>
    </div>
  )
}

function DefangedUrl({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  async function copy() {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }
  return (
    <div>
      <Label>Checked as text, not opened</Label>
      <div className="quarantine flex flex-wrap items-center justify-between gap-3 bg-paper p-3">
        <code className="min-w-0 font-mono text-sm break-all">{text}</code>
        <button type="button" onClick={copy} className="shrink-0 border border-ink px-3 py-1 text-sm font-semibold hover:bg-ink hover:text-on-ink">
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  )
}

/** The service's evidence rules skip the character-pattern scores, so a flagged URL can match
 * no rule. "No strong indicators" beside a warning badge reads as a contradiction. */
export function explainEvidence(result: UrlResult, limit?: number): string[] {
  return result.evidence
    .slice(0, limit)
    .map((item) => (item === NO_RULE_MATCHED && result.band !== 'Low' ? CHARACTER_PATTERNS : item))
}

export function UrlCard({ result, thresholds }: { result: UrlResult; thresholds: UrlThresholds | null }) {
  const verdict = URL_VERDICTS[result.band]
  const evidence = explainEvidence(result, result.band === 'High' ? 3 : undefined)
  return (
    <Sheet tone={verdict.tone}>
      <Headline verdict={verdict} />
      <div>
        <Bar
          label="Risk score"
          percent={result.score}
          unit=" / 100"
          tone={verdict.tone}
          marks={thresholds ? [thresholds.thr_medium, thresholds.thr_high] : []}
        />
        {thresholds && (
          <p className="mt-2 font-mono text-xs text-ink-soft">
            Marks: Suspicious from {thresholds.thr_medium.toFixed(1)}, High from {thresholds.thr_high.toFixed(1)}
          </p>
        )}
      </div>
      <div>
        <Label>What to do</Label>
        <p className="font-semibold">{verdict.action}</p>
      </div>
      <div>
        <Label>Why?</Label>
        {evidence.length > 0 ? (
          <ul className="list-disc space-y-1 pl-5">
            {evidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p>{result.note}</p>
        )}
      </div>
      <DefangedUrl text={result.url_defanged} />
      <Footer version={result.model} text={result.disclaimer} />
    </Sheet>
  )
}

export function EmailCard({ result }: { result: EmailResult }) {
  const verdict = emailVerdict(result)
  const rows = [
    { label: 'LEGITIMATE', tone: 'neutral' },
    { label: 'SPAM', tone: 'warning' },
    { label: 'PHISHING', tone: 'danger' },
  ] as const
  const top = rows.reduce((a, b) => (result.probabilities[b.label] > result.probabilities[a.label] ? b : a))
  return (
    <Sheet tone={verdict.tone}>
      <Headline verdict={verdict} />
      <div className="space-y-3">
        {rows.map(({ label, tone }) => (
          <Bar key={label} label={label} percent={result.probabilities[label] * 100} unit="%" tone={tone} />
        ))}
      </div>
      <div>
        <Label>Why?</Label>
        <p>
          The model gave its highest probability to {top.label}, at {(result.probabilities[top.label] * 100).toFixed(1)}%.
        </p>
        {result.truncated && <p className="mt-2">Long email: only the start and end were analysed.</p>}
      </div>
      <Footer version={result.model_version} text={EMAIL_DISCLAIMER} />
    </Sheet>
  )
}

/** The shared result region: skeleton, unavailable card, inline error, toast, or the result. */
export function ResultRegion<T>({ outcome, pending, render }: { outcome: Outcome<T> | null; pending: boolean; render: (data: T) => ReactNode }) {
  return (
    <>
      <div aria-live="polite" className="mt-8 lg:sticky lg:top-6 lg:mt-0">
        {!pending && (!outcome || outcome.kind === 'invalid' || outcome.kind === 'rate_limited') && (
          <div aria-hidden="true" className="hidden min-h-96 items-center justify-center border border-dashed border-rule p-8 font-mono text-sm text-ink-soft lg:flex">
            Result appears here
          </div>
        )}
        {pending && (
          <div className="border border-rule bg-sheet p-7" aria-label="Checking">
            <div className="pulse h-8 w-2/3 bg-rule" />
            <div className="pulse mt-6 h-3 w-full bg-rule" />
            <div className="pulse mt-3 h-3 w-5/6 bg-rule" />
          </div>
        )}
        {outcome?.kind === 'ok' && render(outcome.data)}
        {outcome?.kind === 'unavailable' && (
          <Sheet tone="unavailable">
            <Headline verdict={UNAVAILABLE} />
          </Sheet>
        )}
      </div>
      {outcome?.kind === 'rate_limited' && (
        <div role="status" className="reveal fixed right-4 bottom-4 left-4 z-10 bg-ink p-4 text-on-ink sm:left-auto">
          Too many checks — wait a minute
        </div>
      )}
    </>
  )
}
