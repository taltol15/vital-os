import { normalizeItem, withChecksum } from "@/lib/catalog";
import { supabaseConfigured } from "@/lib/env";
import { itemFromFields, releaseFromFields } from "@/lib/forms";
import { empty, hasAuthCookie, json, sameOrigin } from "@/lib/http";
import { userClientFromRequest } from "@/lib/supabase/request";
import { validateItem } from "@/lib/validate";
import type { SupabaseClient } from "@supabase/supabase-js";

export async function adminClient(request: Request): Promise<{ supabase: SupabaseClient } | Response> {
  if (!hasAuthCookie(request)) return empty(401);
  if (!sameOrigin(request)) return json({ error: "forbidden" }, 403);
  if (!supabaseConfigured()) return empty(401);
  const supabase = userClientFromRequest(request);
  const { data, error } = await supabase.auth.getUser();
  if (error || !data.user) return empty(401);
  const allow = await supabase.from("admin_allowlist").select("user_id").eq("user_id", data.user.id).maybeSingle();
  if (allow.error || !allow.data) return json({ error: "forbidden" }, 403);
  return { supabase };
}

function redirectTo(request: Request, path: string, error?: string): Response {
  const url = new URL(path, request.url);
  if (error) url.searchParams.set("error", error.slice(0, 280));
  return new Response(null, {
    status: 303,
    headers: { Location: `${url.pathname}${url.search}`, "Cache-Control": "no-store" },
  });
}

export async function saveCatalog(request: Request, fields: Record<string, string>): Promise<Response> {
  const gate = await adminClient(request);
  if (gate instanceof Response) return gate;
  const draft = itemFromFields(fields);
  const errors = validateItem(normalizeItem(draft));
  if (errors.length) return redirectTo(request, fields.id ? `/mgmt/catalog/${fields.id}` : "/mgmt/catalog/new", errors[0]);
  let stored;
  try {
    stored = withChecksum(draft);
  } catch (error) {
    const message = error instanceof Error ? error.message : "invalid item";
    return redirectTo(request, "/mgmt/catalog/new", message);
  }
  const published = fields.published === "on" || fields.published === "true";
  const { error } = await gate.supabase.from("catalog_items").upsert({
    id: stored.id,
    document: stored,
    published,
  });
  if (error) return redirectTo(request, `/mgmt/catalog/${stored.id}`, error.message);
  await gate.supabase.from("catalog_item_versions").insert({
    item_id: stored.id,
    version: stored.version,
    document: stored,
  });
  return redirectTo(request, `/mgmt/catalog/${stored.id}`);
}

export async function deleteCatalog(request: Request, fields: Record<string, string>): Promise<Response> {
  const gate = await adminClient(request);
  if (gate instanceof Response) return gate;
  if (fields.confirm !== "yes") return redirectTo(request, `/mgmt/catalog/${fields.id}`, "Type yes to delete.");
  const { error } = await gate.supabase.from("catalog_items").delete().eq("id", fields.id);
  if (error) return redirectTo(request, `/mgmt/catalog/${fields.id}`, error.message);
  return redirectTo(request, "/mgmt/catalog");
}

export async function saveRelease(request: Request, fields: Record<string, string>): Promise<Response> {
  const gate = await adminClient(request);
  if (gate instanceof Response) return gate;
  const release = releaseFromFields(fields);
  if (!/^[a-f0-9]{64}$/.test(release.sha256)) {
    return redirectTo(request, "/mgmt/releases", "SHA-256 must be 64 lowercase hex characters.");
  }
  if (!release.version || !release.filename || !release.download_url.startsWith("https://") || release.size_bytes < 0) {
    return redirectTo(request, "/mgmt/releases", "Version, filename, https download URL, and size are required.");
  }
  if (Number.isNaN(Date.parse(release.published_at))) {
    return redirectTo(request, "/mgmt/releases", "Published date is invalid.");
  }
  if (release.recommended) {
    const clear = gate.supabase.from("releases").update({ recommended: false }).eq("recommended", true);
    const { error } = release.id ? await clear.neq("id", release.id) : await clear;
    if (error) return redirectTo(request, "/mgmt/releases", error.message);
  }
  const row = {
    version: release.version,
    published_at: release.published_at,
    notes: release.notes,
    sha256: release.sha256,
    size_bytes: release.size_bytes,
    filename: release.filename,
    download_url: release.download_url,
    sums_url: release.sums_url,
    readme_url: release.readme_url,
    recommended: release.recommended,
    archived: release.archived,
    prerelease: release.prerelease,
  };
  const query = release.id
    ? gate.supabase.from("releases").update(row).eq("id", release.id)
    : gate.supabase.from("releases").insert(row);
  const { error } = await query;
  if (error) return redirectTo(request, "/mgmt/releases", error.message);
  return redirectTo(request, "/mgmt/releases");
}

export async function markMessage(request: Request, fields: Record<string, string>): Promise<Response> {
  const gate = await adminClient(request);
  if (gate instanceof Response) return gate;
  const id = Number(fields.id);
  if (!Number.isInteger(id)) return redirectTo(request, "/mgmt/messages", "Missing message.");
  const { error } = await gate.supabase
    .from("contact_messages")
    .update({ read_at: new Date().toISOString() })
    .eq("id", id);
  if (error) return redirectTo(request, "/mgmt/messages", error.message);
  return redirectTo(request, "/mgmt/messages");
}
