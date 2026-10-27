// Recruiter app: sign-in (invite-only) and the board, add-candidates and candidate screens.
import { useEffect, useState, type FormEvent } from 'react'
import type { Session } from '@supabase/supabase-js'
import AddCandidates from './AddCandidates'
import Board from './Board'
import CandidateDetail from './CandidateDetail'
import { cameFromInvite, supabase } from './supabase'
import { useBoard } from './useBoard'
import { useRoute } from './useRoute'

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [needsPassword, setNeedsPassword] = useState(cameFromInvite)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })
    const { data } = supabase.auth.onAuthStateChange((event, s) => {
      setSession(s)
      if (event === 'PASSWORD_RECOVERY') setNeedsPassword(true)
    })
    return () => data.subscription.unsubscribe()
  }, [])

  if (loading) return <main className="card">Loading…</main>
  if (!session) return <Login />
  if (needsPassword) return <SetPassword onDone={() => setNeedsPassword(false)} />
  return <Signed email={session.user.email ?? ''} />
}

function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [msg, setMsg] = useState('')

  async function signIn(e: FormEvent) {
    e.preventDefault()
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    setMsg(error ? error.message : '')
  }

  async function forgot() {
    const { error } = await supabase.auth.resetPasswordForEmail(email, { redirectTo: window.location.origin })
    setMsg(error ? error.message : 'Check your email for a reset link.')
  }

  return (
    <main className="card">
      <h1>Sazón Talent</h1>
      <form onSubmit={signIn}>
        <label>Email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
        <label>Password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <button type="submit">Sign in</button>
      </form>
      <button className="link" onClick={forgot} disabled={!email}>Forgot password?</button>
      {msg && <p className="msg">{msg}</p>}
    </main>
  )
}

function SetPassword({ onDone }: { onDone: () => void }) {
  const [password, setPassword] = useState('')
  const [msg, setMsg] = useState('')

  async function save(e: FormEvent) {
    e.preventDefault()
    const { error } = await supabase.auth.updateUser({ password })
    if (error) setMsg(error.message)
    else onDone()
  }

  return (
    <main className="card">
      <h1>Choose a password</h1>
      <form onSubmit={save}>
        <label>New password<input type="password" minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
        <button type="submit">Save and continue</button>
      </form>
      {msg && <p className="msg">{msg}</p>}
    </main>
  )
}

function Signed({ email }: { email: string }) {
  const data = useBoard()
  const [route, go] = useRoute()
  if (route.name === 'add') return <AddCandidates data={data} email={email} go={go} />
  if (route.name === 'candidate') return <CandidateDetail data={data} email={email} id={route.id} go={go} />
  return <Board data={data} email={email} go={go} />
}
