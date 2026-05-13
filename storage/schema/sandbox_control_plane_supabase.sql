create schema if not exists container;

create table if not exists container.abstract_terminals (
    terminal_id text primary key,
    thread_id text not null,
    sandbox_runtime_id text not null,
    cwd text not null,
    env_delta_json text not null default '{}',
    state_version integer not null default 0,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists container.thread_terminal_pointers (
    thread_id text primary key,
    active_terminal_id text not null references container.abstract_terminals(terminal_id) on delete cascade,
    default_terminal_id text not null references container.abstract_terminals(terminal_id) on delete cascade,
    updated_at timestamptz not null default now()
);

create table if not exists container.chat_sessions (
    chat_session_id text primary key,
    thread_id text not null,
    terminal_id text not null references container.abstract_terminals(terminal_id) on delete cascade,
    sandbox_runtime_id text not null,
    runtime_id text,
    status text not null default 'active',
    idle_ttl_sec integer not null,
    max_duration_sec integer not null,
    budget_json text,
    started_at timestamptz not null,
    last_active_at timestamptz not null,
    ended_at timestamptz,
    close_reason text
);

create table if not exists container.terminal_commands (
    command_id text primary key,
    terminal_id text not null references container.abstract_terminals(terminal_id) on delete cascade,
    chat_session_id text references container.chat_sessions(chat_session_id) on delete set null,
    command_line text not null,
    cwd text not null,
    status text not null,
    stdout text not null default '',
    stderr text not null default '',
    exit_code integer,
    created_at timestamptz not null,
    updated_at timestamptz not null,
    finished_at timestamptz
);

create table if not exists container.terminal_command_chunks (
    chunk_id bigserial primary key,
    command_id text not null references container.terminal_commands(command_id) on delete cascade,
    stream text not null check (stream in ('stdout', 'stderr')),
    content text not null,
    created_at timestamptz not null
);

create index if not exists idx_container_abstract_terminals_thread_created
    on container.abstract_terminals(thread_id, created_at desc);

create index if not exists idx_container_abstract_terminals_runtime_created
    on container.abstract_terminals(sandbox_runtime_id, created_at desc);

create index if not exists idx_container_chat_sessions_thread_status
    on container.chat_sessions(thread_id, status, started_at desc);

create unique index if not exists uq_container_chat_sessions_active_terminal
    on container.chat_sessions(terminal_id)
    where status in ('active', 'idle', 'paused');

create index if not exists idx_container_terminal_commands_terminal_created
    on container.terminal_commands(terminal_id, created_at desc);

create index if not exists idx_container_terminal_command_chunks_command_order
    on container.terminal_command_chunks(command_id, chunk_id);

grant usage on schema container to service_role, authenticated, anon;
revoke all on
    container.abstract_terminals,
    container.thread_terminal_pointers,
    container.chat_sessions,
    container.terminal_commands,
    container.terminal_command_chunks
from anon, authenticated;
grant select, insert, update, delete on
    container.abstract_terminals,
    container.thread_terminal_pointers,
    container.chat_sessions,
    container.terminal_commands,
    container.terminal_command_chunks
to service_role;
grant usage, select on sequence container.terminal_command_chunks_chunk_id_seq to service_role;
