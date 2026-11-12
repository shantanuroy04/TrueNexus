import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import EmailPage from '../src/pages/EmailPage'

const BASE = 'http://localhost:8000'
const server = setupServer()
const FORBIDDEN_WORD = new RegExp('\\b' + ['sa', 'fe'].join('') + '\\b', 'i')

beforeAll(() => server.listen({ onUnhandledFrame: 'error' }))
afterEach(() => {
  cleanup()
  server.resetHandlers()
})
afterAll(() => server.close())

const email = (verdict = 'LEGITIMATE') => ({
  prediction: verdict,
  verdict,
  confidence: 0.9,
  probabilities: { LEGITIMATE: 0.9, SPAM: 0.05, PHISHING: 0.05 },
  truncated: false,
  model_version: 'm',
})
const link = (band: string, host: string, evidence = ['Uses lure words']) => ({
  model: 'u',
  band,
  score: band === 'High' ? 99.9 : band === 'Medium' ? 80 : 2,
  evidence,
  url_defanged: `hxxp://${host}[.]example/`,
  note: 'n',
  disclaimer: 'd',
})
const result = (over: Record<string, unknown> = {}) => ({
  email: email(),
  urls: [],
  urls_found: 0,
  urls_checked: 0,
  urls_capped: false,
  overall: 'LOW',
  overall_reason: 'Email classified LEGITIMATE; no links found',
  ...over,
})

function stub(path: string, body: unknown, status = 200) {
  server.use(http.post(`${BASE}${path}`, () => HttpResponse.json(body as never, { status })))
}

function paste() {
  render(<MemoryRouter><EmailPage /></MemoryRouter>)
  fireEvent.change(screen.getByLabelText('Body'), { target: { value: 'hello http://x.example' } })
  fireEvent.click(screen.getByRole('button', { name: 'Check' }))
}

describe('email + links result', () => {
  it('shows the overall banner with the reason, then links worst first', async () => {
    stub(
      '/api/analyze-email',
      result({
        urls: [link('Low', 'low'), { url_defanged: 'hxxp://gone[.]example/', band: 'UNAVAILABLE' }, link('High', 'high'), link('Medium', 'mid')],
        urls_found: 4,
        urls_checked: 4,
        overall: 'HIGH',
        overall_reason: 'Email classified LEGITIMATE; 1 of 4 links rated High',
      }),
    )
    paste()
    expect(await screen.findByRole('heading', { name: 'High risk' })).toBeTruthy()
    expect(screen.getByText('Email classified LEGITIMATE; 1 of 4 links rated High')).toBeTruthy()
    const rows = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    expect(rows.map((r) => r.querySelector('code')?.textContent)).toEqual([
      'hxxp://high[.]example/',
      'hxxp://mid[.]example/',
      'hxxp://gone[.]example/',
      'hxxp://low[.]example/',
    ])
    expect(within(rows[2]).getByText('Not checked')).toBeTruthy()
    expect(document.querySelectorAll('a')).toHaveLength(0)
    expect(document.body.textContent).not.toMatch(FORBIDDEN_WORD)
  })

  it('says how many links were checked when capped', async () => {
    stub('/api/analyze-email', result({ urls: [link('Low', 'a')], urls_found: 34, urls_checked: 20, urls_capped: true }))
    paste()
    expect(await screen.findByText(/Checked 20 of 34 links/)).toBeTruthy()
  })

  it('says when an email has no links', async () => {
    stub('/api/analyze-email', result())
    paste()
    expect(await screen.findByText('No links found in this email.')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'No warning signs found' })).toBeTruthy()
  })

  it('a partial result is shown as incomplete, never as clean', async () => {
    stub('/api/analyze-email', result({ email: { verdict: 'UNAVAILABLE' }, overall: 'UNAVAILABLE', overall_reason: 'Email model unavailable; no links found' }))
    paste()
    expect(await screen.findByRole('heading', { name: 'Analysis incomplete' })).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Email text not analysed' })).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'No warning signs found' })).toBeNull()
  })

  it.each([
    ['unknown overall', { overall: 'FINE' }],
    ['link with unknown band', { urls: [{ url_defanged: 'x', band: 'Fine' }] }],
    ['missing email', { email: null }],
  ])('a reply with %s is treated as unavailable', async (_, over) => {
    stub('/api/analyze-email', result(over))
    paste()
    expect(await screen.findByRole('heading', { name: 'Analysis unavailable' })).toBeTruthy()
  })
})

describe('.eml upload', () => {
  function choose(file: File) {
    render(<MemoryRouter><EmailPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('tab', { name: 'Upload .eml' }))
    fireEvent.change(screen.getByLabelText(/Email file/), { target: { files: [file] } })
  }

  it('rejects a file that is not .eml before sending anything', () => {
    choose(new File(['x'], 'report.pdf'))
    expect(screen.getByRole('alert').textContent).toBe('Choose a .eml file (a saved email).')
    expect((screen.getByRole('button', { name: 'Check' }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('rejects a file over 2 MB before sending anything', () => {
    choose(new File([new Uint8Array(2 * 1024 * 1024 + 1)], 'big.eml'))
    expect(screen.getByRole('alert').textContent).toBe('File is larger than 2 MB.')
  })

  it('sends the file as message/rfc822 and shows the parsed subject as text', async () => {
    let contentType = ''
    server.use(
      http.post(`${BASE}/api/check-eml`, ({ request }) => {
        contentType = request.headers.get('content-type') ?? ''
        return HttpResponse.json(result({ parsed_subject: '<b>Account notice</b>', overall: 'HIGH', overall_reason: 'r' }))
      }),
    )
    choose(new File(['Subject: hi\n\nbody'], 'mail.eml'))
    fireEvent.click(screen.getByRole('button', { name: 'Check' }))
    expect(await screen.findByText('<b>Account notice</b>')).toBeTruthy()
    expect(contentType).toBe('message/rfc822')
    expect(document.querySelector('b')).toBeNull()
  })

  it('shows the server message for a file that is not an email', async () => {
    stub('/api/check-eml', { detail: { message: 'This file does not look like an email.' } }, 422)
    choose(new File(['junk'], 'odd.eml'))
    fireEvent.click(screen.getByRole('button', { name: 'Check' }))
    expect((await screen.findByRole('alert')).textContent).toBe('This file does not look like an email.')
  })
})
