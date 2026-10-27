import { describe, expect, it } from 'vitest'
import { parseCandidatesCsv } from './csv'

describe('parseCandidatesCsv', () => {
  it('reads rows with BOM, CRLF and quoted commas', () => {
    const text = '\uFEFFphone,name,source\r\n612345678,"Pérez, Ana",Job board\r\n+34 611 222 333,Luis,\r\n'
    const { rows, skipped } = parseCandidatesCsv(text, new Set())
    expect(skipped).toEqual([])
    expect(rows).toEqual([
      { phone: '+34612345678', name: 'Pérez, Ana', source_label: 'Job board' },
      { phone: '+34611222333', name: 'Luis', source_label: '' },
    ])
  })

  it('accepts a header in any case and order', () => {
    const { rows } = parseCandidatesCsv('Name,PHONE\nAna,612345678\n', new Set())
    expect(rows).toEqual([{ phone: '+34612345678', name: 'Ana', source_label: '' }])
  })

  it('skips duplicates of the board and of earlier rows, and invalid phones', () => {
    const text = 'phone,name\n612345678,Ana\n611222333,Luis\n+34611222333,Luis again\nabc,Bad\n,Empty\n'
    const { rows, skipped } = parseCandidatesCsv(text, new Set(['+34612345678']))
    expect(rows.map((r) => r.phone)).toEqual(['+34611222333'])
    expect(skipped.map((s) => [s.line, s.reason])).toEqual([
      [2, 'duplicate'], [4, 'duplicate'], [5, 'invalid phone'], [6, 'missing phone'],
    ])
  })

  it('needs a phone column', () => {
    const { rows, error } = parseCandidatesCsv('name\nAna\n', new Set())
    expect(rows).toEqual([])
    expect(error).toMatch(/phone/)
  })

  it('ignores blank lines', () => {
    expect(parseCandidatesCsv('phone\n\n612345678\n\n', new Set()).rows).toHaveLength(1)
  })
})
