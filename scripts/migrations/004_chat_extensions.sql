-- Migration 004: chat_members.pinned column + count_unread_per_chat RPC
-- Applied to production: 2026-04-07
-- Both objects already exist in DB; this file documents the applied state.

-- chat_members: pinned column (置顶标志)
ALTER TABLE chat_members ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT FALSE;

-- RPC: count unread messages per chat for a given user
CREATE OR REPLACE FUNCTION count_unread_per_chat(p_user_id text, p_chat_ids text[])
RETURNS TABLE(chat_id text, unread_count bigint)
LANGUAGE sql
STABLE SECURITY DEFINER
AS $$
  SELECT
    m.chat_id,
    COUNT(*)::bigint AS unread_count
  FROM messages m
  JOIN chat_members cm
    ON cm.chat_id = m.chat_id
   AND cm.user_id = p_user_id
  WHERE m.chat_id = ANY(p_chat_ids)
    AND m.sender_id != p_user_id
    AND m.deleted_at IS NULL
    AND (cm.last_read_at IS NULL OR m.created_at > cm.last_read_at)
  GROUP BY m.chat_id;
$$;
