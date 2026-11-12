import catalogItems from "../../supabase/seed/catalog-items.json";
import releases from "../../supabase/seed/releases.json";
import type { CatalogItem, ReleaseRecord, SeedItem } from "@/lib/types";

export const seedReleases = releases as ReleaseRecord[];
export const seedCatalog = catalogItems as SeedItem[];

export function seedPublishedItems(): { item: CatalogItem; updated_at: string }[] {
  return seedCatalog
    .filter((row) => row.published)
    .map((row) => ({ item: row.document, updated_at: row.updated_at }));
}

export function recommendedSeedRelease(): ReleaseRecord | null {
  return seedReleases.find((release) => release.recommended) ?? seedReleases[0] ?? null;
}
