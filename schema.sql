-- MASTER FISHING - esquema inicial Supabase
-- Executar no SQL Editor do projeto Supabase.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text unique not null,
  display_name text,
  role text not null default 'user' check (role in ('admin','user')),
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.events (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  organization_name text not null,
  event_date date,
  location text,
  description text,
  logo_path text,
  status text not null default 'setup' check (status in ('setup','active','completed','archived')),
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.event_access (
  event_id uuid not null references public.events(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  can_edit boolean not null default true,
  can_export boolean not null default true,
  created_at timestamptz not null default now(),
  primary key (event_id, user_id)
);

create table if not exists public.participants (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references public.events(id) on delete cascade,
  registration_number integer not null,
  full_name text not null,
  created_at timestamptz not null default now(),
  unique(event_id, registration_number)
);

create table if not exists public.audit_log (
  id bigint generated always as identity primary key,
  event_id uuid references public.events(id) on delete set null,
  user_id uuid not null default auth.uid(),
  action text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists idx_event_access_user on public.event_access(user_id);
create index if not exists idx_participants_event on public.participants(event_id);
create index if not exists idx_audit_event on public.audit_log(event_id);

-- Criar automaticamente o perfil quando uma conta Auth é criada.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (id, email, display_name, role, active)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data ->> 'display_name', ''),
    'user',
    true
  )
  on conflict (id) do update set email = excluded.email;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure public.handle_new_user();

-- Funções auxiliares para políticas RLS.
create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select exists (
    select 1 from public.profiles p
    where p.id = (select auth.uid()) and p.role = 'admin' and p.active = true
  );
$$;

create or replace function public.has_event_access(target_event uuid)
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
  select public.is_admin() or exists (
    select 1 from public.event_access ea
    join public.profiles p on p.id = ea.user_id
    where ea.event_id = target_event
      and ea.user_id = (select auth.uid())
      and p.active = true
  );
$$;

alter table public.profiles enable row level security;
alter table public.events enable row level security;
alter table public.event_access enable row level security;
alter table public.participants enable row level security;
alter table public.audit_log enable row level security;

-- Perfis: cada utilizador consulta o próprio; Admin consulta/edita todos.
drop policy if exists "profile read own or admin" on public.profiles;
create policy "profile read own or admin" on public.profiles
for select to authenticated using (id = (select auth.uid()) or public.is_admin());

drop policy if exists "admin manage profiles" on public.profiles;
create policy "admin manage profiles" on public.profiles
for all to authenticated using (public.is_admin()) with check (public.is_admin());

-- Eventos: Admin cria e gere; utilizadores atribuídos consultam.
drop policy if exists "event read assigned" on public.events;
create policy "event read assigned" on public.events
for select to authenticated using (public.has_event_access(id));

drop policy if exists "admin manage events" on public.events;
create policy "admin manage events" on public.events
for all to authenticated using (public.is_admin()) with check (public.is_admin());

-- Acessos: Admin gere; utilizador consulta apenas as próprias atribuições.
drop policy if exists "access read own or admin" on public.event_access;
create policy "access read own or admin" on public.event_access
for select to authenticated using (user_id = (select auth.uid()) or public.is_admin());

drop policy if exists "admin manage event access" on public.event_access;
create policy "admin manage event access" on public.event_access
for all to authenticated using (public.is_admin()) with check (public.is_admin());

-- Participantes: Admin ou colaborador com edição no evento.
drop policy if exists "participants read assigned" on public.participants;
create policy "participants read assigned" on public.participants
for select to authenticated using (public.has_event_access(event_id));

drop policy if exists "participants insert assigned editors" on public.participants;
create policy "participants insert assigned editors" on public.participants
for insert to authenticated with check (
  public.is_admin() or exists (
    select 1 from public.event_access ea
    where ea.event_id = participants.event_id and ea.user_id = (select auth.uid()) and ea.can_edit
  )
);

drop policy if exists "participants update assigned editors" on public.participants;
create policy "participants update assigned editors" on public.participants
for update to authenticated using (
  public.is_admin() or exists (
    select 1 from public.event_access ea
    where ea.event_id = participants.event_id and ea.user_id = (select auth.uid()) and ea.can_edit
  )
) with check (
  public.is_admin() or exists (
    select 1 from public.event_access ea
    where ea.event_id = participants.event_id and ea.user_id = (select auth.uid()) and ea.can_edit
  )
);

drop policy if exists "participants delete admin" on public.participants;
create policy "participants delete admin" on public.participants
for delete to authenticated using (public.is_admin());

-- Auditoria: utilizadores podem registar e consultar operações dos eventos a que acedem.
drop policy if exists "audit read assigned" on public.audit_log;
create policy "audit read assigned" on public.audit_log
for select to authenticated using (event_id is null and public.is_admin() or public.has_event_access(event_id));

drop policy if exists "audit insert assigned" on public.audit_log;
create policy "audit insert assigned" on public.audit_log
for insert to authenticated with check (
  user_id = (select auth.uid()) and (event_id is null and public.is_admin() or public.has_event_access(event_id))
);

-- NOTA: após criar a primeira conta Admin no Supabase Auth, executar:
-- update public.profiles set role = 'admin' where email = 'O_TEU_EMAIL';
