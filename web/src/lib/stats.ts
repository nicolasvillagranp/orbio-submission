import type { Call, Candidate } from '../types'

const dayKey = (d: Date) => `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
const placedCall = (c: Call) => c.status !== 'requested' && c.status !== 'blocked'

export function kpis(cands: Candidate[], calls: Call[], now: Date) {
  const placed = calls.filter(placedCall)
  const screened = cands.filter((c) => c.stage !== 'queue')
  const waiting = cands.filter((c) => c.stage === 'revision')
  const oldest = Math.min(...waiting.map((c) => new Date(c.stage_changed_at).getTime()))
  return {
    placed: placed.length,
    answeredPct: placed.length ? placed.filter((c) => c.answered).length / placed.length : null,
    acceptedPct: screened.length ? screened.filter((c) => c.stage === 'accepted').length / screened.length : null,
    waiting: waiting.length,
    oldestWaitMs: waiting.length ? now.getTime() - oldest : null,
  }
}

/** Calls per local day for the last `days` days, oldest first. */
export function volumeByDay(calls: Call[], now: Date, days = 14) {
  const start = new Date(now)
  start.setHours(0, 0, 0, 0)
  start.setDate(start.getDate() - (days - 1))
  const buckets = Array.from({ length: days }, (_, i) => {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    return { day: d.toISOString(), answered: 0, missed: 0 }
  })
  // Bucket by local calendar day, not 24-hour slices: days are 23 or 25 h long around clock changes.
  const index = new Map(buckets.map((b, i) => [dayKey(new Date(b.day)), i]))
  for (const c of calls.filter(placedCall)) {
    const i = index.get(dayKey(new Date(c.created_at)))
    if (i === undefined) continue
    if (c.answered) buckets[i].answered++
    else buckets[i].missed++
  }
  return buckets
}

export function outcomes(cands: Candidate[]) {
  const count = (s: Candidate['stage']) => cands.filter((c) => c.stage === s).length
  const reasons = new Map<string, number>()
  for (const c of cands) {
    if (c.stage === 'rejected' && c.disqualify_reason) reasons.set(c.disqualify_reason, (reasons.get(c.disqualify_reason) ?? 0) + 1)
  }
  return {
    accepted: count('accepted'),
    revision: count('revision'),
    rejected: count('rejected'),
    reasons: [...reasons].map(([reason, n]) => ({ reason, count: n })).sort((a, b) => b.count - a.count).slice(0, 4),
  }
}
