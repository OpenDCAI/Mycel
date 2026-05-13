alter table chat.relationships
    add column if not exists message text;

notify pgrst, 'reload schema';
