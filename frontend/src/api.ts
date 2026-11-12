// Empty = same origin: Vite (dev) and nginx (Docker) forward /api to the backend.
const BASE = import.meta.env.VITE_API_BASE ?? ''

export type UrlBand = 'High' | 'Medium' | 'Low'
export type EmailVerdict = 'LEGITIMATE' | 'SPAM' | 'PHISHING' | 'UNCERTAIN'
const EMAIL_LABELS = ['LEGITIMATE', 'SPAM', 'PHISHING'] as const

export type UrlResult = {
  model: string
  band: UrlBand
  score: number
  evidence: string[]
  url_defanged: string
  note: string
  disclaimer: string
}

export type EmailResult = {
  prediction: string
  verdict: EmailVerdict
  confidence: number
  probabilities: Record<(typeof EMAIL_LABELS)[number], number>
  truncated: boolean
  model_version: string
}

export type Health = { status: string; url_model: boolean; email_model: boolean }

export type Outcome<T> =
  | { kind: 'ok'; data: T }
  | { kind: 'invalid'; message: string }
  | { kind: 'rate_limited' }
  | { kind: 'unavailable' }

type Json = Record<string, unknown>

const isUrlResult = (r: Json): boolean =>
  ['High', 'Medium', 'Low'].includes(r.band as string) &&
  typeof r.score === 'number' &&
  r.score >= 0 &&
  r.score <= 100 &&
  Array.isArray(r.evidence) &&
  r.evidence.every((e) => typeof e === 'string') &&
  typeof r.url_defanged === 'string' &&
  typeof r.disclaimer === 'string'

const isEmailResult = (r: Json): boolean =>
  ['LEGITIMATE', 'SPAM', 'PHISHING', 'UNCERTAIN'].includes(r.verdict as string) &&
  typeof r.prediction === 'string' &&
  typeof r.probabilities === 'object' &&
  r.probabilities !== null &&
  EMAIL_LABELS.every((label) => typeof (r.probabilities as Json)[label] === 'number')

const isObject = (r: unknown): r is Json => typeof r === 'object' && r !== null

export type UrlEntry = UrlResult | { url_defanged: string; band: 'UNAVAILABLE' }
export type EmailPart = EmailResult | { verdict: 'UNAVAILABLE' }
export type Overall = 'HIGH' | 'MEDIUM' | 'UNCERTAIN' | 'UNAVAILABLE' | 'LOW'
export type AnalyzeResult = {
  email: EmailPart
  urls: UrlEntry[]
  urls_found: number
  urls_checked: number
  urls_capped: boolean
  overall: Overall
  overall_reason: string
  parsed_subject?: string
}

const isAnalyzeResult = (r: Json): boolean =>
  ['HIGH', 'MEDIUM', 'UNCERTAIN', 'UNAVAILABLE', 'LOW'].includes(r.overall as string) &&
  typeof r.overall_reason === 'string' &&
  typeof r.urls_found === 'number' &&
  typeof r.urls_checked === 'number' &&
  typeof r.urls_capped === 'boolean' &&
  isObject(r.email) &&
  (r.email.verdict === 'UNAVAILABLE' || isEmailResult(r.email)) &&
  Array.isArray(r.urls) &&
  r.urls.every((u) => isObject(u) && ((u.band === 'UNAVAILABLE' && typeof u.url_defanged === 'string') || isUrlResult(u)))

type Payload = { body: BodyInit; contentType: string }
const json = (value: unknown): Payload => ({ body: JSON.stringify(value), contentType: 'application/json' })

/** Anything that is not a recognised result becomes unavailable, never a clean result (R3). */
async function post<T>(path: string, payload: Payload, isResult: (r: Json) => boolean, signal: AbortSignal): Promise<Outcome<T>> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': payload.contentType },
      body: payload.body,
      signal,
      referrerPolicy: 'no-referrer',
    })
    if (res.status === 429) return { kind: 'rate_limited' }
    const body = (await res.json()) as Json | null
    if (res.status === 422 || res.status === 413 || res.status === 415) {
      // The URL service sends detail as a string, the email handler as { message }.
      const detail = body?.detail
      const message = typeof detail === 'string' ? detail : (detail as Json | undefined)?.message
      return { kind: 'invalid', message: typeof message === 'string' ? message : 'That input could not be checked.' }
    }
    return res.ok && body && isResult(body) ? { kind: 'ok', data: body as T } : { kind: 'unavailable' }
  } catch (error) {
    if (signal.aborted) throw error
    return { kind: 'unavailable' }
  }
}

export const checkUrl = (url: string, signal: AbortSignal) =>
  post<UrlResult>('/api/check-url', json({ url }), isUrlResult, signal)

/** The email model on the text plus the URL model on every link in it. */
export const analyzeEmail = (subject: string, body: string, signal: AbortSignal) =>
  post<AnalyzeResult>('/api/analyze-email', json({ subject, body }), isAnalyzeResult, signal)

/** The raw .eml bytes; the server parses it and ignores attachments. */
export const analyzeEml = (file: Blob, signal: AbortSignal) =>
  post<AnalyzeResult>('/api/check-eml', { body: file, contentType: 'message/rfc822' }, isAnalyzeResult, signal)

