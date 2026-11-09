import { clientAddress, parseTelemetry } from "@/lib/telemetry";
import { writeDriver } from "@/lib/env";
import { empty, json } from "@/lib/http";
import { consumeRate, recordTelemetry } from "@/lib/store";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return json({ error: "invalid json" }, 422);
  }
  const parsed = parseTelemetry(payload);
  if (!parsed.ok) return json({ error: parsed.error }, 422);
  if (writeDriver() === "unconfigured") return json({ error: "unavailable" }, 503);
  try {
    const addressOk = await consumeRate(`ip:${clientAddress(request)}`, 40);
    if (!addressOk) return json({ error: "rate limit exceeded" }, 429);
    const installOk = await consumeRate(`install:${parsed.record.install_id}`, 8);
    if (!installOk) return json({ error: "rate limit exceeded" }, 429);
    await recordTelemetry(parsed.record);
  } catch {
    return json({ error: "unavailable" }, 503);
  }
  return empty(204);
}
