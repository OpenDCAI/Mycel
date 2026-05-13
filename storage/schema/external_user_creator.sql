alter table identity.users
    add column if not exists created_by_user_id text references identity.users(id) on delete set null;

create index if not exists idx_identity_users_created_by_user_id
    on identity.users(created_by_user_id)
    where created_by_user_id is not null;

notify pgrst, 'reload schema';
