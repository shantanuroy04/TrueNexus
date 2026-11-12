import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import App from '../src/App'

const BASE = 'http://localhost:8000'
const ALICE = { name: 'Alice', email: 'alice@example.com' }
const FORBIDDEN_WORD = new RegExp('\\b' + ['sa', 'fe'].join('') + '\\b', 'i')

const metrics = (recall: number) => ({ macro_f1: 0.737, phish_recall: recall, phish_to_legit: 0.051, legit_false_alert: 0.087 })
const INFO = {
  url: { version: 'mlphil_url_v5', thr_high: 91.306, thr_medium: 67.201, metrics: null },
  email: {
    version: 'email_security_model, trained 2026-11-05 06:49',
    base_model: 'distilbert-base-uncased',
    labels: ['LEGITIMATE', 'SPAM', 'PHISHING'],
    max_length: 256,
    phishing_threshold: 0.5,
    uncertain_below: 0.6,
    trained: '2026-11-05 06:49',
    metrics: {
      internal: metrics(0.989),
      external: metrics(0.5417),
      external_ci95: { phish_recall: [0.521, 0.56], macro_f1: null, phish_to_legit: null, legit_false_alert: null },
      external_by_source: [{ source: 'phishing_pot', n_phish: 2627, phish_recall: 0.5417 }],
      targets: [{ name: 'external phishing recall', value: 0.542, target: 0.9, result: 'FAIL' }],
      sources: [
        { source: 'CEAS_08', role: 'train', rows: 39154 },
        { source: 'phishing_pot', role: 'external', rows: 3000 },
      ],
    },
  },
}

const server = setupServer(
  http.get(`${BASE}/api/health`, () => HttpResponse.json({ status: 'ready', url_model: true, email_model: true })),
  http.get(`${BASE}/api/auth/me`, () => HttpResponse.json({ detail: 'Not logged in.' }, { status: 401 })),
  http.get(`${BASE}/api/model-info`, () => HttpResponse.json(INFO)),
)

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
})
afterAll(() => server.close())

function open(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  )
}

describe('How it works', () => {
  it('shows the numbers the API reports, internal and external', async () => {
    open('/how-it-works')
    expect((await screen.findAllByText('54.2%')).length).toBe(2) // overall table and by-source table
    expect(screen.getByText('98.9%')).toBeTruthy()
    expect(screen.getByText('52.1% to 56.0%')).toBeTruthy()
    expect(screen.getByText('FAIL')).toBeTruthy()
    expect(screen.getByText(/Suspicious from 67.2, High from 91.3/)).toBeTruthy()
    expect(screen.getByText(/reads up to 256 tokens/)).toBeTruthy()
    expect(document.body.textContent).not.toMatch(FORBIDDEN_WORD)
  })

  it('describes a date-split test honestly when the report says so', async () => {
    const withDesign = structuredClone(INFO)
    Object.assign(withDesign.email.metrics, {
      split_design: { phishing_pot: 'train <= 2024, dev 2025, test >= 2026', enron: { train: 50 }, fully_unseen_test_sources: ['Ling', 'TREC_06'] },
      sources: [{ source: 'Enron', role: 'split', rows: 100 }, { source: 'Ling', role: 'external', rows: 50 }],
    })
    server.use(http.get(`${BASE}/api/model-info`, () => HttpResponse.json(withDesign)))
    open('/how-it-works')
    expect(await screen.findByText(/newer/)).toBeTruthy()
    expect(screen.getByText(/train <= 2024, dev 2025, test >= 2026/)).toBeTruthy()
    expect(screen.queryByText(/uses sources never used for training or tuning/)).toBeNull()
    expect(screen.getByText(/split by groups of near-identical emails/)).toBeTruthy()
    expect(screen.getByText('Never used for training or tuning: Ling.')).toBeTruthy() // TREC_06 absent from the data
  })

  it('shows URL results when the bundle has a report', async () => {
    const withUrl = structuredClone(INFO) as unknown as { url: { metrics: unknown } }
    withUrl.url.metrics = {
      verdict: 'ADVISORY_WITH_CAVEATS',
      results: [
        { split: 'ext_test', cohort: 'OpenPhish_feed', metric: 'recall', n: 152, rate: 0.812, ci95: [0.74, 0.86] },
        { split: 'ext_test', cohort: 'Tranco_roots', metric: 'false_alert', n: 1268, rate: 0.008, ci95: [0.004, 0.014] },
      ],
      criteria: [{ name: 'ext phishing recall (OpenPhish) >= 0.75', value: 0.812, target: 0.75, passed: true }],
    }
    server.use(http.get(`${BASE}/api/model-info`, () => HttpResponse.json(withUrl)))
    open('/how-it-works')
    expect(await screen.findByText('OpenPhish_feed')).toBeTruthy()
    expect(screen.getByText('81.2%')).toBeTruthy()
    expect(screen.getByText('0.8%')).toBeTruthy()
    expect(screen.queryByText('Test results for this version are not yet available in the app.')).toBeNull()
  })

  it('says URL results are not yet available instead of showing a number', async () => {
    open('/how-it-works')
    expect(await screen.findByText('Test results for this version are not yet available in the app.')).toBeTruthy()
  })

  it('shows no figures at all when the API is down', async () => {
    server.use(http.get(`${BASE}/api/model-info`, () => HttpResponse.json({ detail: 'UNAVAILABLE' }, { status: 503 })))
    open('/how-it-works')
    expect(await screen.findByText('Model details are unavailable right now, so no figures are shown.')).toBeTruthy()
    expect(screen.queryByText(/%$/)).toBeNull()
  })
})

