import { pct, reasonLabel } from './lib/format'
import { outcomes, volumeByDay } from './lib/stats'
import type { Call, Candidate } from './types'

const Chevron = () => (
  <svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#5B6675" strokeWidth="2"><path d="M6 9l6 6 6-6" /></svg>
)

export default function Summary({ candidates, calls, now }: { candidates: Candidate[]; calls: Call[]; now: Date }) {
  const days = volumeByDay(calls, now)
  const placed = days.reduce((s, d) => s + d.answered + d.missed, 0)
  const answered = days.reduce((s, d) => s + d.answered, 0)
  const max = Math.max(1, ...days.map((d) => d.answered + d.missed))
  const o = outcomes(candidates)
  const screened = o.accepted + o.revision + o.rejected
  const share = (n: number) => (screened ? n / screened : null)
  const topReason = Math.max(1, ...o.reasons.map((r) => r.count))

  return (
    <section className="summary" aria-labelledby="summary-h">
      <h2 id="summary-h">Summary <span>· last 14 days</span></h2>
      <div className="panels">
        <details className="panel">
          <summary>
            <span className="t"><span>Call volume</span><span>{placed} calls · {pct(placed ? answered / placed : null)} answered</span></span>
            <Chevron />
          </summary>
          <div className="body">
            <div className="legend">
              <span><i className="sw" style={{ background: '#1F5FBF' }} />Answered</span>
              <span><i className="sw" style={{ background: '#A9C4EA' }} />No answer</span>
            </div>
            <div className="bars" role="img" aria-label={`Calls per day: ${placed} placed, ${answered} answered`}>
              {days.map((d) => (
                <div className="bar" key={d.day} title={`${new Date(d.day).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}: ${d.answered + d.missed} placed, ${d.answered} answered`}>
                  {d.answered + d.missed > 0 && <b>{d.answered + d.missed}</b>}
                  {d.missed > 0 && <i className="miss" style={{ height: `${(d.missed / max) * 120}px` }} />}
                  {d.answered > 0 && <i className="ans" style={{ height: `${(d.answered / max) * 120}px` }} />}
                </div>
              ))}
            </div>
            <div className="days" aria-hidden="true">
              {days.map((d, i) => (
                <span key={d.day}>{i % 2 === days.length % 2 ? '' : new Date(d.day).toLocaleDateString('en-GB', { day: 'numeric' })}</span>
              ))}
            </div>
          </div>
        </details>

        <details className="panel">
          <summary>
            <span className="t"><span>Outcomes</span><span>{pct(share(o.accepted))} accepted · {pct(share(o.rejected))} rejected</span></span>
            <Chevron />
          </summary>
          <div className="body">
            <div className="split" role="img" aria-label={`Accepted ${pct(share(o.accepted))}, In revision ${pct(share(o.revision))}, Rejected ${pct(share(o.rejected))}`}>
              {o.accepted > 0 && <div style={{ flex: o.accepted, background: '#15803D' }} />}
              {o.revision > 0 && <div style={{ flex: o.revision, background: '#E0A526' }} />}
              {o.rejected > 0 && <div style={{ flex: o.rejected, background: '#B91C1C' }} />}
              {screened === 0 && <div style={{ flex: 1, background: '#E9EDF2' }} />}
            </div>
            <div className="legend">
              <span><i className="sw" style={{ background: '#15803D' }} />Accepted <strong>{o.accepted}</strong></span>
              <span><i className="sw" style={{ background: '#E0A526' }} />In revision <strong>{o.revision}</strong></span>
              <span><i className="sw" style={{ background: '#B91C1C' }} />Rejected <strong>{o.rejected}</strong></span>
            </div>
            <h3 style={{ fontSize: 13, color: '#3A4552', marginTop: 6 }}>Top reasons for rejection</h3>
            {o.reasons.length === 0 && <span className="empty">No rejections yet.</span>}
            {o.reasons.map((r) => (
              <div className="reason" key={r.reason}>
                <span>{reasonLabel(r.reason)}</span>
                <div className="track"><div className="fill" style={{ width: `${(r.count / topReason) * 100}%` }} /></div>
                <span className="n">{r.count}</span>
              </div>
            ))}
          </div>
        </details>
      </div>
    </section>
  )
}
