import { useEffect, useState } from 'react'

export type Route = { name: 'board' } | { name: 'add' } | { name: 'candidate'; id: string }
export type Go = (r: Route) => void

// Routes live in the hash (#/, #/add, #/c/<id>) so the phone's back button works without a router.
function parse(hash: string): Route {
  const m = hash.match(/^#\/c\/([\w-]+)/)
  if (m) return { name: 'candidate', id: m[1] }
  return hash.startsWith('#/add') ? { name: 'add' } : { name: 'board' }
}

export function useRoute(): [Route, Go] {
  const [route, setRoute] = useState(() => parse(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  const go: Go = (r) => {
    window.location.hash = r.name === 'candidate' ? `/c/${r.id}` : r.name === 'add' ? '/add' : '/'
    window.scrollTo(0, 0)
  }
  return [route, go]
}
