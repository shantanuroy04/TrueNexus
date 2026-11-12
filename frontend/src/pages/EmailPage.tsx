import { useState, type FormEvent } from 'react'
import { analyzeEmail, analyzeEml, type AnalyzeResult } from '../api'
import { AnalysisView } from '../components/Analysis'
import { Examples, FieldError, INPUT, PANES, SectionHead, Submit } from '../components/Fields'
import { ResultRegion } from '../components/Result'
import { EMAIL_EXAMPLES } from '../examples'
import { useCheck } from '../useCheck'

const MAX_CHARS = 100_000
const MAX_EML_BYTES = 2 * 1024 * 1024

function Tabs({ tab, onChange }: { tab: 'paste' | 'upload'; onChange: (tab: 'paste' | 'upload') => void }) {
  const item = (value: 'paste' | 'upload', label: string) => (
    <button
      type="button"
      role="tab"
      aria-selected={tab === value}
      onClick={() => onChange(value)}
      className={`border-b-2 px-1 pb-1 font-semibold ${tab === value ? 'border-ink' : 'border-transparent text-ink-soft hover:border-rule'}`}
    >
      {label}
    </button>
  )
  return (
    <div role="tablist" aria-label="How to give the email" className="mb-5 flex gap-6">
      {item('paste', 'Paste text')}
      {item('upload', 'Upload .eml')}
    </div>
  )
}

export default function EmailPage() {
  const [tab, setTab] = useState<'paste' | 'upload'>('paste')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState<string>()
  const { outcome, pending, run } = useCheck<AnalyzeResult>()
  const chars = subject.length + body.length
  const tooLong = chars > MAX_CHARS

  function submit(event: FormEvent) {
    event.preventDefault()
    if (tab === 'paste') void run((signal) => analyzeEmail(subject, body, signal))
    else if (file) void run((signal) => analyzeEml(file, signal))
  }

  function pickFile(picked: File | undefined) {
    setFile(null)
    setFileError(undefined)
    if (!picked) return
    if (!picked.name.toLowerCase().endsWith('.eml')) setFileError('Choose a .eml file (a saved email).')
    else if (picked.size > MAX_EML_BYTES) setFileError('File is larger than 2 MB.')
    else setFile(picked)
  }

  const serverError = outcome?.kind === 'invalid' ? outcome.message : undefined
  const pasteError = tooLong ? 'Email is longer than 100,000 characters.' : serverError
  const uploadError = fileError ?? serverError
  return (
    <div className={PANES}>
      <div>
        <SectionHead mark="B" title="Check an email">
          The model reads the email text, and every link in it is checked with the URL model. Nothing is stored, and nothing is opened.
        </SectionHead>
        <Tabs tab={tab} onChange={setTab} />
        <form onSubmit={submit} noValidate className="space-y-4">
          {tab === 'paste' ? (
            <>
              <div>
                <label htmlFor="subject" className="mb-2 block font-semibold">
                  Subject <span className="font-normal text-ink-soft">(optional)</span>
                </label>
                <input id="subject" value={subject} onChange={(e) => setSubject(e.target.value)} autoComplete="off" className={INPUT} />
              </div>
              <div>
                <div className="mb-2 flex items-baseline justify-between gap-3">
                  <label htmlFor="body" className="font-semibold">
                    Body
                  </label>
                  <span className={`font-mono text-xs ${tooLong ? 'font-medium text-danger' : 'text-ink-soft'}`}>
                    {chars.toLocaleString('en-IN')} / {MAX_CHARS.toLocaleString('en-IN')}
                  </span>
                </div>
                <textarea
                  id="body"
                  value={body}
                  onChange={(e) => setBody(e.target.value)}
                  rows={10}
                  spellCheck={false}
                  aria-invalid={Boolean(pasteError)}
                  aria-describedby={pasteError ? 'body-error' : undefined}
                  className={`${INPUT} lg:h-[calc(100dvh-33rem)] lg:min-h-28`}
                />
                <FieldError id="body-error" message={pasteError} />
              </div>
              <div className="flex flex-wrap items-end gap-x-6 gap-y-4">
                <Submit pending={pending} disabled={!body.trim() || tooLong} />
                <Examples
                  items={EMAIL_EXAMPLES}
                  label={(e) => e.label}
                  onPick={(e) => {
                    setSubject(e.subject)
                    setBody(e.body)
                  }}
                />
              </div>
            </>
          ) : (
            <>
              <div>
                <label htmlFor="eml" className="mb-2 block font-semibold">
                  Email file <span className="font-normal text-ink-soft">(.eml, up to 2 MB)</span>
                </label>
                <input
                  id="eml"
                  type="file"
                  accept=".eml,message/rfc822"
                  onChange={(e) => pickFile(e.target.files?.[0])}
                  aria-invalid={Boolean(uploadError)}
                  aria-describedby={uploadError ? 'eml-error' : 'eml-help'}
                  className="block w-full border border-ink bg-sheet p-3 text-sm file:mr-4 file:border-0 file:bg-ink file:px-3 file:py-1 file:font-semibold file:text-on-ink"
                />
                <p id="eml-help" className="mt-2 text-sm text-ink-soft">
                  In most mail apps: open the email, then Save as or Download message. Attachments are ignored and never opened.
                </p>
                <FieldError id="eml-error" message={uploadError} />
              </div>
              <Submit pending={pending} disabled={!file} />
            </>
          )}
        </form>
      </div>
      <ResultRegion outcome={outcome} pending={pending} render={(data) => <AnalysisView result={data} />} />
    </div>
  )
}
