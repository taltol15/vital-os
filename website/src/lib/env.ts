export function supabaseUrl(): string | null {
  const value = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  return value || null;
}

export function publishableKey(): string | null {
  const value = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY?.trim();
  return value || null;
}

export function supabaseConfigured(): boolean {
  return Boolean(supabaseUrl() && publishableKey());
}

export function serviceConfigured(): boolean {
  return Boolean(supabaseUrl() && process.env.SUPABASE_SERVICE_ROLE_KEY?.trim());
}

export type WriteDriver = "memory" | "supabase" | "unconfigured";

export function writeDriver(): WriteDriver {
  if (process.env.VITAL_DATA_DRIVER === "memory") return "memory";
  if (serviceConfigured()) return "supabase";
  return "unconfigured";
}

export function readUsesDatabase(): boolean {
  if (process.env.VITAL_DATA_DRIVER === "memory") return false;
  return supabaseConfigured();
}
