create table if not exists chat.workflow_state (
    chat_id             text primary key references chat.chats(id) on delete cascade,
    kind                text not null,
    state               text not null default 'active',
    config_json         jsonb not null default '{}'::jsonb,
    updated_by_user_id  text references identity.users(id) on delete set null,
    created_at          double precision not null,
    updated_at          double precision
);

create table if not exists chat.tasks (
    chat_id          text not null references chat.chats(id) on delete cascade,
    task_id          text not null,
    subject          text not null,
    description      text not null default '',
    status           text not null default 'pending',
    active_form      text,
    owner_user_id    text references identity.users(id) on delete set null,
    blocks_json      jsonb not null default '[]'::jsonb,
    blocked_by_json  jsonb not null default '[]'::jsonb,
    metadata_json    jsonb not null default '{}'::jsonb,
    created_at       double precision not null,
    updated_at       double precision,
    primary key (chat_id, task_id)
);

create index if not exists idx_chat_tasks_owner_user_id
    on chat.tasks(owner_user_id)
    where owner_user_id is not null;

grant select, insert, update, delete on chat.workflow_state to service_role;
grant select, insert, update, delete on chat.workflow_state to authenticated;
grant select, insert, update, delete on chat.tasks to service_role;
grant select, insert, update, delete on chat.tasks to authenticated;

notify pgrst, 'reload schema';
