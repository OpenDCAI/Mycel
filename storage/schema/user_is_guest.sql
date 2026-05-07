alter table identity.users
    add column if not exists is_guest boolean not null default false;

do $$
begin
    if exists (
        select 1
        from information_schema.columns
        where table_schema = 'identity'
          and table_name = 'users'
          and column_name = 'owner_profile'
    ) then
        update identity.users
           set is_guest = true
         where owner_profile = 'guest';

        alter table identity.users
            drop column owner_profile;
    end if;
end $$;

notify pgrst, 'reload schema';
