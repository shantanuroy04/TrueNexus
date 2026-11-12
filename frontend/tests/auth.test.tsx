import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import App from '../src/App'

const BASE = 'http://localhost:8000'
const ALICE = { name: 'Alice', email: 'alice@example.com' }

const server = setupServer(
  http.get(`${BASE}/api/health`, () => HttpResponse.json({ status: 'ready', url_model: true, email_model: true })),
  http.get(`${BASE}/api/auth/me`, () => HttpResponse.json({ detail: 'Not logged in.' }, { status: 401 })),
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

function fill(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label, { exact: false }), { target: { value } })
}

describe('accounts', () => {
  it('shows Log in and Sign up when nobody is logged in', async () => {
    open('/')
    expect(await screen.findByRole('link', { name: 'Log in' })).toBeTruthy()
    expect(screen.getByRole('link', { name: 'Sign up' })).toBeTruthy()
  })

  it('shows the user when a session already exists', async () => {
    server.use(http.get(`${BASE}/api/auth/me`, () => HttpResponse.json(ALICE)))
    open('/')
    expect(await screen.findByText('Alice')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Log out' })).toBeTruthy()
  })

  it('a failed login shows the server message and stays logged out', async () => {
    // Node's fetch drops `credentials` before MSW sees it, so check what the page passes.
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    server.use(
      http.post(`${BASE}/api/auth/login`, () => HttpResponse.json({ detail: 'Email or password is incorrect.' }, { status: 401 })),
    )
    open('/login')
    fill('Email', 'alice@example.com')
    fill('Password', 'wrong-password')
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Email or password is incorrect.')
    const loginCall = fetchSpy.mock.calls.find(([url]) => String(url).endsWith('/api/auth/login'))
    expect(loginCall?.[1]?.credentials).toBe('include')
    fetchSpy.mockRestore()
    expect(screen.queryByRole('button', { name: 'Log out' })).toBeNull()
  })

  it('a successful signup logs in and returns to the home page', async () => {
    server.use(http.post(`${BASE}/api/auth/signup`, () => HttpResponse.json(ALICE, { status: 201 })))
    open('/signup')
    fill('Name', 'Alice')
    fill('Email', 'alice@example.com')
    fill('Password', 'correct horse battery')
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
    expect(await screen.findByRole('heading', { name: 'Read the bait without biting it.' })).toBeTruthy()
    expect(screen.getByText('Alice')).toBeTruthy()
  })

  it('log out forgets the user', async () => {
    server.use(
      http.get(`${BASE}/api/auth/me`, () => HttpResponse.json(ALICE)),
      http.post(`${BASE}/api/auth/logout`, () => new HttpResponse(null, { status: 204 })),
    )
    open('/')
    fireEvent.click(await screen.findByRole('button', { name: 'Log out' }))
    expect(await screen.findByRole('link', { name: 'Log in' })).toBeTruthy()
  })

  it('a server failure shows a plain message, not a stack trace', async () => {
    server.use(http.post(`${BASE}/api/auth/login`, () => HttpResponse.json({ detail: 'Traceback ...' }, { status: 500 })))
    open('/login')
    fill('Email', 'alice@example.com')
    fill('Password', 'whatever-123')
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Accounts are unavailable right now. Try again later.')
  })

  it('429 asks the user to wait', async () => {
    server.use(http.post(`${BASE}/api/auth/login`, () => HttpResponse.json({ detail: 'x' }, { status: 429 })))
    open('/login')
    fill('Email', 'alice@example.com')
    fill('Password', 'whatever-123')
    fireEvent.click(screen.getByRole('button', { name: 'Log in' }))
    expect((await screen.findByRole('alert')).textContent).toBe('Too many attempts. Wait a minute and try again.')
  })
})
