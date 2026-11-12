import { Link } from 'react-router-dom'
import type { Health } from '../api'

function Entry({ to, mark, title, text, ready }: { to: string; mark: string; title: string; text: string; ready: boolean | null }) {
  return (
    <Link to={to} className="group flex min-h-52 flex-col border border-ink bg-sheet p-6 transition-colors hover:bg-ink hover:text-on-ink sm:p-8 lg:min-h-96">
      <span className="flex items-start justify-between gap-3">
        <span className="font-display text-6xl leading-none lg:text-7xl">{mark}</span>
        {ready === false && <span className="font-mono text-xs">Model not loaded</span>}
      </span>
      <span className="mt-auto pt-6 font-display text-3xl">{title}</span>
      <span className="mt-2">{text}</span>
    </Link>
  )
}

export default function Home({ health }: { health: Health | null | undefined }) {
  const ready = (loaded?: boolean) => (health ? Boolean(loaded) : health === null ? false : null)
  return (
    <div className="lg:grid lg:min-h-[calc(100dvh-12rem)] lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:items-center lg:gap-14">
      <div>
        <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">AI phishing detection</p>
        <h1 className="mt-3 font-display text-4xl leading-[1.1] sm:text-5xl lg:text-6xl">Read the bait without biting it.</h1>
        <p className="mt-5 max-w-prose text-lg text-ink-soft">
          TrueNexus checks a URL or an email as plain text and flags phishing patterns. It never opens what you give it, and its results are advisory.
        </p>
      </div>
      <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:mt-0">
        <Entry to="/url" mark="A" title="Check a URL" text="Paste a web address and get a risk band with a score." ready={ready(health?.url_model)} />
        <Entry to="/email" mark="B" title="Check an email" text="Paste a subject and body and see how the model classes it." ready={ready(health?.email_model)} />
      </div>
    </div>
  )
}
