import type { Call } from '../types'

/** Why the latest call to a candidate didn't happen, if it didn't. */
export function lastCallIssue(calls: Call[], candidateId: string): string | null {
  const last = calls
    .filter((c) => c.candidate_id === candidateId)
    .reduce<Call | undefined>((a, c) => (!a || c.created_at > a.created_at ? c : a), undefined)
  if (!last || (last.status !== 'blocked' && last.status !== 'failed')) return null
  return `Call ${last.status}${last.error ? `: ${last.error}` : ''}`
}

/** The phone is ringing or on the call: decisions and deleting wait until it ends. */
export const isDialling = (call: Call | undefined) => call?.status === 'dialling' || call?.status === 'in_call'
