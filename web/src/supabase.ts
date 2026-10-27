import { createClient } from '@supabase/supabase-js'

// Read before the client consumes the URL hash: an invite link lands here with type=invite,
// and the invited person still has to choose a password.
export const cameFromInvite = window.location.hash.includes('type=invite')

export const supabase = createClient(
  import.meta.env.VITE_SUPABASE_URL,
  import.meta.env.VITE_SUPABASE_ANON_KEY,
)
