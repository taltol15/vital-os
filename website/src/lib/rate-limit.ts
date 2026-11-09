import { createHmac } from "node:crypto";

export function rateHash(material: string, now = new Date()): string {
  const salt = process.env.VITAL_RATE_LIMIT_SALT || "vital-os-dev-rate";
  const hour = now.toISOString().slice(0, 13);
  return createHmac("sha256", salt).update(`${hour}|${material}`).digest("hex");
}

export function liveDays(): number {
  const parsed = Number(process.env.VITAL_LIVE_DAYS || "14");
  if (!Number.isFinite(parsed) || parsed < 1 || parsed > 90) return 14;
  return Math.floor(parsed);
}

export function rateSaltConfigured(): boolean {
  return Boolean(process.env.VITAL_RATE_LIMIT_SALT && process.env.VITAL_RATE_LIMIT_SALT.length >= 16);
}
