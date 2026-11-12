import { useEffect, useState, type FormEvent } from 'react'
import { checkUrl, getUrlThresholds, type UrlResult, type UrlThresholds } from '../api'
import { Examples, FieldError, INPUT, PANES, SectionHead, Submit } from '../components/Fields'
import { ResultRegion, UrlCard } from '../components/Result'
import { URL_EXAMPLES } from '../examples'
import { useCheck } from '../useCheck'

export default function UrlPage() {
  const [url, setUrl] = useState('')
  const { outcome, pending, run } = useCheck<UrlResult>()
  const [thresholds, setThresholds] = useState<UrlThresholds | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    void getUrlThresholds(controller.signal).then(setThresholds)
    return () => controller.abort()
  }, [])

  function submit(event: FormEvent) {
    event.preventDefault()
    void run((signal) => checkUrl(url, signal))
  }

  const error = outcome?.kind === 'invalid' ? outcome.message : undefined
  return (
    <div className={PANES}>
      <div>
      <SectionHead mark="A" title="Check a URL">
        The model reads the address as text and looks for phishing patterns. The URL is never opened, visited or looked up.
      </SectionHead>
      <form onSubmit={submit} noValidate>
        <label htmlFor="url" className="mb-2 block font-semibold">
          Web address
        </label>
        <div className="flex flex-col gap-3 sm:flex-row">
          <input
            id="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            maxLength={2048}
            autoComplete="off"
            spellCheck={false}
            placeholder="example.com/login"
            aria-invalid={Boolean(error)}
            aria-describedby={error ? 'url-error' : undefined}
            className={INPUT}
          />
          <Submit pending={pending} disabled={!url.trim()} />
        </div>
        <FieldError id="url-error" message={error} />
      </form>
      <div className="mt-4">
        <Examples items={URL_EXAMPLES} label={(u) => u} onPick={setUrl} />
      </div>
      </div>
      <ResultRegion outcome={outcome} pending={pending} render={(data) => <UrlCard result={data} thresholds={thresholds} />} />
    </div>
  )
}
