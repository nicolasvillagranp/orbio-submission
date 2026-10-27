export const pct = (n: number | null) => (n === null ? '—' : `${Math.round(n * 100)}%`)

export function ago(ms: number): string {
  const min = Math.max(0, Math.round(ms / 60_000))
  if (min < 60) return `${min} min`
  const h = Math.round(min / 60)
  return h < 24 ? `${h} h` : `${Math.round(h / 24)} d`
}

// Backend reason codes → what recruiters read.
export const REASON_LABELS: Record<string, string> = {
  no_license: 'No licence',
  license_in_progress: 'Licence in progress',
  out_of_area: 'Out of area',
  declined: 'Declined the interview',
  deletion_requested: 'Asked to be deleted',
  abusive: 'Abusive',
  location_borderline_distance: 'Lives 15–20 km away',
  start_date_far: 'Starts in more than 60 days',
  geocoder_unavailable: 'Location not checked',
  license_needs_renewal: 'Licence needs renewal',
  override_out_of_area: 'Out of area, overruled by a recruiter',
  override_no_license: 'No licence, overruled by a recruiter',
  override_license_in_progress: 'Licence in progress, overruled by a recruiter',
  human_requested: 'Asked to talk to a person',
}

export function reasonLabel(code: string): string {
  if (REASON_LABELS[code]) return REASON_LABELS[code]
  const m = code.match(/^(.+)_unresolved_after_retries$/)
  if (m) return `Unclear answer: ${m[1].replace(/_/g, ' ')}`
  const s = code.replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}
