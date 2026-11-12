import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import EmailPage from '../src/pages/EmailPage'
import UrlPage from '../src/pages/UrlPage'

const BASE = 'http://localhost:8000'
const server = setupServer(
  http.get(`${BASE}/api/model-info`, () => HttpResponse.json({ url: { version: 'v', thr_high: 88.8, thr_medium: 44.4 }, email: null })),
)
const FORBIDDEN_WORD = new RegExp('\\b' + ['sa', 'fe'].join('') + '\\b', 'i')

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
})
afterAll(() => server.close())

const urlResult = (band: string, evidence: string[] = ['Uses lure words']) => ({
  model: 'mlphil_url_v5',
  band,
  score: band === 'High' ? 100 : band === 'Medium' ? 80 : 3.3,
  evidence,
  url_defanged: 'hxxps://paypal[.]example/signin',
  note: 'note from model',
  disclaimer: 'URL-text analysis only. The link was not opened. A Low band is not a safety guarantee.',
})

const emailResult = (verdict: string, prediction = verdict) => ({
  prediction,
  verdict,
  confidence: 0.9,
  probabilities: { LEGITIMATE: 0.05, SPAM: 0.05, PHISHING: 0.9 },
  truncated: false,
  model_version: 'email_security_model, trained 2026-11-05 06:49',
  note: 'Calibrated model probability. Advisory only: a low phishing score does not prove an email is ' + ['sa', 'fe'].join('') + '.',
})

function stub(path: string, body: unknown, status = 200) {
  server.use(http.post(`${BASE}${path}`, () => HttpResponse.json(body as never, { status })))
}

/** The email page calls analyze-email: wrap an email result as that response with no links. */
function stubEmail(email: unknown, status = 200) {
  const body = status === 200 ? { email, urls: [], urls_found: 0, urls_checked: 0, urls_capped: false, overall: 'LOW', overall_reason: 'r' } : email
  stub('/api/analyze-email', body, status)
}

const SUBMITTED = 'https://paypal.example/signin'

function submitUrl() {
  render(<MemoryRouter><UrlPage /></MemoryRouter>)
  fireEvent.change(screen.getByLabelText('Web address'), { target: { value: SUBMITTED } })
  fireEvent.click(screen.getByRole('button', { name: 'Check' }))
}

function submitEmail() {
  render(<MemoryRouter><EmailPage /></MemoryRouter>)
  fireEvent.change(screen.getByLabelText('Body'), { target: { value: `Visit ${SUBMITTED} now <img src=x onerror=alert(1)>` } })
  fireEvent.click(screen.getByRole('button', { name: 'Check' }))
}

function expectNoForbiddenWord() {
  expect(document.body.textContent).not.toMatch(FORBIDDEN_WORD)
}

describe('URL results', () => {
  it.each([
    ['High', 'High phishing risk'],
    ['Medium', 'Suspicious link'],
    ['Low', 'No warning signs found in this URL'],
  ])('%s renders "%s"', async (band, badge) => {
    stub('/api/check-url', urlResult(band))
    submitUrl()
    expect(await screen.findByRole('heading', { name: badge })).toBeTruthy()
    expectNoForbiddenWord()
  })

  it.each([
    ['High', 'Do not open this link or enter any details on it.'],
    ['Medium', "Do not open it yet. Go to the organisation's website yourself to check the message."],
    ['Low', 'Still check who sent it before entering any details.'],
  ])('%s tells the user what to do', async (band, action) => {
    stub('/api/check-url', urlResult(band))
    submitUrl()
    expect(await screen.findByText(action)).toBeTruthy()
  })

  it.each(['High', 'Medium'])('%s with no matched rule explains the score instead of contradicting the badge', async (band) => {
    stub('/api/check-url', urlResult(band, ['No strong URL-pattern indicators found']))
    submitUrl()
    expect(await screen.findByText(/character patterns in this address/)).toBeTruthy()
    expect(screen.queryByText('No strong URL-pattern indicators found')).toBeNull()
  })

  it('Low keeps the original no-indicators line', async () => {
    stub('/api/check-url', urlResult('Low', ['No strong URL-pattern indicators found']))
    submitUrl()
    expect(await screen.findByText('No strong URL-pattern indicators found')).toBeTruthy()
    expect(screen.queryByText(/character patterns in this address/)).toBeNull()
  })

  it('marks the bands on the score bar at the values from the API', async () => {
    stub('/api/check-url', urlResult('High'))
    submitUrl()
    expect(await screen.findByText('Marks: Suspicious from 44.4, High from 88.8')).toBeTruthy()
    const marks = screen.getAllByTestId('band-mark').map((m) => m.style.left)
    expect(marks).toEqual(['44.4%', '88.8%'])
  })

  it('shows no marks when the thresholds are unknown, rather than guessing', async () => {
    server.use(http.get(`${BASE}/api/model-info`, () => HttpResponse.json({ detail: 'UNAVAILABLE' }, { status: 503 })))
    stub('/api/check-url', urlResult('High'))
    submitUrl()
    await screen.findByRole('heading', { name: 'High phishing risk' })
    expect(screen.queryAllByTestId('band-mark')).toHaveLength(0)
    expect(screen.queryByText(/^Marks:/)).toBeNull()
  })

  it('Low says it is not a guarantee and the link was not opened', async () => {
    stub('/api/check-url', urlResult('Low'))
    submitUrl()
    expect(await screen.findByText('Not a safety guarantee. The link was not opened.')).toBeTruthy()
  })

  it('High shows at most three evidence items', async () => {
    stub('/api/check-url', urlResult('High', ['one', 'two', 'three', 'four']))
    submitUrl()
    await screen.findByText('three')
    expect(screen.queryByText('four')).toBeNull()
  })

  it('shows the model note when there is no evidence list', async () => {
    stub('/api/check-url', urlResult('High', []))
    submitUrl()
    expect(await screen.findByText('note from model')).toBeTruthy()
  })

  it('shows the URL defanged and never as a link', async () => {
    stub('/api/check-url', urlResult('High'))
    submitUrl()
    const code = await screen.findByText('hxxps://paypal[.]example/signin')
    expect(code.tagName).toBe('CODE')
    expect(document.querySelectorAll('a')).toHaveLength(0)
  })
})

