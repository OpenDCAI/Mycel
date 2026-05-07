create extension if not exists pgcrypto;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'anon') then
    create role anon nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'authenticated') then
    create role authenticated nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'service_role') then
    create role service_role nologin bypassrls;
  end if;
end
$$;

grant anon, authenticated, service_role to postgres;

create schema if not exists identity;
create schema if not exists chat;
create schema if not exists agent;
create schema if not exists container;
create schema if not exists library;

create sequence if not exists identity.mycel_id_seq start with 100000;

create table if not exists identity.users (
  id text primary key,
  type text not null,
  display_name text not null,
  owner_user_id text,
  agent_config_id text,
  next_thread_seq integer not null default 0,
  avatar text,
  email text unique,
  mycel_id integer unique,
  created_by_user_id text,
  owner_profile text,
  created_at double precision not null,
  updated_at double precision,
  check (type in ('human', 'agent', 'external')),
  check (owner_profile is null or owner_profile in ('full', 'guest'))
);

create table if not exists identity.invite_codes (
  code text primary key,
  max_uses integer,
  used_count integer not null default 0,
  used_by_auth_user_ids_json jsonb not null default '[]'::jsonb,
  expires_at double precision,
  created_at double precision not null default extract(epoch from now())
);

create table if not exists identity.user_settings (
  user_id text primary key,
  default_workspace text,
  recent_workspaces_json jsonb not null default '[]'::jsonb,
  default_model text,
  models_config_json jsonb,
  account_resource_limits_json jsonb,
  created_at double precision not null default extract(epoch from now()),
  updated_at double precision
);

create or replace function identity.next_mycel_id()
returns integer
language sql
as $$
  select nextval('identity.mycel_id_seq')::integer;
$$;

create or replace function identity.increment_user_thread_seq(p_user_id text)
returns integer
language plpgsql
as $$
declare
  next_seq integer;
begin
  update identity.users
  set next_thread_seq = next_thread_seq + 1,
      updated_at = extract(epoch from now())
  where id = p_user_id
  returning next_thread_seq into next_seq;
  if next_seq is null then
    raise exception 'user not found: %', p_user_id;
  end if;
  return next_seq;
end;
$$;

create table if not exists chat.chats (
  id text primary key,
  type text not null,
  title text,
  status text not null default 'active',
  created_by_user_id text not null,
  next_message_seq bigint not null default 0,
  created_at double precision not null,
  updated_at double precision
);

create table if not exists chat.chat_members (
  chat_id text not null references chat.chats(id) on delete cascade,
  user_id text not null,
  role text not null default 'member',
  joined_at double precision not null,
  last_read_seq bigint not null default 0,
  muted boolean not null default false,
  mute_until text,
  version integer not null default 0,
  primary key (chat_id, user_id)
);

create table if not exists chat.messages (
  id text primary key,
  chat_id text not null references chat.chats(id) on delete cascade,
  seq bigint not null,
  sender_user_id text not null,
  content text not null,
  content_type text not null default 'text/plain',
  message_type text not null default 'text',
  signal text,
  mentions_json jsonb not null default '[]'::jsonb,
  delivery_scope text not null default 'broadcast',
  addressed_to_user_ids_json jsonb not null default '[]'::jsonb,
  reply_to_message_id text,
  ai_metadata_json jsonb not null default '{}'::jsonb,
  deleted_for jsonb not null default '[]'::jsonb,
  created_at double precision not null,
  delivered_at double precision,
  edited_at double precision,
  retracted_at double precision,
  deleted_at double precision,
  unique (chat_id, seq),
  check (delivery_scope in ('broadcast', 'addressed'))
);

create table if not exists chat.contacts (
  source_user_id text not null,
  target_user_id text not null,
  kind text not null default 'normal',
  state text not null default 'active',
  alias text,
  note text,
  pinned boolean not null default false,
  muted boolean not null default false,
  archived boolean not null default false,
  blocked boolean not null default false,
  snapshot_json jsonb not null default '{}'::jsonb,
  version integer not null default 0,
  created_at double precision not null,
  updated_at double precision,
  primary key (source_user_id, target_user_id)
);

