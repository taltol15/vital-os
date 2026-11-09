import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { publishableKey, supabaseUrl } from "@/lib/env";

export function publicClient(): SupabaseClient {
  const url = supabaseUrl();
  const key = publishableKey();
  if (!url || !key) throw new Error("Supabase is not configured");
  return createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
