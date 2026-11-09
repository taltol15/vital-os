import type { CatalogItem } from "@/lib/types";

const SHA256 = /^[a-f0-9]{64}$/;
const ITEM_ID = /^[A-Za-z0-9][A-Za-z0-9._+-]{1,80}$/;
const APT = /^[a-z0-9][a-z0-9+.-]{0,80}$/;
const FLATPAK = /^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*)+$/;
const METHODS = new Set(["apt", "flatpak", "deb", "script"]);

const ITEM_KEYS = new Set([
  "id",
  "name",
  "summary",
  "description",
  "icon",
  "version",
  "category",
  "publisher",
  "homepage",
  "license",
  "install",
  "screenshots",
  "min_os_version",
  "example",
  "checksum",
  "signature",
]);

function text(value: unknown, key: string, max: number, errors: string[]) {
  if (typeof value !== "string" || !value.trim()) {
    errors.push(`${key} is required`);
    return;
  }
  if (value.length > max) errors.push(`${key} is longer than ${max} characters`);
}

export function validateItem(item: unknown): string[] {
  const errors: string[] = [];
  if (!item || typeof item !== "object" || Array.isArray(item)) return ["item must be an object"];
  const record = item as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    if (!ITEM_KEYS.has(key)) errors.push(`unknown field ${key}`);
  }
  if (typeof record.id !== "string" || !ITEM_ID.test(record.id)) {
    errors.push("id must match ^[A-Za-z0-9][A-Za-z0-9._+-]{1,80}$");
  }
  text(record.name, "name", 80, errors);
  text(record.summary, "summary", 160, errors);
  text(record.description, "description", 8000, errors);
  text(record.version, "version", 64, errors);
  text(record.category, "category", 40, errors);
  text(record.publisher, "publisher", 80, errors);
  text(record.homepage, "homepage", 2000, errors);
  text(record.license, "license", 80, errors);
  text(record.min_os_version, "min_os_version", 64, errors);

  const icon = record.icon;
  if (!icon || typeof icon !== "object" || Array.isArray(icon)) {
    errors.push("icon is required");
  } else {
    const iconRecord = icon as Record<string, unknown>;
    if (typeof iconRecord.url !== "string" || !iconRecord.url) errors.push("icon.url is required");
    if (typeof iconRecord.sha256 !== "string" || !SHA256.test(iconRecord.sha256)) {
      errors.push("icon.sha256 must be 64 lowercase hex characters");
    }
  }

  const install = record.install;
  if (!install || typeof install !== "object" || Array.isArray(install)) {
    errors.push("install is required");
  } else {
    const row = install as Record<string, unknown>;
    const method = row.method;
    if (typeof method !== "string" || !METHODS.has(method)) {
      errors.push("install.method must be apt, flatpak, deb, or script");
    } else if (method === "apt") {
      if (typeof row.package !== "string" || !APT.test(row.package)) errors.push("apt package name is invalid");
    } else if (method === "flatpak") {
      if (typeof row.flatpak_id !== "string" || !FLATPAK.test(row.flatpak_id)) errors.push("flatpak_id is invalid");
    } else {
      const url = row.url;
      if (typeof url !== "string" || !(url.startsWith("https://") || url.startsWith("bundled://"))) {
        errors.push(`${method} url must be https or bundled`);
      }
      if (typeof row.sha256 !== "string" || !SHA256.test(row.sha256)) {
        errors.push(`${method} sha256 must be 64 lowercase hex characters`);
      }
    }
  }

  if (record.screenshots !== undefined) {
    if (!Array.isArray(record.screenshots)) errors.push("screenshots must be a list");
    else {
      record.screenshots.forEach((shot, index) => {
        if (!shot || typeof shot !== "object") {
          errors.push(`screenshots[${index}] must be an object`);
          return;
        }
        const row = shot as Record<string, unknown>;
        if (typeof row.url !== "string" || !row.url) errors.push(`screenshots[${index}].url is required`);
        if (typeof row.sha256 !== "string" || !SHA256.test(row.sha256)) {
          errors.push(`screenshots[${index}].sha256 is invalid`);
        }
      });
    }
  }

  if ("example" in record && typeof record.example !== "boolean") errors.push("example must be a boolean");
  if ("checksum" in record && (typeof record.checksum !== "string" || !SHA256.test(record.checksum))) {
    errors.push("checksum must be a sha256");
  }
  return errors;
}

export function validateCatalogDocument(catalog: unknown): string[] {
  if (!catalog || typeof catalog !== "object" || Array.isArray(catalog)) return ["catalog must be an object"];
  const record = catalog as Record<string, unknown>;
  const errors: string[] = [];
  if (record.format !== 1) errors.push("format must be 1");
  if (typeof record.name !== "string" || !record.name.trim()) errors.push("name is required");
  if (typeof record.issued !== "string" || record.issued.trim().length < 4) errors.push("issued is required");
  if (!Array.isArray(record.items) || record.items.length === 0) {
    errors.push("items must be a non-empty list");
    return errors;
  }
  const seen = new Set<string>();
  for (const item of record.items) {
    errors.push(...validateItem(item));
    if (item && typeof item === "object" && typeof (item as CatalogItem).id === "string") {
      const id = (item as CatalogItem).id;
      if (seen.has(id)) errors.push(`duplicate id ${id}`);
      seen.add(id);
    }
  }
  const signature = record.signature;
  if (signature !== undefined) {
    if (!signature || typeof signature !== "object" || Array.isArray(signature)) {
      errors.push("signature.alg must be ed25519");
    } else {
      const sig = signature as Record<string, unknown>;
      if (sig.alg !== "ed25519") errors.push("signature.alg must be ed25519");
      if (typeof sig.value !== "string" || !sig.value) errors.push("signature.value is required");
    }
  }
  return errors;
}
