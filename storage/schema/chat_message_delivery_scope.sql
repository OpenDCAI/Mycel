alter table chat.messages
  add column if not exists delivery_scope text not null default 'broadcast',
  add column if not exists addressed_to_user_ids_json jsonb not null default '[]'::jsonb;

alter table chat.messages
  drop constraint if exists messages_delivery_scope_check;

alter table chat.messages
  add constraint messages_delivery_scope_check
  check (delivery_scope in ('broadcast', 'addressed'));
