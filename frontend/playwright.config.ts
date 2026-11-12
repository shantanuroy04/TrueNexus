import { defineConfig } from '@playwright/test'

// End-to-end against the real backend and real models. Starts both servers if they are not
// already running. Uses the installed Google Chrome, so no browser download is needed.
const python = process.platform === 'win32' ? '.venv\\Scripts\\python' : '.venv/bin/python'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: 0,
  workers: 1, // one backend, shared rate limit
  use: { baseURL: 'http://localhost:5173', channel: 'chrome', trace: 'retain-on-failure' },
  webServer: [
    {
      command: `${python} -m uvicorn main:app --port 8000 --no-server-header`,
      cwd: '../backend',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: true,
      timeout: 180_000,
      env: { MLPHIL_URL_BUNDLE: '../models/model_bundle', MLPHIL_EMAIL_MODEL_DIR: '../models/email_security_model' },
    },
    { command: 'npm run dev', url: 'http://localhost:5173', reuseExistingServer: true, timeout: 60_000 },
  ],
})
