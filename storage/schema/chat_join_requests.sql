create table if not exists chat.join_requests (
    id                  text primary key,
    chat_id             text not null references chat.chats(id),
    requester_user_id   text not null references identity.users(id),
    state               text not null default 'pending' check (state in ('pending', 'approved', 'rejected')),
    message             text,
    decided_by_user_id  text references identity.users(id),
    decided_at          double precision,
    created_at          double precision not null,
    updated_at          double precision,
    unique (chat_id, requester_user_id)
);

grant select, insert, update, delete on chat.join_requests to service_role;
grant select, insert, update, delete on chat.join_requests to authenticated;

notify pgrst, 'reload schema';
