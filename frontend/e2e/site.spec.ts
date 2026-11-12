import { expect, test } from '@playwright/test'

const FORBIDDEN_WORD = new RegExp('\\b' + ['sa', 'fe'].join('') + '\\b', 'i')

test.beforeEach(async ({ request }) => {
  const health = await (await request.get('/api/health')).json()
  expect(health, 'both real models must be loaded for e2e').toMatchObject({ url_model: true, email_model: true })
})

test('example phishing email: overall High banner and a link table', async ({ page }) => {
  await page.goto('/email')
  await page.getByRole('button', { name: 'Account suspended' }).click()
  await page.getByRole('button', { name: 'Check', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'High risk' })).toBeVisible()
  await expect(page.getByText(/^Email classified PHISHING; 1 of 1 link rated High$/)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Likely phishing' })).toBeVisible()

  const table = page.getByRole('table')
  await expect(table).toBeVisible()
  await expect(table.getByRole('row').nth(1)).toContainText('hxxp://northwind-bank-verify[.]xyz/login[.]php')
  await expect(table.getByRole('row').nth(1)).toContainText('High risk')

  expect(await page.locator('main a').count()).toBe(0) // links are never clickable (R4)
  expect(await page.locator('main').innerText()).not.toMatch(FORBIDDEN_WORD)
})

test('URL check: phishing-style address is High, shown defanged', async ({ page }) => {
  await page.goto('/url')
  await page.getByLabel('Web address').fill('paypal.com.secure-verify.xyz/signin')
  await page.getByRole('button', { name: 'Check', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'High phishing risk' })).toBeVisible()
  await expect(page.getByText('paypal[.]com[.]secure-verify[.]xyz/signin')).toBeVisible()
  await expect(page.getByText(/real domain is 'secure-verify.xyz'/)).toBeVisible()
})

test('.eml upload ignores the attachment', async ({ page }) => {
  const eml = [
    'From: Northwind Bank <alerts@northwind-bank.example>',
    'Subject: Your account is suspended',
    'MIME-Version: 1.0',
    'Content-Type: multipart/mixed; boundary="B"',
    '',
    '--B',
    'Content-Type: text/html; charset=utf-8',
    '',
    '<p>Unusual activity. <a href="http://northwind-bank-verify.xyz/login.php">Verify your account</a> within 24 hours.</p>',
    '--B',
    'Content-Type: text/plain',
    'Content-Disposition: attachment; filename="notes.txt"',
    '',
    'http://attachment-link.example/should-not-appear',
    '--B--',
    '',
  ].join('\r\n')

  await page.goto('/email')
  await page.getByRole('tab', { name: 'Upload .eml' }).click()
  await page.getByLabel(/Email file/).setInputFiles({ name: 'suspended.eml', mimeType: 'message/rfc822', buffer: Buffer.from(eml) })
  await page.getByRole('button', { name: 'Check', exact: true }).click()

  await expect(page.getByText('Your account is suspended')).toBeVisible()
  await expect(page.getByRole('table')).toContainText('northwind-bank-verify[.]xyz')
  await expect(page.locator('main')).not.toContainText('attachment-link')
})

test('How it works shows figures from the model reports', async ({ page, request }) => {
  const info = await (await request.get('/api/model-info')).json()
  const recall = `${(info.email.metrics.external.phish_recall * 100).toFixed(1)}%`
  const bands = `Suspicious from ${info.url.thr_medium.toFixed(1)}, High from ${info.url.thr_high.toFixed(1)}`
  await page.goto('/how-it-works')
  await expect(page.getByText(bands)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Email model: measured results' })).toBeVisible()
  await expect(page.getByRole('row', { name: /Phishing caught as PHISHING/ })).toContainText(recall)
})