export type User = { name: string; email: string }
export type AuthOutcome = { kind: 'ok'; user: User } | { kind: 'error'; message: string }

const isUser = (r: unknown): r is User =>
  typeof r === 'object' && r !== null && typeof (r as Json).name === 'string' && typeof (r as Json).email === 'string'

/** The session lives in an HttpOnly cookie, so these calls send credentials and never see the token. */
async function authPost(path: string, payload: unknown): Promise<AuthOutcome> {
  try {
    const res = await fetch(`${BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      credentials: 'include',
    })
    const body = (await res.json().catch(() => null)) as Json | null
    if (res.ok && isUser(body)) return { kind: 'ok', user: body }
    if (res.status === 429) return { kind: 'error', message: 'Too many attempts. Wait a minute and try again.' }
    if (res.status < 500 && typeof body?.detail === 'string') return { kind: 'error', message: body.detail }
  } catch {
    // network failure: fall through
  }
  return { kind: 'error', message: 'Accounts are unavailable right now. Try again later.' }
}

export const signup = (name: string, email: string, password: string) => authPost('/api/auth/signup', { name, email, password })
export const login = (email: string, password: string) => authPost('/api/auth/login', { email, password })

export async function logout(): Promise<void> {
  try {
    await fetch(`${BASE}/api/auth/logout`, { method: 'POST', credentials: 'include' })
  } catch {
    // the page forgets the user either way
  }
}

/** Null on success, otherwise a message for the form. */
export async function deleteAccount(password: string): Promise<string | null> {
  try {
    const res = await fetch(`${BASE}/api/auth/delete-account`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
      credentials: 'include',
    })
    if (res.status === 204) return null
    if (res.status === 429) return 'Too many attempts. Wait a minute and try again.'
    const body = (await res.json().catch(() => null)) as Json | null
    if (res.status < 500 && typeof body?.detail === 'string') return body.detail
  } catch {
    // network failure: fall through
  }
  return 'Accounts are unavailable right now. Try again later.'
}

export async function getMe(signal: AbortSignal): Promise<User | null> {
  try {
    const res = await fetch(`${BASE}/api/auth/me`, { signal, credentials: 'include' })
    const body: unknown = await res.json()
    return res.ok && isUser(body) ? body : null
  } catch {
    return null
  }
}

export type UrlThresholds = { thr_high: number; thr_medium: number }

/** Null when unknown, so the score bar shows no marks instead of invented ones (R8). */
export async function getUrlThresholds(signal: AbortSignal): Promise<UrlThresholds | null> {
  try {
    const res = await fetch(`${BASE}/api/model-info`, { signal })
    const url = ((await res.json()) as { url?: Partial<UrlThresholds> | null } | null)?.url
    const valid = [url?.thr_high, url?.thr_medium].every((v) => typeof v === 'number' && v >= 0 && v <= 100)
    return res.ok && valid ? (url as UrlThresholds) : null
  } catch {
    return null
  }
}

export type Metrics = Partial<Record<
  | 'n_legit' | 'n_spam' | 'n_phish' | 'macro_f1' | 'accuracy' | 'phish_recall' | 'phish_malicious_caught' | 'phish_to_legit'
  | 'legit_false_alert' | 'spam_recall' | 'ece' | 'uncertain_rate',
  number | null
>>
export type ModelInfo = {
  url: {
    version: string
    thr_high: number
    thr_medium: number
    metrics: {
      verdict: string | null
      results: { split: string; cohort: string; metric: 'recall' | 'false_alert'; n: number | null; rate: number | null; ci95: [number, number] | null }[]
      criteria: { name: string; value: number | null; target: number | null; passed: boolean }[]
    } | null
  } | null
  email: {
    version: string | null
    base_model: string | null
    labels: string[] | null
    max_length: number | null
    phishing_threshold: number | null
    uncertain_below: number | null
    trained: string | null
    metrics: {
      internal: Metrics
      external: Metrics
      external_ci95: Partial<Record<'macro_f1' | 'phish_recall' | 'phish_to_legit' | 'legit_false_alert', [number, number] | null>>
      external_by_source: (Metrics & { source: string })[]
      targets: { name: string; value: number | null; target: number | null; result: string }[]
      sources: { source: string; role: string; rows: number | null }[]
      split_design?: { phishing_pot?: string; enron?: Record<string, number>; fully_unseen_test_sources?: string[] } | null
    } | null
  } | null
}

/** Null when the models are down or the reply is not shaped as expected. */
export async function getModelInfo(signal: AbortSignal): Promise<ModelInfo | null> {
  try {
    const res = await fetch(`${BASE}/api/model-info`, { signal })
    const body: unknown = await res.json()
    return res.ok && isObject(body) && 'url' in body && 'email' in body ? (body as ModelInfo) : null
  } catch {
    return null
  }
}

export async function getHealth(signal: AbortSignal): Promise<Health | null> {
  try {
    const res = await fetch(`${BASE}/api/health`, { signal })
    const body = (await res.json()) as Json
    return { status: String(body.status), url_model: body.url_model === true, email_model: body.email_model === true }
  } catch {
    return null
  }
}