create table if not exists chat.relationships (
  user_low text not null,
  user_high text not null,
  kind text not null default 'hire_visit',
  state text not null default 'pending',
  initiator_user_id text,
  message text,
  version integer not null default 0,
  created_at double precision not null,
  updated_at double precision,
  primary key (user_low, user_high, kind),
  check (user_low <> user_high)
);

create table if not exists chat.join_requests (
  id text primary key,
  chat_id text not null references chat.chats(id) on delete cascade,
  requester_user_id text not null,
  state text not null default 'pending',
  message text,
  decided_by_user_id text,
  decided_at double precision,
  created_at double precision not null,
  updated_at double precision,
  unique (chat_id, requester_user_id)
);

create table if not exists chat.workflow_state (
  chat_id text primary key references chat.chats(id) on delete cascade,
  kind text not null,
  state text not null default 'active',
  config_json jsonb not null default '{}'::jsonb,
  updated_by_user_id text,
  created_at double precision not null,
  updated_at double precision
);

create table if not exists chat.tasks (
  chat_id text not null references chat.chats(id) on delete cascade,
  task_id text not null,
  subject text not null default '',
  description text not null default '',
  status text not null default 'pending',
  active_form text,
  owner_user_id text,
  blocks_json jsonb not null default '[]'::jsonb,
  blocked_by_json jsonb not null default '[]'::jsonb,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at double precision not null,
  updated_at double precision,
  primary key (chat_id, task_id)
);

create table if not exists chat.workflow_events (
  chat_id text not null references chat.chats(id) on delete cascade,
  event_id text not null,
  kind text not null,
  state text not null default 'open',
  resource_refs_json jsonb not null default '[]'::jsonb,
  requested_by_user_id text,
  decision_states_json jsonb not null default '{}'::jsonb,
  rationales_json jsonb not null default '{}'::jsonb,
  final_state_json jsonb not null default '{}'::jsonb,
  metadata_json jsonb not null default '{}'::jsonb,
  created_at double precision not null,
  updated_at double precision,
  settled_at double precision,
  primary key (chat_id, event_id)
);

create or replace function chat.increment_chat_message_seq(p_chat_id text)
returns bigint
language plpgsql
as $$
declare
  next_seq bigint;
begin
  update chat.chats
  set next_message_seq = next_message_seq + 1,
      updated_at = extract(epoch from now())
  where id = p_chat_id
  returning next_message_seq into next_seq;
  if next_seq is null then
    raise exception 'chat not found: %', p_chat_id;
  end if;
  return next_seq;
end;
$$;

create table if not exists agent.message_queue (
  id bigserial primary key,
  thread_id text not null,
  content text not null,
  notification_type text not null default 'steer',
  source text,
  sender_user_id text,
  sender_name text,
  created_at timestamptz not null default now()
);

create table if not exists agent.threads (
  id text primary key,
  agent_user_id text not null,
  owner_user_id text not null,
  current_workspace_id text not null,
  sandbox_type text not null,
  model text,
  cwd text,
  status text not null default 'active',
  run_status text,
  is_main boolean not null default false,
  branch_index integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz,
  last_active_at timestamptz
);

create table if not exists agent.agent_configs (
  id text primary key,
  agent_user_id text,
  owner_user_id text,
  name text,
  description text,
  status text,
  version text,
  resolved_config_json jsonb not null default '{}'::jsonb,
  created_at double precision not null default extract(epoch from now()),
  updated_at double precision
);

create table if not exists container.sandbox_recipes (
  owner_user_id text not null,
  recipe_id text not null,
  kind text not null,
  provider_type text not null,
  data_json jsonb not null default '{}'::jsonb,
  created_at double precision not null default extract(epoch from now()),
  updated_at double precision,
  primary key (owner_user_id, recipe_id)
);

grant usage on schema identity, chat, agent, container, library to anon, authenticated, service_role;
grant all privileges on all tables in schema identity, chat, agent, container, library to service_role;
grant select, insert, update, delete on all tables in schema identity, chat, agent, container, library to authenticated;
grant select on all tables in schema identity, chat, agent, container, library to anon;
grant usage, select on all sequences in schema identity, chat, agent, container, library to service_role, authenticated, anon;
grant execute on all functions in schema identity, chat to service_role, authenticated, anon;

notify pgrst, 'reload schema';
