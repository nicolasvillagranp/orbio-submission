import { describe, expect, it } from 'vitest'
import type { Call, Candidate } from '../types'
import { kpis, outcomes, volumeByDay } from './stats'

const NOW = new Date('2026-10-26T18:00:00Z')
const H = 3_600_000

function cand(stage: Candidate['stage'], extra: Partial<Candidate> = {}): Candidate {
  return {
    id: Math.random().toString(36), phone: '+34600000001', name: null, source: 'seed', stage, decided_by: null,
    agent_status: null, summary: null, answers: {}, review_reasons: [], disqualify_reason: null, transcript: [],
    team_note: '', attempts: 0, retry_reason: null, is_demo: true,
    created_at: NOW.toISOString(), stage_changed_at: NOW.toISOString(), updated_at: NOW.toISOString(), ...extra,
  }
}

function call(status: Call['status'], answered: boolean, hoursAgo: number): Call {
  const at = new Date(NOW.getTime() - hoursAgo * H).toISOString()
  return { id: Math.random().toString(36), candidate_id: 'x', requested_by: 'a', status, answered, error: null,
    created_at: at, started_at: at, ended_at: at }
}

describe('kpis', () => {
  it('shows zeros and no percentages when empty', () => {
    expect(kpis([], [], NOW)).toEqual({ placed: 0, answeredPct: null, acceptedPct: null, waiting: 0, oldestWaitMs: null })
  })

  it('counts placed calls, ignoring requested and blocked ones', () => {
    const calls = [call('done', true, 1), call('no_answer', false, 2), call('requested', false, 0), call('blocked', false, 0),
      call('in_call', true, 0)]
    const k = kpis([], calls, NOW)
    expect(k.placed).toBe(3)
    expect(k.answeredPct).toBeCloseTo(2 / 3)
  })

  it('accepted share of screened candidates and the oldest review wait', () => {
    const cands = [cand('accepted'), cand('accepted'), cand('rejected'), cand('queue'),
      cand('revision', { stage_changed_at: new Date(NOW.getTime() - 5 * H).toISOString() }),
      cand('revision', { stage_changed_at: new Date(NOW.getTime() - 2 * H).toISOString() })]
    const k = kpis(cands, [], NOW)
    expect(k.acceptedPct).toBeCloseTo(2 / 5)
    expect(k.waiting).toBe(2)
    expect(k.oldestWaitMs).toBe(5 * H)
  })
})

describe('volumeByDay', () => {
  it('has one bucket per day for 14 days, oldest first', () => {
    const v = volumeByDay([call('done', true, 1), call('no_answer', false, 2), call('done', true, 24 * 20)], NOW)
    expect(v).toHaveLength(14)
    expect(v[13]).toMatchObject({ answered: 1, missed: 1 })
    expect(v.reduce((s, d) => s + d.answered + d.missed, 0)).toBe(2)
  })

  it('leaves out requests that were never placed', () => {
    expect(volumeByDay([call('requested', false, 0), call('blocked', false, 0)], NOW)[13]).toMatchObject({ answered: 0, missed: 0 })
  })
})

describe('outcomes', () => {
  it('splits stages and ranks rejection reasons', () => {
    const cands = [cand('accepted'), cand('revision'),
      cand('rejected', { disqualify_reason: 'no_license' }), cand('rejected', { disqualify_reason: 'no_license' }),
      cand('rejected', { disqualify_reason: 'out_of_area' }), cand('rejected', { disqualify_reason: 'declined' })]
    const o = outcomes(cands)
    expect([o.accepted, o.revision, o.rejected]).toEqual([1, 1, 4])
    expect(o.reasons[0]).toEqual({ reason: 'no_license', count: 2 })
    expect(o.reasons).toHaveLength(3)
  })
})

describe('volumeByDay across a clock change', () => {
  it('puts a late-evening call on its own day after DST ended', () => {
    // Runs in Europe/Madrid (vite.config.ts): summer time ended on 25 Oct 2026.
    const now = new Date(2026, 9, 26, 23, 50)
    const late = new Date(2026, 9, 26, 23, 30).toISOString()
    const c: Call = { id: '1', candidate_id: 'x', requested_by: 'a', status: 'done', answered: true, error: null,
      created_at: late, started_at: late, ended_at: late }
    const v = volumeByDay([c], now)
    expect(v[13].answered).toBe(1)
  })
})
