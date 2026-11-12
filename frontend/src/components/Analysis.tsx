import type { AnalyzeResult, UrlEntry } from '../api'
import { LINK_BAND, OVERALL, UNAVAILABLE } from '../verdicts'
import { EmailCard, Headline, Label, Sheet, TONE_ICON, TONE_TEXT, explainEvidence } from './Result'

const ORDER = { High: 0, Medium: 1, UNAVAILABLE: 2, Low: 3 }

function LinkRow({ entry }: { entry: UrlEntry }) {
  const band = LINK_BAND[entry.band]
  const evidence = 'evidence' in entry ? explainEvidence(entry) : []
  return (
    <tr className="border-t border-rule align-top">
      <td className="py-3 pr-4">
        <code className="font-mono text-sm break-all">{entry.url_defanged}</code>
      </td>
      <td className={`py-3 pr-4 whitespace-nowrap ${TONE_TEXT[band.tone]}`}>
        <span className="inline-flex items-center gap-1.5 font-semibold">
          <svg viewBox="0 0 24 24" aria-hidden="true" className="size-4 shrink-0 fill-none stroke-current stroke-2">
            {TONE_ICON[band.tone]}
          </svg>
          {band.badge}
        </span>
      </td>
      <td className="py-3 pr-4 font-mono text-sm whitespace-nowrap">{'score' in entry ? entry.score.toFixed(1) : '—'}</td>
      <td className="py-3 text-sm">
        {evidence.length > 0 ? (
          <details>
            <summary className="cursor-pointer font-semibold">Why</summary>
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </details>
        ) : (
          <span className="text-ink-soft">—</span>
        )}
      </td>
    </tr>
  )
}

function LinksTable({ result }: { result: AnalyzeResult }) {
  const rows = [...result.urls].sort((a, b) => ORDER[a.band] - ORDER[b.band])
  return (
    <section className="border border-rule bg-sheet p-5 sm:p-7">
      <Label>Links in this email</Label>
      <p className="mb-3 text-sm text-ink-soft">
        {result.urls_capped
          ? `Checked ${result.urls_checked} of ${result.urls_found} links. Links are read as text and never opened.`
          : result.urls_checked === 0
            ? 'No links found in this email.'
            : `${result.urls_checked} ${result.urls_checked === 1 ? 'link' : 'links'} checked as text. None was opened.`}
      </p>
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead className="font-mono text-xs tracking-widest text-ink-soft uppercase">
              <tr>
                <th className="pb-2 font-normal">Link</th>
                <th className="pb-2 font-normal">Rating</th>
                <th className="pb-2 font-normal">Score</th>
                <th className="pb-2 font-normal">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((entry, i) => (
                <LinkRow key={`${entry.url_defanged}-${i}`} entry={entry} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

/** Overall banner, then the email card, then every link found in the email. */
export function AnalysisView({ result }: { result: AnalyzeResult }) {
  const banner = OVERALL[result.overall]
  return (
    <div className="space-y-5">
      <Sheet tone={banner.tone}>
        <Headline verdict={{ ...banner, subtext: result.overall_reason }} />
        <p className="font-semibold">{banner.action}</p>
        {result.parsed_subject !== undefined && (
          <p className="text-sm text-ink-soft">
            Uploaded email subject: <span className="text-ink">{result.parsed_subject || '(none)'}</span>
          </p>
        )}
      </Sheet>
      {result.email.verdict === 'UNAVAILABLE' ? (
        <Sheet tone="unavailable">
          <Headline verdict={{ ...UNAVAILABLE, badge: 'Email text not analysed' }} />
        </Sheet>
      ) : (
        <EmailCard result={result.email} />
      )}
      <LinksTable result={result} />
    </div>
  )
}
