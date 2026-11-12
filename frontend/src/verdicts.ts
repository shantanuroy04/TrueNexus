import type { EmailResult, Overall, UrlBand } from './api'

export type Tone = 'danger' | 'warning' | 'warning-muted' | 'neutral' | 'unavailable'
export type Verdict = { badge: string; tone: Tone; subtext?: string; action?: string }

export const URL_VERDICTS: Record<UrlBand, Verdict> = {
  High: {
    badge: 'High phishing risk',
    tone: 'danger',
    action: 'Do not open this link or enter any details on it.',
  },
  Medium: {
    badge: 'Suspicious link',
    tone: 'warning',
    action: "Do not open it yet. Go to the organisation's website yourself to check the message.",
  },
  Low: {
    badge: 'No warning signs found in this URL',
    tone: 'neutral',
    subtext: 'Not a safety guarantee. The link was not opened.',
    action: 'Still check who sent it before entering any details.',
  },
}

export function emailVerdict(result: EmailResult): Verdict {
  switch (result.verdict) {
    case 'PHISHING':
      return { badge: 'Likely phishing', tone: 'danger' }
    case 'SPAM':
      return { badge: 'Likely spam', tone: 'warning' }
    case 'LEGITIMATE':
      return { badge: 'No phishing or spam pattern found', tone: 'neutral', subtext: 'Advisory only. Still check the sender.' }
    case 'UNCERTAIN':
      return { badge: 'Model is unsure', tone: 'warning-muted', subtext: `Leaning: ${result.prediction}. Verify manually.` }
  }
}

/** Banner for the combined email + links result. Worst signal wins (decided by the backend). */
export const OVERALL: Record<Overall, Verdict> = {
  HIGH: { badge: 'High risk', tone: 'danger', action: 'Do not click any link or reply. Report it to whoever runs your email.' },
  MEDIUM: { badge: 'Caution', tone: 'warning', action: 'Do not click links until you have checked the sender another way.' },
  UNCERTAIN: { badge: 'Unclear result', tone: 'warning-muted', action: 'The model is unsure. Verify the message manually.' },
  UNAVAILABLE: {
    badge: 'Analysis incomplete',
    tone: 'unavailable',
    action: 'Part of the analysis could not run, so this is not a clean result.',
  },
  LOW: { badge: 'No warning signs found', tone: 'neutral', action: 'Not a safety guarantee. Still check who sent it.' },
}

/** Short labels for the links table. */
export const LINK_BAND: Record<UrlBand | 'UNAVAILABLE', Verdict> = {
  High: { badge: 'High risk', tone: 'danger' },
  Medium: { badge: 'Suspicious', tone: 'warning' },
  Low: { badge: 'No warning', tone: 'neutral' },
  UNAVAILABLE: { badge: 'Not checked', tone: 'unavailable' },
}

export const UNAVAILABLE: Verdict = {
  badge: 'Analysis unavailable',
  tone: 'unavailable',
  subtext: 'Model not loaded. Nothing was concluded about this input.',
}
