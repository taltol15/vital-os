import type { CatalogItem, InstallMethod, ReleaseRecord } from "@/lib/types";

const METHODS = new Set<InstallMethod>(["apt", "flatpak", "deb", "script"]);

export function checked(value: string | undefined): boolean {
  return value === "on" || value === "true" || value === "yes";
}

export function itemFromFields(fields: Record<string, string>): CatalogItem {
  const method = METHODS.has(fields.method as InstallMethod) ? (fields.method as InstallMethod) : "apt";
  const install: CatalogItem["install"] = { method };
  if (method === "apt") install.package = fields.package ?? "";
  else if (method === "flatpak") install.flatpak_id = fields.flatpak_id ?? "";
  else {
    install.url = fields.url ?? "";
    install.sha256 = (fields.artifact_sha256 ?? "").trim().toLowerCase();
  }
  const item: CatalogItem = {
    id: fields.id ?? "",
    name: fields.name ?? "",
    summary: fields.summary ?? "",
    description: fields.description ?? "",
    icon: {
      url: fields.icon_url ?? "",
      sha256: (fields.icon_sha256 ?? "").trim().toLowerCase(),
    },
    version: fields.version ?? "",
    category: fields.category ?? "",
    publisher: fields.publisher ?? "",
    homepage: fields.homepage ?? "",
    license: fields.license ?? "",
    install,
    screenshots: [],
    min_os_version: fields.min_os_version || "0.1.0",
  };
  if (checked(fields.example)) item.example = true;
  return item;
}

export function releaseFromFields(fields: Record<string, string>): ReleaseRecord {
  const size = Number(fields.size_bytes);
  return {
    id: fields.id ? Number(fields.id) : undefined,
    version: (fields.version ?? "").trim(),
    published_at: fields.published_at ? new Date(fields.published_at).toISOString() : "",
    notes: fields.notes ?? "",
    sha256: (fields.sha256 ?? "").trim().toLowerCase(),
    size_bytes: Number.isFinite(size) ? size : -1,
    filename: (fields.filename ?? "").trim(),
    download_url: (fields.download_url ?? "").trim(),
    sums_url: (fields.sums_url ?? "").trim() || null,
    readme_url: (fields.readme_url ?? "").trim() || null,
    recommended: checked(fields.recommended),
    archived: checked(fields.archived),
    prerelease: checked(fields.prerelease),
  };
}
