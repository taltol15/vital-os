import { createHash } from "node:crypto";

/** Canonical JSON matching marketplace/python/vital_catalog.py canonical_bytes. */
export function canonicalString(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value) || !Number.isInteger(value)) {
      throw new Error("catalog numbers must be finite integers");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalString(item)).join(",")}]`;
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const keys = Object.keys(record).sort();
    return `{${keys
      .map((key) => `${JSON.stringify(key)}:${canonicalString(record[key])}`)
      .join(",")}}`;
  }
  throw new Error("unsupported value in canonical JSON");
}

export function canonicalBytes(value: unknown): Buffer {
  return Buffer.from(canonicalString(value), "utf8");
}

export function sha256Hex(data: Buffer | string): string {
  return createHash("sha256").update(data).digest("hex");
}

export function withoutKeys<T extends Record<string, unknown>>(value: T, keys: string[]): T {
  const copy = { ...value };
  for (const key of keys) delete copy[key];
  return copy;
}

export function itemChecksum(item: Record<string, unknown>): string {
  return sha256Hex(canonicalBytes(withoutKeys(item, ["checksum", "signature"])));
}
