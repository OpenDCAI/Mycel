alter table chat.relationships
    drop constraint if exists relationships_check;

alter table chat.relationships
    add constraint relationships_check check (user_low <> user_high);
