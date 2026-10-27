import { describe, expect, it } from 'vitest'
import { normalizePhone } from './phone'

describe('normalizePhone', () => {
  it.each([
    ['612 345 678', '+34612345678'],
    ['0034612345678', '+34612345678'],
    ['+34 612-345-678', '+34612345678'],
    ['(+34) 612.345.678', '+34612345678'],
    ['+44 7700 900123', '+447700900123'],
  ])('%s → %s', (raw, want) => expect(normalizePhone(raw)).toBe(want))

  it.each(['12ab', '', '   ', '12345', '+34 61 23'])('rejects %j', (raw) => expect(normalizePhone(raw)).toBeNull())
})
