// Phone numbers are stored in E.164 (+34612345678). Spanish numbers may be typed without the prefix.
export function normalizePhone(raw: string): string | null {
  let s = raw.replace(/[\s\-.()]/g, '')
  if (s.startsWith('00')) s = '+' + s.slice(2)
  if (/^[6789]\d{8}$/.test(s)) s = '+34' + s
  return /^\+\d{8,15}$/.test(s) ? s : null
}