describe('email results', () => {
  it.each([
    ['PHISHING', 'Likely phishing'],
    ['SPAM', 'Likely spam'],
    ['LEGITIMATE', 'No phishing or spam pattern found'],
  ])('%s renders "%s" with three probability bars', async (verdict, badge) => {
    stubEmail(emailResult(verdict))
    submitEmail()
    expect(await screen.findByRole('heading', { name: badge })).toBeTruthy()
    expect(screen.getAllByRole('meter')).toHaveLength(3)
    expectNoForbiddenWord()
  })

  it('footer shows the version and the site disclaimer, not the model note', async () => {
    stubEmail(emailResult('LEGITIMATE'))
    submitEmail()
    expect(await screen.findByText('email_security_model, trained 2026-11-05 06:49')).toBeTruthy()
    expect(screen.getByText('Advisory only. A low phishing score is not a safety guarantee.')).toBeTruthy()
    expect(screen.queryByText(/^Calibrated/)).toBeNull()
  })

  it('UNCERTAIN shows the leaning', async () => {
    stubEmail(emailResult('UNCERTAIN', 'SPAM'))
    submitEmail()
    expect(await screen.findByRole('heading', { name: 'Model is unsure' })).toBeTruthy()
    expect(screen.getByText('Leaning: SPAM. Verify manually.')).toBeTruthy()
  })

  it('flags a truncated email', async () => {
    stubEmail({ ...emailResult('SPAM'), truncated: true })
    submitEmail()
    expect(await screen.findByText('Long email: only the start and end were analysed.')).toBeTruthy()
  })

  it('never turns pasted email content into live markup', async () => {
    stubEmail(emailResult('PHISHING'))
    submitEmail()
    await screen.findByRole('heading', { name: 'Likely phishing' })
    expect(document.querySelectorAll('img, iframe, a')).toHaveLength(0)
  })

  it('blocks submit past the character limit', () => {
    render(<MemoryRouter><EmailPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Body'), { target: { value: 'x'.repeat(100_001) } })
    expect((screen.getByRole('button', { name: 'Check' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByRole('alert').textContent).toContain('100,000')
  })
})

describe('failures never look like a clean result', () => {
  const unavailable = 'Analysis unavailable'

  it('503 shows the unavailable card', async () => {
    stub('/api/check-url', { detail: 'UNAVAILABLE' }, 503)
    submitUrl()
    expect(await screen.findByRole('heading', { name: unavailable })).toBeTruthy()
    expect(screen.getByText('Model not loaded. Nothing was concluded about this input.')).toBeTruthy()
    expectNoForbiddenWord()
  })

  it.each([
    ['unknown band', { ...urlResult('Low'), band: 'Fine' }],
    ['score out of range', { ...urlResult('Low'), score: 500 }],
    ['empty object', {}],
    ['null', null],
  ])('200 with %s is treated as unavailable', async (_, body) => {
    stub('/api/check-url', body)
    submitUrl()
    expect(await screen.findByRole('heading', { name: unavailable })).toBeTruthy()
  })

  it('email 200 with an unknown verdict is treated as unavailable', async () => {
    stubEmail({ ...emailResult('LEGITIMATE'), verdict: 'FINE' })
    submitEmail()
    expect(await screen.findByRole('heading', { name: unavailable })).toBeTruthy()
  })

  it('a network failure is treated as unavailable', async () => {
    server.use(http.post(`${BASE}/api/check-url`, () => HttpResponse.error()))
    submitUrl()
    expect(await screen.findByRole('heading', { name: unavailable })).toBeTruthy()
  })

  it('422 is an inline field error with no result card', async () => {
    stub('/api/check-url', { detail: 'server says no' }, 422)
    submitUrl()
    expect((await screen.findByRole('alert')).textContent).toBe('server says no')
    expect(document.querySelector('article')).toBeNull()
  })

  it('email 422 shows the message from the handler', async () => {
    stubEmail({ detail: { message: 'empty email' } }, 422)
    submitEmail()
    expect((await screen.findByRole('alert')).textContent).toBe('empty email')
    expect(document.querySelector('article')).toBeNull()
  })

  it('429 is a toast with no result card', async () => {
    stub('/api/check-url', { detail: 'slow down' }, 429)
    submitUrl()
    expect((await screen.findByRole('status')).textContent).toBe('Too many checks — wait a minute')
    expect(document.querySelector('article')).toBeNull()
  })
})
