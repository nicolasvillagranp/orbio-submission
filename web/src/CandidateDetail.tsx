import { useEffect, useState } from 'react'
import { describeAnswer, FIELDS } from './lib/answers'
import { isDialling, lastCallIssue } from './lib/calls'
import { reasonLabel } from './lib/format'
import { supabase } from './supabase'
import { STAGES, type Stage } from './types'
import { requestCall, type Board } from './useBoard'
import type { Go } from './useRoute'

type Props = { data: Board; email: string; id: string; go: Go }

export default function CandidateDetail({ data, email, id, go }: Props) {
  const c = data.candidates.find((x) => x.id === id)
  const [note, setNote] = useState('')
  const [saved, setSaved] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => { setNote(c?.team_note ?? '') }, [c?.id, c?.team_note])

  if (!c) {
    return (
      <main className="card">
        <p>{data.loading ? 'Loading…' : 'This candidate is no longer on the board.'}</p>
        <a href="#/">Back to board</a>
      </main>
    )
  }

  const active = data.activeCall(c.id)
  const dialling = isDialling(active) // a request still waiting doesn't block decisions
  const issue = active ? null : lastCallIssue(data.calls, c.id)
  const stageLabel = STAGES.find((s) => s.id === c.stage)!.label
  const reasons = c.stage === 'rejected'
    ? (c.disqualify_reason ? [reasonLabel(c.disqualify_reason)] : [])
    : c.review_reasons.map(reasonLabel)
  const answered = FIELDS.filter((f) => c.answers[f.id])

  async function decide(stage: Stage) {
    setBusy(true)
    const { error } = await supabase.from('candidates').update({ stage, decided_by: email }).eq('id', c!.id)
    setBusy(false)
    if (error) setMsg(error.message)
    else go({ name: 'board' })
  }

  async function remove() {
    if (!window.confirm(`Delete ${c!.name || c!.phone} from the board? This can’t be undone.`)) return
    setBusy(true)
    const { error } = await supabase.from('candidates').delete().eq('id', c!.id)
    setBusy(false)
    if (error) setMsg(error.message)
    else go({ name: 'board' })
  }

  async function callAgain() {
    setBusy(true)
    setMsg(await requestCall(c!.id, email))
    setBusy(false)
  }

  async function saveNote() {
    if (note === c!.team_note) return
    const { error } = await supabase.from('candidates').update({ team_note: note }).eq('id', c!.id)
    setSaved(error ? error.message : 'Saved')
  }

  return (
    <>
      <div className="hero">
        <div className="inner" style={{ paddingTop: 8, paddingBottom: 0 }}>
          <a className="back" href="#/" aria-label="Back to board">
            <svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M15 5l-7 7 7 7" /></svg>
          </a>
        </div>
        <div className="inner">
          <div>
            <div className="nm">{c.name || c.phone}</div>
            <div className="ph">{c.name ? c.phone : ''}</div>
          </div>
          <span className={`pill ${c.stage}`}>{stageLabel}</span>
        </div>
      </div>

      <main className="page narrow" style={{ gap: 14 }}>
        {active && <div className="box"><span className="calling">{active.status === 'in_call' ? 'On the call now…' : 'Calling…'}</span></div>}

        {issue && <div className="banner">{issue}</div>}

        {(c.stage === 'revision' || c.stage === 'rejected') && reasons.length > 0 && (
          <section className={`why ${c.stage}`}>
            <strong>{c.stage === 'revision' ? 'Why it needs you' : 'Why it was rejected'}</strong>
            {reasons.map((r) => <span key={r}>{r}</span>)}
          </section>
        )}

        {c.stage === 'queue' && c.retry_reason && (
          <section className="box">
            Last call: {c.retry_reason === 'no_answer' ? 'no answer' : c.retry_reason === 'hung_up' ? 'hung up before the end' : 'failed'}
            {' '}({c.attempts} {c.attempts === 1 ? 'attempt' : 'attempts'}).
          </section>
        )}

        {c.summary && (
          <section className="box">
            <div className="h">Agent summary</div>
            <p>{c.summary}</p>
          </section>
        )}

        {answered.length > 0 && (
          <section className="box fields" aria-label="Screening answers">
            {answered.map((f) => {
              const a = c.answers[f.id]
              return (
                <div className="field" key={f.id}>
                  <span className="k">{f.label}</span>
                  <span className="v">
                    {describeAnswer(f.id, a)}
                    {a.flagged ? <span className="mark rev">review</span> : <span className="mark okm" aria-label="ok">✓</span>}
                    {a.note && !a.flagged && <div className="meta">{reasonLabel(a.note)}</div>}
                  </span>
                </div>
              )
            })}
          </section>
        )}

        {c.transcript.length > 0 && (
          <section className="box">
            <details className="transcript">
              <summary>Transcript ({c.transcript.length} messages)</summary>
              <div className="turns">
                {c.transcript.map((t, i) => (
                  <div key={i} className={`turn ${t.role}`}>
                    {t.role !== 'system' && <small>{t.role === 'agent' ? 'Agent' : c.name?.split(' ')[0] || 'Candidate'}</small>}
                    {t.text}
                  </div>
                ))}
              </div>
            </details>
          </section>
        )}

        <label>
          Team note
          <textarea rows={3} placeholder="Visible to the whole team" value={note}
            onChange={(e) => { setNote(e.target.value); setSaved('') }} onBlur={saveNote} />
          {saved && <span className={saved === 'Saved' ? 'ok' : 'msg'}>{saved}</span>}
        </label>

        <p className="meta">
          {c.decided_by ? `Decided by ${c.decided_by === 'agent' ? 'the agent' : c.decided_by}. ` : ''}
          Added {new Date(c.created_at).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
          {c.is_demo ? ' · demo candidate' : ''}
        </p>
        {msg && <p className="msg">{msg}</p>}
        <button className="link" style={{ color: '#B91C1C', alignSelf: 'flex-start' }} disabled={busy || dialling} onClick={remove}
          title={dialling ? 'Wait until the call ends' : undefined}>Delete candidate</button>
      </main>

      <div className="actionbar">
        <div className="inner">
          <button className="btn danger" disabled={busy || dialling || c.stage === 'rejected'} onClick={() => decide('rejected')}>Reject</button>
          <button className="btn ghost" disabled={busy || !!active || c.is_demo} onClick={callAgain}
            title={c.is_demo ? 'Demo candidates are never called' : undefined}>Call again</button>
          <button className="btn success" disabled={busy || dialling || c.stage === 'accepted'} onClick={() => decide('accepted')}>Accept</button>
        </div>
      </div>
    </>
  )
}
