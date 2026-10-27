import { describe, expect, it } from 'vitest'
import type { Call } from '../types'
import { isDialling, lastCallIssue } from './calls'

const call = (status: Call['status'], created_at: string, error: string | null = null): Call =>
  ({ id: created_at, candidate_id: 'c1', requested_by: 'a', status, answered: false, error, created_at, started_at: null, ended_at: null })

describe('lastCallIssue', () => {
  it('explains a blocked or failed latest call', () => {
    expect(lastCallIssue([call('blocked', '2026-10-26T10:00:00Z', '+34611 is not in CALL_ALLOWLIST')], 'c1'))
      .toBe('Call blocked: +34611 is not in CALL_ALLOWLIST')
    expect(lastCallIssue([call('failed', '2026-10-26T10:00:00Z', 'request expired (30 min old): ask again')], 'c1'))
      .toBe('Call failed: request expired (30 min old): ask again')
  })

  it('says nothing when the latest call went fine or there is none', () => {
    expect(lastCallIssue([call('failed', '2026-10-26T09:00:00Z', 'x'), call('done', '2026-10-26T10:00:00Z')], 'c1')).toBeNull()
    expect(lastCallIssue([], 'c1')).toBeNull()
    expect(lastCallIssue([call('blocked', '2026-10-26T10:00:00Z', 'x')], 'other')).toBeNull()
  })
})

describe('isDialling', () => {
  it('is true only once the worker has started the call', () => {
    expect(isDialling(undefined)).toBe(false)
    expect(isDialling(call('requested', '2026-10-26T10:00:00Z'))).toBe(false)
    expect(isDialling(call('dialling', '2026-10-26T10:00:00Z'))).toBe(true)
    expect(isDialling(call('in_call', '2026-10-26T10:00:00Z'))).toBe(true)
  })
})
