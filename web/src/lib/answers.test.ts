import { describe, expect, it } from 'vitest'
import type { Candidate } from '../types'
import { cardNote, cardTags, describeAnswer } from './answers'

const a = (value: unknown, flagged = false) => ({ value, flagged, note: null })

function cand(extra: Partial<Candidate>): Candidate {
  return {
    id: '1', phone: '+34600000001', name: 'Ana', source: 'manual', stage: 'queue', decided_by: null, agent_status: null,
    summary: null, answers: {}, review_reasons: [], disqualify_reason: null, transcript: [], team_note: '', attempts: 0,
    retry_reason: null, is_demo: false, created_at: '', stage_changed_at: '', updated_at: '', ...extra,
  }
}

describe('describeAnswer', () => {
  it.each([
    ['has_license', 'yes', 'Yes'],
    ['has_license', 'expired', 'Expired, renewing'],
    ['has_license', 'in_progress', 'Still getting it'],
    ['availability', ['full_time', 'weekends'], 'Full-time, weekends'],
    ['schedule', ['morning', 'evening'], 'Mornings, evenings'],
    ['experience_years', 0, 'None'],
    ['experience_years', 1, '1 yr'],
    ['experience_years', 3, '3 yrs'],
    ['experience_years', 0.5, 'A few months'],
    ['platforms', [], 'None'],
    ['platforms', ['Glovo', 'Uber Eats'], 'Glovo, Uber Eats'],
    ['start_date', '2026-11-02', 'Mon 2 Nov'],
    ['full_name', 'Ana López', 'Ana López'],
    ['experience_years', null, '—'],
  ])('%s %j → %s', (field, value, want) => expect(describeAnswer(field, a(value))).toBe(want))

  it('shows the place and distance for a location', () => {
    const loc = { status: 'ok', place: 'Leganés, Madrid', restaurant: 'Getafe, Madrid', distance_km: 17.4 }
    expect(describeAnswer('location', a(loc))).toBe('Leganés, Madrid · 17 km')
  })
})

describe('cardTags', () => {
  it('summarises licence, place and experience for screened candidates', () => {
    const c = cand({
      stage: 'accepted',
      answers: {
        has_license: a('yes'),
        location: a({ place: 'Leganés, Madrid', distance_km: 6.4 }),
        experience_years: a(3),
        platforms: a(['Glovo']),
      },
    })
    expect(cardTags(c)).toEqual(['Licence ✓', 'Leganés · 6 km', '3 yrs · Glovo'])
  })

  it('shows retries and the source in the queue', () => {
    expect(cardTags(cand({ attempts: 2, retry_reason: 'no_answer', source: 'csv' }))).toEqual(['No answer ×2', 'CSV import'])
    expect(cardTags(cand({ attempts: 1, retry_reason: 'hung_up' }))).toEqual(['Hung up ×1', 'Added by hand'])
  })
})

describe('cardNote', () => {
  it('explains revision and rejection', () => {
    expect(cardNote(cand({ stage: 'revision', review_reasons: ['location_borderline_distance', 'start_date_far'] })))
      .toBe('Lives 15–20 km away · Starts in more than 60 days')
    expect(cardNote(cand({ stage: 'rejected', disqualify_reason: 'no_license' }))).toBe('No licence')
    expect(cardNote(cand({ stage: 'accepted' }))).toBe('')
  })
})
