import { useState } from 'react'
import CandidateCard from './CandidateCard'
import Header from './Header'
import { ago, pct } from './lib/format'
import { lastCallIssue } from './lib/calls'
import { kpis } from './lib/stats'
import Summary from './Summary'
import { STAGES, type Stage } from './types'
import type { Board as BoardData } from './useBoard'
import type { Go } from './useRoute'

const DOT: Record<Stage, string> = { queue: '#6B7785', revision: '#B45309', accepted: '#15803D', rejected: '#B91C1C' }

export default function Board({ data, email, go }: { data: BoardData; email: string; go: Go }) {
  const [tab, setTab] = useState<Stage>('revision')
  const [q, setQ] = useState('')
  const { candidates, calls, now } = data
  const k = kpis(candidates, calls, now)

  const needle = q.trim().toLowerCase()
  const shown = needle
    ? candidates.filter((c) => (c.name ?? '').toLowerCase().includes(needle) || c.phone.replace(/\s/g, '').includes(needle.replace(/\s/g, '')))
    : candidates

  return (
    <>
      <Header email={email} />
      <main className="page">
        <div className="titlebar">
          <h1>Screening board</h1>
          <div className="tools">
            <label className="search">
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></svg>
              <input type="search" placeholder="Search name or phone" aria-label="Search name or phone" value={q} onChange={(e) => setQ(e.target.value)} />
            </label>
            <a className="btn" href="#/add">
              <svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><path d="M12 5v14M5 12h14" /></svg>
              Add candidates
            </a>
          </div>
        </div>

        {data.error && <div className="banner">Couldn’t load the board: {data.error}</div>}

        <section className="kpis" aria-label="Key figures">
          <div className="kpi">
            <span className="label">Calls placed</span>
            <span className="value">{k.placed}</span>
            <span className="sub">{pct(k.answeredPct)} answered</span>
          </div>
          <div className="kpi">
            <span className="label">Accepted</span>
            <span className="value">{pct(k.acceptedPct)}</span>
            <span className="sub">of {candidates.filter((c) => c.stage !== 'queue').length} screened candidates</span>
          </div>
          <div className="kpi">
            <span className="label">Waiting for human review</span>
            <span className="value">{k.waiting}</span>
            <span className="sub">{k.oldestWaitMs === null ? 'Nothing waiting' : `Oldest: ${ago(k.oldestWaitMs)}`}</span>
          </div>
        </section>

        <div className="tabs" role="tablist" aria-label="Columns">
          {STAGES.map((s) => (
            <button key={s.id} role="tab" aria-selected={tab === s.id} onClick={() => setTab(s.id)}>
              <span>{s.label}</span>
              <span>{shown.filter((c) => c.stage === s.id).length}</span>
            </button>
          ))}
        </div>

        <div className="columns">
          {STAGES.map((s) => {
            const cards = shown.filter((c) => c.stage === s.id)
            return (
              <section key={s.id} className={`column ${tab === s.id ? 'current' : ''}`} aria-label={s.label}>
                <div className="colhead">
                  <span className="dot" style={{ background: DOT[s.id] }} />
                  <h2>{s.label}</h2>
                  <span className="count">{cards.length}</span>
                </div>
                {data.loading && <div className="empty">Loading…</div>}
                {!data.loading && cards.length === 0 && <div className="empty">{needle ? 'No matches.' : 'Nobody here.'}</div>}
                {cards.map((c) => (
                  <CandidateCard key={c.id} c={c} activeCall={data.activeCall(c.id)} issue={lastCallIssue(calls, c.id)} now={now} email={email}
                    onOpen={() => go({ name: 'candidate', id: c.id })} />
                ))}
              </section>
            )
          })}
        </div>

        <Summary candidates={candidates} calls={calls} now={now} />
      </main>
    </>
  )
}
