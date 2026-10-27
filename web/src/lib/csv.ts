import { normalizePhone } from './phone'

export type NewCandidate = { phone: string; name: string; source_label: string }
export type Skipped = { line: number; raw: string; reason: 'invalid phone' | 'duplicate' | 'missing phone' }

// One CSV line into fields; handles "quoted, fields" and "" escapes.
function splitLine(line: string): string[] {
  const out: string[] = []
  let cur = ''
  let quoted = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (quoted) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++ }
      else if (ch === '"') quoted = false
      else cur += ch
    } else if (ch === '"') quoted = true
    else if (ch === ',') { out.push(cur); cur = '' }
    else cur += ch
  }
  out.push(cur)
  return out.map((f) => f.trim())
}

/** Candidates from a `phone,name,source` CSV (header required, any order), skipping bad rows. */
export function parseCandidatesCsv(text: string, existing: Set<string>) {
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/)
  const header = splitLine(lines[0] ?? '').map((h) => h.toLowerCase())
  const col = { phone: header.indexOf('phone'), name: header.indexOf('name'), source: header.indexOf('source') }
  const rows: NewCandidate[] = []
  const skipped: Skipped[] = []
  if (col.phone < 0) return { rows, skipped, error: 'The first line must be a header with a "phone" column.' }

  const seen = new Set(existing)
  lines.slice(1).forEach((raw, i) => {
    if (!raw.trim()) return
    const line = i + 2 // as numbered in the file, header = line 1
    const f = splitLine(raw)
    const rawPhone = f[col.phone] ?? ''
    if (!rawPhone) return skipped.push({ line, raw, reason: 'missing phone' })
    const phone = normalizePhone(rawPhone)
    if (!phone) return skipped.push({ line, raw, reason: 'invalid phone' })
    if (seen.has(phone)) return skipped.push({ line, raw, reason: 'duplicate' })
    seen.add(phone)
    rows.push({ phone, name: col.name >= 0 ? f[col.name] ?? '' : '', source_label: col.source >= 0 ? f[col.source] ?? '' : '' })
  })
  return { rows, skipped, error: '' }
}