describe('About', () => {
  it('credits the datasets with their licences', () => {
    open('/about')
    expect(screen.getByText(/Licence: CC BY 4.0/)).toBeTruthy()
    expect(screen.getByText(/CC BY-NC 4.0, so non-commercial use only/)).toBeTruthy()
    expect(document.body.textContent).not.toMatch(FORBIDDEN_WORD)
  })
})

describe('Account', () => {
  it('asks a logged-out visitor to log in', async () => {
    open('/account')
    expect(await screen.findByText(/to manage your account/)).toBeTruthy()
  })

  it('deletes the account only after password and confirmation', async () => {
    server.use(
      http.get(`${BASE}/api/auth/me`, () => HttpResponse.json(ALICE)),
      http.post(`${BASE}/api/auth/delete-account`, () => new HttpResponse(null, { status: 204 })),
    )
    open('/account')
    expect(await screen.findByText('alice@example.com')).toBeTruthy()
    const button = screen.getByRole('button', { name: 'Delete my account' }) as HTMLButtonElement
    fireEvent.change(screen.getByLabelText('Confirm with your password'), { target: { value: 'pw-123456' } })
    expect(button.disabled).toBe(true)
    fireEvent.click(screen.getByLabelText('I understand this cannot be undone.'))
    expect(button.disabled).toBe(false)
    fireEvent.click(button)
    expect(await screen.findByRole('heading', { name: 'Read the bait without biting it.' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Log in' })).toBeTruthy()
  })

  it('shows a wrong password message and keeps the user', async () => {
    server.use(
      http.get(`${BASE}/api/auth/me`, () => HttpResponse.json(ALICE)),
      http.post(`${BASE}/api/auth/delete-account`, () => HttpResponse.json({ detail: 'Password is incorrect.' }, { status: 401 })),
    )
    open('/account')
    fireEvent.change(await screen.findByLabelText('Confirm with your password'), { target: { value: 'wrong-pass' } })
    fireEvent.click(screen.getByLabelText('I understand this cannot be undone.'))
    fireEvent.click(screen.getByRole('button', { name: 'Delete my account' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Password is incorrect.')
    expect(screen.getByRole('button', { name: 'Log out' })).toBeTruthy()
  })
})
