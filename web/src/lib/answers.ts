import type { Answer, Candidate } from '../types'
import { reasonLabel } from './format'

// Screening fields in the order the agent asks them, with recruiter-facing labels.
export const FIELDS: { id: string; label: string }[] = [
  { id: 'full_name', label: 'Name' },
  { id: 'has_license', label: 'Driving licence' },
  { id: 'location', label: 'Location' },
  { id: 'availability', label: 'Availability' },
  { id: 'schedule', label: 'Schedule' },
  { id: 'experience_years', label: 'Experience' },
  { id: 'platforms', label: 'Platforms' },
  { id: 'start_date', label: 'Start date' },
]

const WORDS: Record<string, string> = {
  yes: 'Yes', no: 'No', expired: 'Expired, renewing', in_progress: 'Still getting it',
  full_time: 'Full-time', part_time: 'Part-time', weekends: 'weekends',
  morning: 'Mornings', afternoon: 'Afternoons', evening: 'Evenings', flexible: 'Flexible',
}

type Place = { place?: string; distance_km?: number | null }

function list(values: string[]): string {
  const words = values.map((v) => WORDS[v] ?? v)
  return words.map((w, i) => (i === 0 ? w.charAt(0).toUpperCase() + w.slice(1) : w.toLowerCase())).join(', ')
}

export function describeAnswer(field: string, answer: Answer | undefined): string {
  const v = answer?.value
  if (v === null || v === undefined || v === '') return '—'
  switch (field) {
    case 'location': {
      const p = v as Place
      return p.place ? `${p.place}${p.distance_km != null ? ` · ${Math.round(p.distance_km)} km` : ''}` : '—'
    }
    case 'availability':
    case 'schedule':
      return Array.isArray(v) && v.length ? list(v as string[]) : '—'
    case 'platforms':
      return Array.isArray(v) && v.length ? (v as string[]).join(', ') : 'None'
    case 'experience_years': {
      const n = Number(v)
      if (n === 0) return 'None'
      if (n < 1) return 'A few months'
      return `${n} ${n === 1 ? 'yr' : 'yrs'}`
    }
    case 'start_date': {
      const d = new Date(`${v}T12:00:00`)
      return Number.isNaN(d.getTime()) ? String(v)
        : d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short' }).replace(',', '')
    }
    default:
      return typeof v === 'string' ? WORDS[v] ?? v : String(v)
  }
}

const SOURCE: Record<Candidate['source'], string> = { csv: 'CSV import', manual: 'Added by hand', seed: '' }
const RETRY: Record<string, string> = { no_answer: 'No answer', hung_up: 'Hung up', failed: 'Call failed' }

/** Up to three short facts for a board card. */
export function cardTags(c: Candidate): string[] {
  if (c.stage === 'queue') {
    return [c.retry_reason ? `${RETRY[c.retry_reason] ?? c.retry_reason} ×${c.attempts}` : '', SOURCE[c.source]].filter(Boolean)
  }
  const tags: string[] = []
  const lic = c.answers.has_license?.value
  if (lic === 'yes') tags.push('Licence ✓')
  else if (lic === 'expired') tags.push('Licence renewing')
  const p = c.answers.location?.value as Place | undefined
  if (p?.place) tags.push(`${p.place.split(',')[0]}${p.distance_km != null ? ` · ${Math.round(p.distance_km)} km` : ''}`)
  const yrs = c.answers.experience_years?.value
  if (yrs !== undefined && yrs !== null) {
    const plats = (c.answers.platforms?.value as string[] | undefined) ?? []
    tags.push([describeAnswer('experience_years', c.answers.experience_years), plats[0]].filter(Boolean).join(' · '))
  }
  return tags.slice(0, 3)
}

/** Why a card sits in its column, when that needs saying. */
export function cardNote(c: Candidate): string {
  if (c.stage === 'revision') return c.review_reasons.map(reasonLabel).join(' · ')
  if (c.stage === 'rejected') return c.disqualify_reason ? reasonLabel(c.disqualify_reason) : ''
  return ''
}
