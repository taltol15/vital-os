import { validateContact } from "@/lib/contact";
import { writeDriver } from "@/lib/env";
import { json, readPayload, wantsJson } from "@/lib/http";
import { clientAddress } from "@/lib/telemetry";
import { consumeRate, insertContact } from "@/lib/store";
import { localePrefix } from "@/lib/format";

export const dynamic = "force-dynamic";

function finish(request: Request, locale: "en" | "he", status: "sent" | "error" | "rate" | "unavailable", errors?: Record<string, string>) {
  if (wantsJson(request)) {
    if (status === "sent") return json({ ok: true }, 200);
    if (status === "rate") return json({ error: "rate_limit" }, 429);
    if (status === "unavailable") return json({ error: "unavailable" }, 503);
    return json({ errors: errors ?? {} }, 400);
  }
  const prefix = localePrefix(locale);
  const url = new URL(`${prefix}/contact`, request.url);
  url.searchParams.set(status === "sent" ? "sent" : "error", status === "sent" ? "1" : status);
  return Response.redirect(url, 303);
}

export async function POST(request: Request): Promise<Response> {
  const fields = await readPayload(request);
  const parsed = validateContact(fields);
  const locale = fields.locale === "he" ? "he" : "en";
  if (!parsed.ok) return finish(request, locale, "error", parsed.errors);
  if (parsed.honeypot) return finish(request, locale, "sent");
  if (writeDriver() === "unconfigured") return finish(request, parsed.locale, "unavailable");
  try {
    const addressOk = await consumeRate(`contact-ip:${clientAddress(request)}`, 5);
    const emailOk = await consumeRate(`contact-email:${parsed.value.email.toLowerCase()}`, 3);
    if (!addressOk || !emailOk) return finish(request, parsed.locale, "rate");
    await insertContact(parsed.value);
  } catch {
    return finish(request, parsed.locale, "unavailable");
  }
  return finish(request, parsed.locale, "sent");
}
