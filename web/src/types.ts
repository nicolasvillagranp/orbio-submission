export type Stage = 'queue' | 'revision' | 'accepted' | 'rejected'
export type CallStatus = 'requested' | 'dialling' | 'in_call' | 'done' | 'no_answer' | 'failed' | 'blocked'

export type Answer = { value: unknown; flagged: boolean; note: string | null }
export type Turn = { role: 'agent' | 'candidate' | 'system'; text: string; at?: string }

export type Candidate = {
  id: string
  phone: string
  name: string | null
  source: 'manual' | 'csv' | 'seed'
  stage: Stage
  decided_by: string | null
  agent_status: string | null
  summary: string | null
  answers: Record<string, Answer>
  review_reasons: string[]
  disqualify_reason: string | null
  transcript: Turn[]
  team_note: string
  attempts: number
  retry_reason: string | null
  is_demo: boolean
  created_at: string
  stage_changed_at: string
  updated_at: string
}

export type Call = {
  id: string
  candidate_id: string
  requested_by: string
  status: CallStatus
  answered: boolean
  error: string | null
  created_at: string
  started_at: string | null
  ended_at: string | null
}

export const STAGES: { id: Stage; label: string }[] = [
  { id: 'queue', label: 'Queue' },
  { id: 'revision', label: 'In revision' },
  { id: 'accepted', label: 'Accepted' },
  { id: 'rejected', label: 'Rejected' },
]

export const ACTIVE_CALL: CallStatus[] = ['requested', 'dialling', 'in_call']
