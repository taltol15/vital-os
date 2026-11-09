import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { publishableKey, supabaseConfigured, supabaseUrl } from "@/lib/env";

export async function userClient() {
  if (!supabaseConfigured()) throw new Error("Supabase is not configured");
  const cookieStore = await cookies();
  return createServerClient(supabaseUrl() as string, publishableKey() as string, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(list) {
        try {
          for (const cookie of list) {
            cookieStore.set(cookie.name, cookie.value, cookie.options);
          }
        } catch {
          // A Server Component cannot always write cookies. Sign-in uses a server action, which can.
        }
      },
    },
  });
}
