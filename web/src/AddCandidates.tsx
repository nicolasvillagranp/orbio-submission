import { useState, type FormEvent } from 'react'
import Header from './Header'
import { parseCandidatesCsv, type NewCandidate, type Skipped } from './lib/csv'
import { normalizePhone } from './lib/phone'
import { supabase } from './supabase'
import { requestCall, type Board } from './useBoard'
import type { Go } from './useRoute'

type Tab = 'manual' | 'csv' | 'auto'
const SOURCES = ['Job board', 'Referral', 'Walk-in', 'Other']
const TABS: { id: Tab; label: string }[] = [
  { id: 'manual', label: 'Manual' },
  { id: 'csv', label: 'CSV upload' },
  { id: 'auto', label: 'Auto-sourcing' },
]

export default function AddCandidates({ data, email, go }: { data: Board; email: string; go: Go }) {
  const [tab, setTab] = useState<Tab>('manual')
  return (
    <>
      <Header email={email} />
      <main className="page narrow">
        <div className="titlebar">
          <h1>Add candidates</h1>
          <a href="#/">Back to board</a>
        </div>
        <div className="segmented" role="tablist">
          {TABS.map((t) => (
            <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>
          ))}
        </div>
        {tab === 'manual' && <Manual data={data} email={email} go={go} />}
        {tab === 'csv' && <Csv data={data} go={go} />}
        {tab === 'auto' && (
          <div className="sheet soon">
            <strong>Coming soon</strong>
            Automatically bring in applicants from job boards and screen them as they arrive.
          </div>
        )}
      </main>
    </>
  )
}

function Manual({ data, email, go }: { data: Board; email: string; go: Go }) {
  const [phone, setPhone] = useState('')
  const [name, setName] = useState('')
  const [source, setSource] = useState(SOURCES[0])
  const [callNow, setCallNow] = useState(true)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  const normalized = normalizePhone(phone)
  const existing = normalized ? data.candidates.find((c) => c.phone === normalized) : undefined

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!normalized) return setMsg('Enter a valid phone number, e.g. 612 345 678 or +34 612 345 678.')
    if (existing) return
    setBusy(true)
    const { data: rows, error } = await supabase.from('candidates')
      .insert({ phone: normalized, name: name.trim() || null, source: 'manual', team_note: `Source: ${source}` })
      .select('id')
    if (error) {
      setBusy(false)
      return setMsg(error.code === '23505' ? 'This number is already on the board.' : error.message)
    }
    if (callNow) {
      const err = await requestCall(rows[0].id, email)
      if (err) {
        setBusy(false)
        return setMsg(`Added, but the call couldn’t be requested: ${err}`)
      }
    }
    go({ name: 'board' })
  }

  return (
    <form className="sheet" onSubmit={submit}>
      <label>
        Phone number
        <input type="tel" inputMode="tel" autoComplete="off" required value={phone} placeholder="+34 612 345 678"
          onChange={(e) => { setPhone(e.target.value); setMsg('') }} />
        {existing && (
          <span className="msg">Already on the board: <a href={`#/c/${existing.id}`}>{existing.name || existing.phone}</a></span>
        )}
      </label>
      <label>
        Name <span className="hint">Optional. The agent asks for it anyway.</span>
        <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label>
        Source
        <select value={source} onChange={(e) => setSource(e.target.value)}>
          {SOURCES.map((s) => <option key={s}>{s}</option>)}
        </select>
      </label>
      <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
        <legend style={{ fontWeight: 600, marginBottom: 6 }}>When</legend>
        <div className="choices">
          <label className="choice"><input type="radio" name="when" checked={callNow} onChange={() => setCallNow(true)} />Call now</label>
          <label className="choice"><input type="radio" name="when" checked={!callNow} onChange={() => setCallNow(false)} />Add to queue</label>
        </div>
      </fieldset>
      {msg && <p className="msg">{msg}</p>}
      <button className="btn" type="submit" disabled={busy || !!existing}>{callNow ? 'Add and call' : 'Add to queue'}</button>
    </form>
  )
}

function Csv({ data, go }: { data: Board; go: Go }) {
  const [parsed, setParsed] = useState<{ rows: NewCandidate[]; skipped: Skipped[]; error: string } | null>(null)
  const [fileName, setFileName] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)

  async function read(file: File | undefined) {
    setMsg('')
    if (!file) return setParsed(null)
    setFileName(file.name)
    setParsed(parseCandidatesCsv(await file.text(), new Set(data.candidates.map((c) => c.phone))))
  }

  async function importRows() {
    if (!parsed?.rows.length) return
    setBusy(true)
    const { error } = await supabase.from('candidates').insert(parsed.rows.map((r) => ({
      phone: r.phone, name: r.name || null, source: 'csv', team_note: r.source_label ? `Source: ${r.source_label}` : '',
    })))
    setBusy(false)
    if (error) return setMsg(error.code === '23505' ? 'Some numbers were added meanwhile. Choose the file again.' : error.message)
    go({ name: 'board' })
  }

  return (
    <div className="sheet">
      <label>
        CSV file
        <span className="hint">Columns: <code>phone</code> (required), <code>name</code>, <code>source</code>. First line is the header.</span>
        <input type="file" accept=".csv,text/csv" onChange={(e) => read(e.target.files?.[0])} />
      </label>
      {parsed?.error && <p className="msg">{parsed.error}</p>}
      {parsed && !parsed.error && (
        <>
          <strong>{fileName}: {parsed.rows.length} to import{parsed.skipped.length ? `, ${parsed.skipped.length} skipped` : ''}</strong>
          {parsed.rows.length > 0 && (
            <div className="scrollbox">
              <table className="preview">
                <thead><tr><th>Phone</th><th>Name</th><th>Source</th></tr></thead>
                <tbody>
                  {parsed.rows.slice(0, 20).map((r) => <tr key={r.phone}><td>{r.phone}</td><td>{r.name}</td><td>{r.source_label}</td></tr>)}
                </tbody>
              </table>
              {parsed.rows.length > 20 && <p className="hint">…and {parsed.rows.length - 20} more.</p>}
            </div>
          )}
          {parsed.skipped.length > 0 && (
            <ul className="skipped">
              {parsed.skipped.map((s) => <li key={s.line}>Line {s.line}: {s.reason} <span className="hint">({s.raw})</span></li>)}
            </ul>
          )}
          {msg && <p className="msg">{msg}</p>}
          <button className="btn" onClick={importRows} disabled={busy || !parsed.rows.length}>
            Import {parsed.rows.length} candidate{parsed.rows.length === 1 ? '' : 's'} to the queue
          </button>
        </>
      )}
    </div>
  )
}
