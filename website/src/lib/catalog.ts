import { canonicalBytes, canonicalString, itemChecksum, withoutKeys } from "@/lib/canonical";
import type { Signer } from "@/lib/sign";
import type { CatalogDocument, CatalogItem } from "@/lib/types";
import { validateItem } from "@/lib/validate";

const INSTALL_KEYS = ["method", "package", "flatpak_id", "url", "sha256"] as const;

export function normalizeItem(input: CatalogItem): CatalogItem {
  const install: CatalogItem["install"] = { method: input.install.method };
  for (const key of INSTALL_KEYS) {
    if (key === "method") continue;
    const value = input.install[key];
    if (typeof value === "string" && value.trim()) install[key] = value.trim();
  }
  const item: CatalogItem = {
    id: input.id.trim(),
    name: input.name.trim(),
    summary: input.summary.trim(),
    description: input.description.trim(),
    icon: { url: input.icon.url.trim(), sha256: input.icon.sha256.trim() },
    version: input.version.trim(),
    category: input.category.trim(),
    publisher: input.publisher.trim(),
    homepage: input.homepage.trim(),
    license: input.license.trim(),
    install,
    screenshots: input.screenshots ?? [],
    min_os_version: input.min_os_version.trim(),
  };
  if (input.example === true) item.example = true;
  return item;
}

export function withChecksum(item: CatalogItem): CatalogItem {
  const clean = normalizeItem(item);
  const errors = validateItem(clean);
  if (errors.length) throw new Error(errors.join("; "));
  const checksum = itemChecksum(clean as unknown as Record<string, unknown>);
  return { ...clean, checksum };
}

export function issuedStamp(values: string[]): string {
  const stamps = values
    .map((value) => {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return "";
      return date.toISOString().replace(/\.\d{3}Z$/, "Z");
    })
    .filter(Boolean)
    .sort();
  return stamps.at(-1) ?? "1970-01-01T00:00:00Z";
}

export function buildCatalog(items: CatalogItem[], issued: string, signer: Signer | null): string {
  const prepared = items.map(withChecksum).sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  const unsigned = {
    format: 1 as const,
    name: "Vital Marketplace",
    issued,
    items: prepared.map((item) => withoutKeys(item as unknown as Record<string, unknown>, ["signature"])),
  };
  const document: CatalogDocument = {
    format: 1,
    name: "Vital Marketplace",
    issued,
    items: prepared,
  };
  if (signer && prepared.length > 0) {
    document.signature = {
      alg: "ed25519",
      key_id: "vital-catalog",
      value: signer.sign(canonicalBytes(unsigned)),
    };
  }
  return canonicalString(document);
}
