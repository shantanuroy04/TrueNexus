import { useEffect, useState, type ReactNode } from 'react'
import { getModelInfo, type Metrics, type ModelInfo } from '../api'

const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
const range = (r: [number, number] | null | undefined) => (r ? `${pct(r[0])} to ${pct(r[1])}` : '—')

function Steps({ steps }: { steps: string[] }) {
  return (
    <ol className="space-y-2">
      {steps.map((step, i) => (
        <li key={step} className="flex gap-3">
          <span className="flex size-7 shrink-0 items-center justify-center border border-ink font-mono text-sm">{i + 1}</span>
          <span className="pt-0.5">{step}</span>
        </li>
      ))}
    </ol>
  )
}

function Panel({ mark, title, children }: { mark: string; title: string; children: ReactNode }) {
  return (
    <section className="space-y-5 border border-rule bg-sheet p-6 sm:p-8">
      <header>
        <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">Section {mark}</p>
        <h2 className="mt-1 font-display text-3xl">{title}</h2>
      </header>
      {children}
    </section>
  )
}

function Sub({ children }: { children: ReactNode }) {
  return <h3 className="font-mono text-xs tracking-widest text-ink-soft uppercase">{children}</h3>
}

function Cannot({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1 pl-5">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  )
}

const ROWS: { key: keyof Metrics; label: string; better: string }[] = [
  { key: 'phish_recall', label: 'Phishing caught as PHISHING', better: 'higher is better' },
  { key: 'phish_malicious_caught', label: 'Phishing given any warning (SPAM or PHISHING)', better: 'higher is better' },
  { key: 'phish_to_legit', label: 'Phishing passed as LEGITIMATE', better: 'lower is better' },
  { key: 'legit_false_alert', label: 'Legitimate email wrongly flagged', better: 'lower is better' },
  { key: 'macro_f1', label: 'Macro F1 (all three classes)', better: 'higher is better' },
]

type UrlMetricsData = NonNullable<NonNullable<ModelInfo['url']>['metrics']>

const SPLIT_TEXT: Record<string, string> = { test: 'Internal test', ext_test: 'External test' }

/** URL model results at the High band, read from the bundle's final_report.json. */
function UrlMetrics({ metrics }: { metrics: UrlMetricsData }) {
  const table = (metric: 'recall' | 'false_alert', title: string) => {
    const rows = metrics.results.filter((r) => r.metric === metric)
    if (!rows.length) return null
    return (
      <div className="overflow-x-auto">
        <p className="text-sm font-semibold">{title}</p>
        <table className="mt-1 w-full text-left text-sm">
          <thead className="font-mono text-xs text-ink-soft uppercase">
            <tr>
              <th className="pb-1 font-normal">Test</th>
              <th className="pb-1 font-normal">Source</th>
              <th className="pb-1 font-normal">URLs</th>
              <th className="pb-1 font-normal">Rate</th>
              <th className="pb-1 font-normal">95% range</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.split}-${r.cohort}`} className="border-t border-rule font-mono">
                <td className="py-1 pr-3 font-sans">{SPLIT_TEXT[r.split] ?? r.split}</td>
                <td className="py-1 pr-3 font-sans">{r.cohort}</td>
                <td className="py-1 pr-3">{r.n == null ? '—' : r.n.toLocaleString('en-IN')}</td>
                <td className="py-1 pr-3 font-semibold">{pct(r.rate)}</td>
                <td className="py-1">{range(r.ci95)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  return (
    <div className="space-y-4">
      {table('recall', 'Phishing rated High (higher is better)')}
      {table('false_alert', 'Legitimate rated High (lower is better)')}
      {metrics.criteria.length > 0 && (
        <ul className="space-y-1 font-mono text-xs">
          {metrics.criteria.map((c) => (
            <li key={c.name}>
              {c.name}: {pct(c.value)} — <span className={c.passed ? '' : 'font-semibold text-danger'}>{c.passed ? 'PASS' : 'FAIL'}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

type EmailMetricsData = NonNullable<NonNullable<ModelInfo['email']>['metrics']>

const ROLE_TEXT: Record<string, string> = {
  train: 'training',
  external: 'test only, never used for training',
  split: 'split by groups of near-identical emails between training, tuning and test',
}

/** What the "external" test means differs between model versions, so it is described from the report. */
function TestDesign({ metrics }: { metrics: EmailMetricsData }) {
  const design = metrics.split_design
  const present = new Set(metrics.sources.map((s) => s.source))
  const unseen = (design?.fully_unseen_test_sources ?? []).filter((s) => present.has(s))
  if (!design) {
    return (
      <p className="max-w-prose text-ink-soft">
        The <strong className="text-ink">internal</strong> test uses unseen emails from the same sources as training. The{' '}
        <strong className="text-ink">external</strong> test uses sources never used for training or tuning, so it is the better guide to
        real-world use.
      </p>
    )
  }
  return (
    <div className="max-w-prose space-y-2 text-ink-soft">
      <p>
        The <strong className="text-ink">internal</strong> test uses unseen emails from the same sources as training. The{' '}
        <strong className="text-ink">external</strong> test holds emails kept out of training and tuning:
      </p>
      <ul className="list-disc space-y-1 pl-5">
        {design.phishing_pot && (
          <li>
            phishing_pot split by date ({design.phishing_pot}), so it tests <strong className="text-ink">newer</strong> phishing from a
            source the model has seen, not a brand-new source.
          </li>
        )}
        {design.enron && <li>Enron: groups of near-identical emails that were not used for training.</li>}
        {unseen.length > 0 && <li>Never used for training or tuning: {unseen.join(', ')}.</li>}
      </ul>
    </div>
  )
}

function EmailMetrics({ metrics }: { metrics: EmailMetricsData }) {
  return (
    <div className="space-y-6">
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="font-mono text-xs tracking-widest text-ink-soft uppercase">
            <tr>
              <th className="pb-2 font-normal">Measure</th>
              <th className="pb-2 font-normal">Internal test</th>
              <th className="pb-2 font-normal">External test</th>
              <th className="pb-2 font-normal">External 95% range</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map(({ key, label, better }) => (
              <tr key={key} className="border-t border-rule">
                <td className="py-2 pr-4">
                  {label} <span className="text-sm text-ink-soft">({better})</span>
                </td>
                <td className="py-2 pr-4 font-mono">{pct(metrics.internal[key])}</td>
                <td className="py-2 pr-4 font-mono font-semibold">{pct(metrics.external[key])}</td>
                <td className="py-2 font-mono text-sm">{range(metrics.external_ci95[key as keyof typeof metrics.external_ci95])}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <TestDesign metrics={metrics} />
      {metrics.targets.length > 0 && (
        <div>
          <Sub>Targets set before testing</Sub>
          <ul className="mt-2 space-y-1">
            {metrics.targets.map((t) => (
              <li key={t.name} className="font-mono text-sm">
                {t.name}: {pct(t.value)} against target {pct(t.target)} —{' '}
                <span className={t.result === 'PASS' ? '' : 'font-semibold text-danger'}>{t.result}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {metrics.external_by_source.length > 0 && (
        <div>
          <Sub>External test by source</Sub>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="font-mono text-xs text-ink-soft uppercase">
                <tr>
                  <th className="pb-1 font-normal">Source</th>
                  <th className="pb-1 font-normal">Emails</th>
                  <th className="pb-1 font-normal">Phishing caught</th>
                  <th className="pb-1 font-normal">Legitimate wrongly flagged</th>
                  <th className="pb-1 font-normal">Spam caught</th>
                </tr>
              </thead>
              <tbody>
                {metrics.external_by_source.map((s) => (
                  <tr key={s.source} className="border-t border-rule font-mono">
                    <td className="py-1.5 pr-4 font-sans">{s.source}</td>
                    <td className="py-1.5 pr-4">{((s.n_legit ?? 0) + (s.n_spam ?? 0) + (s.n_phish ?? 0)).toLocaleString('en-IN')}</td>
                    <td className="py-1.5 pr-4">{pct(s.phish_recall)}</td>
                    <td className="py-1.5 pr-4">{pct(s.legit_false_alert)}</td>
                    <td className="py-1.5">{pct(s.spam_recall)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {metrics.sources.length > 0 && (
        <div>
          <Sub>Data sources</Sub>
          <ul className="mt-2 space-y-1 text-sm">
            {metrics.sources.map((s) => (
              <li key={s.source}>
                <span className="font-semibold">{s.source}</span>: {ROLE_TEXT[s.role] ?? s.role}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

export default function HowItWorks() {
  const [info, setInfo] = useState<ModelInfo | null | undefined>(undefined)

  useEffect(() => {
    const controller = new AbortController()
    void getModelInfo(controller.signal).then((i) => {
      if (!controller.signal.aborted) setInfo(i)
    })
    return () => controller.abort()
  }, [])

  const url = info?.url
  const email = info?.email
  return (
    <div className="space-y-8">
      <header>
        <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">About the models</p>
        <h1 className="mt-1 font-display text-4xl sm:text-5xl">How it works</h1>
        <p className="mt-3 max-w-prose text-ink-soft">
          Two separate models read text. Neither opens a link, loads a page or contacts any outside service. Their results are advisory.
        </p>
        {info === null && (
          <p role="status" className="mt-3 font-semibold text-danger">
            Model details are unavailable right now, so no figures are shown.
          </p>
        )}
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel mark="A" title="URL model">
          <Steps
            steps={[
              'The address is read as text. It is never opened, looked up or visited.',
              'It is tidied first: the http(s):// prefix, www. and a trailing slash are removed.',
              'Features are measured: domain structure, brand names, lure words such as "login" or "verify", look-alike spellings and character patterns.',
              'A gradient-boosted tree model (LightGBM) turns them into a risk score from 0 to 100.',
              url
                ? `The score sets the band: Suspicious from ${url.thr_medium.toFixed(1)}, High from ${url.thr_high.toFixed(1)}.`
                : 'The score sets the band: Low, Suspicious or High.',
            ]}
          />
          <div className="space-y-2">
            <Sub>What it cannot do</Sub>
            <Cannot
              items={[
                'See what the page contains, so a hacked real website can score low.',
                'See where a link shortener leads.',
                'Know who sent the link.',
              ]}
            />
          </div>
          <div className="space-y-2">
            <Sub>Measured results</Sub>
            {url?.metrics ? <UrlMetrics metrics={url.metrics} /> : <p>Test results for this version are not yet available in the app.</p>}
            {url && <p className="font-mono text-xs text-ink-soft">{url.version}</p>}
          </div>
        </Panel>

        <Panel mark="B" title="Email model">
          <Steps
            steps={[
              'The subject and body are read as text. For an uploaded .eml file, only the main body is used and attachments are ignored.',
              'The text is cleaned: HTML is removed, each link is reduced to its host name, and email addresses and long numbers are masked.',
              email?.base_model && email.max_length
                ? `A fine-tuned ${email.base_model} model reads up to ${email.max_length} tokens, keeping the start and end of long emails.`
                : 'A fine-tuned DistilBERT model reads the text, keeping the start and end of long emails.',
              'It gives a probability for LEGITIMATE, SPAM and PHISHING.',
              email?.uncertain_below != null
                ? `If no class reaches ${pct(email.uncertain_below)}, the result is "Model is unsure".`
                : 'If no class is clearly ahead, the result is "Model is unsure".',
              'On this site, every link in the email is also checked by the URL model. The stronger warning wins.',
            ]}
          />
          <div className="space-y-2">
            <Sub>What it cannot do</Sub>
            <Cannot
              items={[
                'Check the real sender, the mail headers or attachments.',
                'Read non-English email reliably: its base model was trained on English.',
                'Keep up with new scams on its own: it needs retraining as scams change.',
                'Reliably tell routine account emails (password resets, one-time codes, statements) from phishing: they can be flagged.',
              ]}
            />
          </div>
          {email?.trained && <p className="font-mono text-xs text-ink-soft">{email.version}</p>}
        </Panel>
      </div>

      <section className="space-y-5 border border-rule bg-sheet p-6 sm:p-8">
        <h2 className="font-display text-3xl">Email model: measured results</h2>
        {info === undefined && <p className="text-ink-soft">Loading…</p>}
        {info !== undefined &&
          (email?.metrics ? (
            <EmailMetrics metrics={email.metrics} />
          ) : (
            <p>Measured results are not available in this build.</p>
          ))}
      </section>
    </div>
  )
}
