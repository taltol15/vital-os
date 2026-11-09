import type { TelemetryRecord } from "@/lib/types";

const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const OS_VERSION = /^[0-9A-Za-z][0-9A-Za-z._+-]{0,31}$/;
const TS = /^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.Z+-]{1,24}$/;
const PACKAGE_ID = /^[A-Za-z0-9][A-Za-z0-9._+-]{1,80}$/;
const BASE_KEYS = ["event", "install_id", "os_version", "ts"];

export type TelemetryParse =
  | { ok: true; record: TelemetryRecord }
  | { ok: false; error: string };

export function parseTelemetry(payload: unknown): TelemetryParse {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { ok: false, error: "payload must be an object" };
  }
  const record = payload as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  const event = record.event;
  const baseOk =
    typeof record.install_id === "string" &&
    UUID_V4.test(record.install_id) &&
    typeof record.os_version === "string" &&
    OS_VERSION.test(record.os_version) &&
    typeof record.ts === "string" &&
    TS.test(record.ts);

  if (event === "package") {
    const expected = [...BASE_KEYS, "package_id"].sort();
    if (keys.join(",") !== expected.join(",")) {
      return { ok: false, error: "package event must contain only install_id, os_version, event, ts, package_id" };
    }
    if (!baseOk) return fieldError(record);
    if (typeof record.package_id !== "string" || !PACKAGE_ID.test(record.package_id)) {
      return { ok: false, error: "package_id is invalid" };
    }
    return {
      ok: true,
      record: {
        install_id: record.install_id as string,
        os_version: record.os_version as string,
        event: "package",
        package_id: record.package_id,
      },
    };
  }

  if (keys.join(",") !== BASE_KEYS.join(",")) {
    return { ok: false, error: "payload must contain only install_id, os_version, event, ts" };
  }
  if (event !== "install" && event !== "heartbeat") {
    return { ok: false, error: "event must be install or heartbeat" };
  }
  if (!baseOk) return fieldError(record);
  return {
    ok: true,
    record: {
      install_id: record.install_id as string,
      os_version: record.os_version as string,
      event,
    },
  };
}

function fieldError(record: Record<string, unknown>): TelemetryParse {
  if (typeof record.install_id !== "string" || !UUID_V4.test(record.install_id)) {
    return { ok: false, error: "install_id must be a uuid v4" };
  }
  if (typeof record.os_version !== "string" || !OS_VERSION.test(record.os_version)) {
    return { ok: false, error: "os_version is invalid" };
  }
  if (typeof record.ts !== "string" || !TS.test(record.ts)) {
    return { ok: false, error: "ts is invalid" };
  }
  return { ok: false, error: "payload was not accepted" };
}

/** The client timestamp is checked and then discarded. The server stores its own time. */
export function clientAddress(request: Request): string {
  const real = request.headers.get("x-real-ip")?.trim();
  if (real) return real;
  const forwarded = request.headers.get("x-forwarded-for");
  if (forwarded) {
    const first = forwarded.split(",")[0]?.trim();
    if (first) return first;
  }
  return "unknown";
}
