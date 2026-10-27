-- Recruiter app schema. Paste into the Supabase SQL editor; safe to run again.
-- Signed-in recruiters read everything, add candidates and call requests, and decide outcomes.
-- Everything else is written by the laptop call worker with the service-role key (bypasses RLS).

drop table if exists public.ping;

create table if not exists public.candidates (
  id uuid primary key default gen_random_uuid(),
  phone text not null unique,
  name text,
  source text not null default 'manual' check (source in ('manual', 'csv', 'seed')),
  stage text not null default 'queue' check (stage in ('queue', 'revision', 'accepted', 'rejected')),
  decided_by text,
  agent_status text,
  summary text,
  answers jsonb not null default '{}',
  review_reasons text[] not null default '{}',
  disqualify_reason text,
  transcript jsonb not null default '[]',
  team_note text not null default '',
  attempts int not null default 0,
  retry_reason text,
  is_demo boolean not null default false,
  created_at timestamptz not null default now(),
  stage_changed_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.calls (
  id uuid primary key default gen_random_uuid(),
  candidate_id uuid not null references public.candidates (id) on delete cascade,
  requested_by text not null,
  status text not null default 'requested'
    check (status in ('requested', 'dialling', 'in_call', 'done', 'no_answer', 'failed', 'blocked')),
  answered boolean not null default false,
  error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  ended_at timestamptz
);

-- One active call per candidate.
create unique index if not exists calls_one_active on public.calls (candidate_id)
  where status in ('requested', 'dialling', 'in_call');
create index if not exists calls_requested on public.calls (created_at) where status = 'requested';

create or replace function public.touch_candidate() returns trigger language plpgsql as $$
begin
  new.updated_at := now();
  if new.stage is distinct from old.stage then
    new.stage_changed_at := now();
  end if;
  return new;
end $$;

drop trigger if exists touch_candidate on public.candidates;
create trigger touch_candidate before update on public.candidates
  for each row execute function public.touch_candidate();

alter table public.candidates enable row level security;
alter table public.calls enable row level security;

drop policy if exists "team reads candidates" on public.candidates;
drop policy if exists "team adds candidates" on public.candidates;
drop policy if exists "team decides candidates" on public.candidates;
drop policy if exists "team deletes candidates" on public.candidates;
drop policy if exists "team reads calls" on public.calls;
drop policy if exists "team requests calls" on public.calls;

create policy "team reads candidates" on public.candidates for select to authenticated using (true);
create policy "team adds candidates" on public.candidates for insert to authenticated
  with check (is_demo = false and source in ('manual', 'csv'));
create policy "team decides candidates" on public.candidates for update to authenticated
  using (true) with check (true);
create policy "team deletes candidates" on public.candidates for delete to authenticated using (true);
create policy "team reads calls" on public.calls for select to authenticated using (true);
create policy "team requests calls" on public.calls for insert to authenticated
  with check (status = 'requested');

-- Recruiters may only change these columns; the worker writes the rest.
revoke update on public.candidates from authenticated;
grant update (stage, decided_by, team_note) on public.candidates to authenticated;
revoke update, delete on public.calls from authenticated;
grant delete on public.candidates to authenticated;  -- also cancels their call requests (cascade)

do $$
begin
  alter publication supabase_realtime add table public.candidates;
exception when duplicate_object then null;
end $$;
do $$
begin
  alter publication supabase_realtime add table public.calls;
exception when duplicate_object then null;
end $$;
