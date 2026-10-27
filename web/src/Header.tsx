import { supabase } from './supabase'

export default function Header({ email }: { email: string }) {
  return (
    <header className="top">
      <a className="brand" href="#/">
        <span className="logo" aria-hidden="true">S</span>
        Sazón Talent
      </a>
      <span className="spacer" />
      <span className="who">{email}</span>
      <button className="link" onClick={() => supabase.auth.signOut()}>Sign out</button>
    </header>
  )
}
