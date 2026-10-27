import { useEffect, useState } from 'react'
import { supabase } from './supabase'
import { ACTIVE_CALL, type Call, type Candidate } from './types'

export type Board = {
  candidates: Candidate[]
  calls: Call[]
  loading: boolean
  error: string
  now: Date
  activeCall: (candidateId: string) => Call | undefined
}

/** Both tables, kept live: any change from another device or the call worker reloads them. */
export function useBoard(): Board {
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [calls, setCalls] = useState<Call[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined
    async function load() {
      const [c, k] = await Promise.all([
        supabase.from('candidates').select('*').order('stage_changed_at', { ascending: false }),
        supabase.from('calls').select('*').order('created_at', { ascending: false }),
      ])
      if (c.error || k.error) setError((c.error ?? k.error)!.message)
      else {
        setCandidates(c.data as Candidate[])
        setCalls(k.data as Call[])
        setError('')
      }
      setNow(new Date())
      setLoading(false)
    }
    const reload = () => {
      clearTimeout(timer)
      timer = setTimeout(load, 300)
    }
    load()
    const channel = supabase
      .channel('board')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'candidates' }, reload)
      .on('postgres_changes', { event: '*', schema: 'public', table: 'calls' }, reload)
      .subscribe()
    const tick = setInterval(() => setNow(new Date()), 60_000)
    return () => {
      clearTimeout(timer)
      clearInterval(tick)
      supabase.removeChannel(channel)
    }
  }, [])

  const activeCall = (id: string) => calls.find((k) => k.candidate_id === id && ACTIVE_CALL.includes(k.status))
  return { candidates, calls, loading, error, now, activeCall }
}

/** Asks the laptop call worker to phone a candidate. Returns an error message, or ''. */
export async function requestCall(candidateId: string, email: string): Promise<string> {
  const { error } = await supabase.from('calls').insert({ candidate_id: candidateId, requested_by: email })
  if (!error) return ''
  return error.code === '23505' ? 'A call to this candidate is already on its way.' : error.message
}
