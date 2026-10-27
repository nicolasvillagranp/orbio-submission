import { useState } from 'react'
import { cardNote, cardTags } from './lib/answers'
import { ago } from './lib/format'
import type { Call, Candidate } from './types'
import { requestCall } from './useBoard'

type Props = { c: Candidate; activeCall?: Call; issue: string | null; now: Date; email: string; onOpen: () => void }

export default function CandidateCard({ c, activeCall, issue, now, email, onOpen }: Props) {
  const [err, setErr] = useState('')
  const note = cardNote(c)
  const tags = cardTags(c)

  async function call(e: React.MouseEvent) {
    e.stopPropagation()
    setErr(await requestCall(c.id, email))
  }

  return (
    <article className="cand" role="button" tabIndex={0} onClick={onOpen}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen() } }}>
      <div className="row">
        <div>
          <div className="name">{c.name || c.phone}</div>
          {c.name && <div className="phone">{c.phone}</div>}
        </div>
        <span className="when" title="Time in this column">{ago(now.getTime() - new Date(c.stage_changed_at).getTime())}</span>
      </div>
      {tags.length > 0 && <div className="tags">{tags.map((t) => <span className="tag" key={t}>{t}</span>)}</div>}
      {note && <div className={`note ${c.stage}`}>{note}</div>}
      {issue && !activeCall && <div className="note rejected">{issue}</div>}
      {activeCall ? (
        <span className="calling">{activeCall.status === 'in_call' ? 'On the call…' : 'Calling…'}</span>
      ) : c.stage === 'queue' && (
        <div className="actions">
          <button className="btn small ghost" onClick={call} disabled={c.is_demo}
            title={c.is_demo ? 'Demo candidates are never called' : undefined}>Call</button>
        </div>
      )}
      {err && <p className="msg">{err}</p>}
    </article>
  )
}
