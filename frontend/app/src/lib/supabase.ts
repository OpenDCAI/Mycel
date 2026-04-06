/**
 * Supabase client singleton for frontend Realtime subscriptions.
 *
 * URL and anon key are injected at build time via Vite env vars:
 *   VITE_SUPABASE_URL
 *   VITE_SUPABASE_ANON_KEY
 *
 * For local dev without Supabase, both vars can be empty — the client
 * will be null and subscriptions will be skipped (SSE fallback remains).
 */

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = import.meta.env.VITE_SUPABASE_URL as string | undefined;
const anonKey = import.meta.env.VITE_SUPABASE_ANON_KEY as string | undefined;

export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null;

export type ChatMessagePayload = {
  id: string;
  chat_id: string;
  sender_id: string;
  content: string;
  content_type: string;
  message_type: string;
  signal: string | null;
  mentions: string[];
  retracted_at: string | null;
  created_at: string;
};

export type MessageReadPayload = {
  message_id: string;
  user_id: string;
  read_at: string;
};

export type RelationshipPayload = {
  id: string;
  principal_a: string;
  principal_b: string;
  state: string;
  direction: string | null;
  updated_at: string;
};
