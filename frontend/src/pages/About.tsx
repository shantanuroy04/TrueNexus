import type { ReactNode } from 'react'

const TEAM: { name: string; roll?: string }[] = [
  { name: 'Vishwesh Shukla', roll: '23052124' },
  { name: 'Amrita Bhattacharyya', roll: '2305515' },
  { name: 'Jonnadula Hansika', roll: '23051914' },
  { name: 'Adriti Purkayastha', roll: '23051890' },
  { name: 'Anusha Bakshi', roll: '2305520' },
  { name: 'Shantanu Roy', roll: '2305811' },
]
const SUPERVISOR = 'Ms. Indu Chaudhary, Assistant Professor'

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-3 border-t border-rule pt-6">
      <h2 className="font-display text-2xl">{title}</h2>
      {children}
    </section>
  )
}

export default function About() {
  return (
    <div className="max-w-3xl space-y-8">
      <header>
        <p className="font-mono text-xs tracking-widest text-ink-soft uppercase">About</p>
        <h1 className="mt-1 font-display text-4xl sm:text-5xl">TrueNexus</h1>
        <p className="mt-3 text-lg text-ink-soft">
          TrueNexus: an integrated machine learning system for URL and email phishing detection. A final-year B.Tech project (Computer Science and Engineering) at KIIT, Bhubaneswar. It checks a URL or an email as plain text and gives an
          advisory result.
        </p>
      </header>

      {(TEAM.length > 0 || SUPERVISOR) && (
        <Block title="Team">
          {TEAM.length > 0 && (
            <ul className="space-y-1">
              {TEAM.map((m) => (
                <li key={m.name}>
                  {m.name}
                  {m.roll && <span className="font-mono text-sm text-ink-soft"> · {m.roll}</span>}
                </li>
              ))}
            </ul>
          )}
          {SUPERVISOR && (
            <p>
              Supervisor: <span className="font-semibold">{SUPERVISOR}</span>
            </p>
          )}
        </Block>
      )}

      <Block title="What we store">
        <p>
          Nothing you check. URLs and emails are analysed in memory and never saved or logged. If you create an account, we store your
          name, your email address and a one-way hash of your password, nothing else.
        </p>
      </Block>

      <Block title="Built with">
        <p>
          React, TypeScript, Vite and Tailwind CSS for the website; FastAPI and SQLite for the server; LightGBM for the URL model; PyTorch,
          Hugging Face Transformers and DistilBERT for the email model.
        </p>
      </Block>

      <Block title="Data and licences">
        <ul className="list-disc space-y-3 pl-5">
          <li>
            <span className="font-semibold">Phishing email corpora curated by Champa et al.</span>, used through the Kaggle dataset{' '}
            <code className="font-mono text-sm">naserabdullahalam/phishing-email-dataset</code> (CEAS-08, SpamAssassin, Nazario, Nigerian
            Fraud, Enron and Ling). Licence: CC BY 4.0.
          </li>
          <li>
            <span className="font-semibold">phishing_pot</span> by rf-peixoto (GitHub), real phishing emails collected by honeypots, used
            only for external testing. Licence: CC BY-NC 4.0, so non-commercial use only.
          </li>
          <li>
            <span className="font-semibold">DistilBERT</span> (<code className="font-mono text-sm">distilbert-base-uncased</code>) by Hugging
            Face, the base of the email model. Licence: Apache 2.0.
          </li>
          <li>The URL model's training sources are listed in the project report.</li>
        </ul>
      </Block>
    </div>
  )
}
