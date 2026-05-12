alter table if exists agent.message_queue
    add column if not exists metadata_json jsonb not null default '{}'::jsonb;

notify pgrst, 'reload schema';
