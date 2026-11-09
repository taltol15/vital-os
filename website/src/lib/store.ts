import { readUsesDatabase, writeDriver } from "@/lib/env";
import { memory, memoryAddContact, memoryConsume, memoryRecordTelemetry } from "@/lib/memory";
import { rateHash } from "@/lib/rate-limit";
import { recommendedSeedRelease, seedPublishedItems, seedReleases } from "@/lib/seed";
import { publicClient } from "@/lib/supabase/public";
import { serviceClient } from "@/lib/supabase/service";
import type { ContactInput } from "@/lib/contact";
import type { CatalogItem, ReleaseRecord, TelemetryRecord } from "@/lib/types";

function byDate(a: ReleaseRecord, b: ReleaseRecord): number {
  return a.published_at < b.published_at ? 1 : a.published_at > b.published_at ? -1 : 0;
}

export async function listReleases(): Promise<ReleaseRecord[]> {
  if (!readUsesDatabase()) return [...seedReleases].sort(byDate);
  const { data, error } = await publicClient()
    .from("releases")
    .select(
      "id, version, published_at, notes, sha256, size_bytes, filename, download_url, sums_url, readme_url, recommended, archived, prerelease",
    )
    .order("published_at", { ascending: false });
  if (error) throw new Error(error.message);
  return (data ?? []) as ReleaseRecord[];
}

export async function recommendedRelease(): Promise<ReleaseRecord | null> {
  const releases = await listReleases();
  return releases.find((release) => release.recommended) ?? null;
}

export async function listPublishedCatalog(): Promise<{ item: CatalogItem; updated_at: string }[]> {
  if (!readUsesDatabase()) return seedPublishedItems();
  const { data, error } = await publicClient()
    .from("catalog_items")
    .select("document, updated_at")
    .eq("published", true);
  if (error) throw new Error(error.message);
  return (data ?? []).map((row) => ({
    item: row.document as CatalogItem,
    updated_at: String(row.updated_at),
  }));
}

export async function consumeRate(material: string, limit: number): Promise<boolean> {
  const hash = rateHash(material);
  const driver = writeDriver();
  if (driver === "memory") return memoryConsume(hash, limit);
  if (driver === "unconfigured") return false;
  const { data, error } = await serviceClient().rpc("consume_rate", {
    bucket: hash,
    max_hits: limit,
    window_seconds: 3600,
  });
  if (error) throw new Error(error.message);
  return data === true;
}

export async function recordTelemetry(record: TelemetryRecord): Promise<void> {
  const driver = writeDriver();
  if (driver === "memory") {
    memoryRecordTelemetry(record);
    return;
  }
  if (driver === "unconfigured") throw new Error("telemetry store is not configured");
  const { error } = await serviceClient().rpc("record_telemetry", {
    p_install: record.install_id,
    p_version: record.os_version,
    p_event: record.event,
    p_package: record.package_id ?? null,
  });
  if (error) throw new Error(error.message);
}

export async function incrementDownloads(): Promise<{ url: string | null; counted: boolean }> {
  const driver = writeDriver();
  if (driver === "memory") {
    memory.downloads += 1;
    return { url: recommendedSeedRelease()?.download_url ?? null, counted: true };
  }
  if (driver === "unconfigured") {
    return { url: recommendedSeedRelease()?.download_url ?? null, counted: false };
  }
  const { data, error } = await serviceClient().rpc("increment_downloads");
  if (error) throw new Error(error.message);
  return { url: typeof data === "string" && data ? data : null, counted: true };
}

export async function insertContact(input: ContactInput): Promise<void> {
  const driver = writeDriver();
  if (driver === "memory") {
    memoryAddContact(input);
    return;
  }
  if (driver === "unconfigured") throw new Error("contact store is not configured");
  const { error } = await serviceClient().rpc("insert_contact", {
    p_name: input.name,
    p_email: input.email,
    p_subject: input.subject,
    p_message: input.message,
  });
  if (error) throw new Error(error.message);
}
