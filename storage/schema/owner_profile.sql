alter table identity.users
    add column if not exists owner_profile text;

notify pgrst, 'reload schema';
