import { liveDays } from "@/lib/rate-limit";
import { supabaseConfigured } from "@/lib/env";
import { emptyStats, previewEnabled, previewMessages, previewStats } from "@/lib/preview";
import { seedCatalog } from "@/lib/seed";
import { userClient } from "@/lib/supabase/server";
import type { CatalogItem, ContactMessage, DashboardStats, ReleaseRecord } from "@/lib/types";
import { listReleases } from "@/lib/store";

export type AdminSession = { email: string };

export async function currentAdmin(): Promise<AdminSession | null> {
  if (previewEnabled() || !supabaseConfigured()) return null;
  const supabase = await userClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) return null;
  const allow = await supabase.from("admin_allowlist").select("email").eq("user_id", data.user.id).maybeSingle();
  if (!allow.data) return null;
  return { email: allow.data.email };
}

export async function loadDashboard(): Promise<{ stats: DashboardStats; preview: boolean }> {
  if (previewEnabled()) return { stats: previewStats(), preview: true };
  if (!supabaseConfigured()) return { stats: emptyStats(), preview: false };
  const supabase = await userClient();
  const { data, error } = await supabase.rpc("admin_stats", { live_days: liveDays() });
  if (error) throw new Error(error.message);
  return { stats: normalizeStats(data), preview: false };
}

function normalizeStats(data: unknown): DashboardStats {
  const row = (data ?? {}) as Partial<DashboardStats>;
  const fallback = emptyStats();
  return {
    downloads: Number(row.downloads ?? 0),
    installs: Number(row.installs ?? 0),
    live: Number(row.live ?? 0),
    liveDays: Number(row.liveDays ?? fallback.liveDays),
    days: Array.isArray(row.days) ? row.days.map(String) : fallback.days,
    heartbeats: Array.isArray(row.heartbeats) ? row.heartbeats.map((value) => Number(value)) : fallback.heartbeats,
    versions: Array.isArray(row.versions)
      ? row.versions.map((item) => ({ os_version: String(item.os_version), count: Number(item.count) }))
      : [],
    packages: Array.isArray(row.packages)
      ? row.packages.map((item) => ({ package_id: String(item.package_id), count: Number(item.count) }))
      : [],
    unreadMessages: Number(row.unreadMessages ?? 0),
  };
}

export type AdminCatalogRow = {
  id: string;
  published: boolean;
  updated_at: string;
  document: CatalogItem;
};

export async function loadCatalog(): Promise<AdminCatalogRow[]> {
  if (previewEnabled() || !supabaseConfigured()) {
    return seedCatalog.map((row) => ({
      id: row.document.id,
      published: row.published,
      updated_at: row.updated_at,
      document: row.document,
    }));
  }
  const supabase = await userClient();
  const { data, error } = await supabase.from("catalog_items").select("id, document, published, updated_at").order("id");
  if (error) throw new Error(error.message);
  return (data ?? []) as AdminCatalogRow[];
}

export async function loadMessages(): Promise<ContactMessage[]> {
  if (previewEnabled()) return previewMessages();
  if (!supabaseConfigured()) return [];
  const supabase = await userClient();
  const { data, error } = await supabase.from("contact_messages").select("*").order("created_at", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as ContactMessage[];
}

export async function loadReleaseRows(): Promise<ReleaseRecord[]> {
  return listReleases();
}
