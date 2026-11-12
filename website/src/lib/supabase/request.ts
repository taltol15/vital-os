import { createServerClient, type CookieOptions } from "@supabase/ssr";
import { publishableKey, supabaseConfigured, supabaseUrl } from "@/lib/env";

function parseCookie(header: string): { name: string; value: string }[] {
  if (!header) return [];
  const cookies: { name: string; value: string }[] = [];
  for (const part of header.split(";")) {
    const index = part.indexOf("=");
    if (index === -1) continue;
    const name = part.slice(0, index).trim();
    if (!name) continue;
    cookies.push({ name, value: decodeURIComponent(part.slice(index + 1).trim()) });
  }
  return cookies;
}

export function userClientFromRequest(request: Request) {
  if (!supabaseConfigured()) throw new Error("Supabase is not configured");
  const url = supabaseUrl() as string;
  const key = publishableKey() as string;
  const cookies = parseCookie(request.headers.get("cookie") ?? "");
  return createServerClient(url, key, {
    cookies: {
      getAll() {
        return cookies;
      },
      setAll(cookies: { name: string; value: string; options: CookieOptions }[]) {
        void cookies;
      },
    },
  });
}
