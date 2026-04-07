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
