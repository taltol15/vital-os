import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { POST as contact } from "@/app/api/contact/route";
import { GET as download } from "@/app/api/v1/downloads/iso/route";
import { POST as telemetry } from "@/app/api/v1/telemetry/route";
import { POST as adminCatalog } from "@/app/api/mgmt/catalog/route";
import { memory, resetMemory } from "@/lib/memory";
import { validateContact } from "@/lib/contact";

const install = {
  install_id: "11111111-1111-4111-8111-111111111111",
  os_version: "0.2.1",
  event: "install",
  ts: "2026-10-05T12:00:00Z",
};

beforeEach(() => {
  resetMemory();
  process.env.VITAL_DATA_DRIVER = "memory";
  process.env.VITAL_RATE_LIMIT_SALT = "test-salt-value-which-is-long";
});

afterEach(() => {
  delete process.env.VITAL_DATA_DRIVER;
  delete process.env.VITAL_RATE_LIMIT_SALT;
});

function jsonRequest(url: string, body: unknown, headers?: HeadersInit) {
  return new Request(url, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

describe("telemetry route", () => {
  it("accepts the distro payload and stores no client timestamp", async () => {
    const response = await telemetry(jsonRequest("https://vital-os.org/api/v1/telemetry", install));
    expect(response.status).toBe(204);
    expect(response.headers.get("set-cookie")).toBeNull();
    const row = memory.installs.get(install.install_id);
    expect(row?.saw_install).toBe(true);
    expect(row?.os_version).toBe("0.2.1");
    expect(JSON.stringify(row)).not.toContain("2026-10-05T12:00:00Z");
  });

  it("rejects extra fields and a bad id", async () => {
    const extra = await telemetry(jsonRequest("https://vital-os.org/api/v1/telemetry", { ...install, hostname: "vital" }));
    expect(extra.status).toBe(422);
    const bad = await telemetry(jsonRequest("https://vital-os.org/api/v1/telemetry", { ...install, install_id: "not-a-uuid" }));
    expect(bad.status).toBe(422);
  });

  it("counts a package install once per machine", async () => {
    const payload = { ...install, event: "package", package_id: "gimp" };
    const first = await telemetry(jsonRequest("https://vital-os.org/api/v1/telemetry", payload));
    const second = await telemetry(jsonRequest("https://vital-os.org/api/v1/telemetry", payload));
    expect(first.status).toBe(204);
    expect(second.status).toBe(204);
    expect(memory.packages.has("gimp|11111111-1111-4111-8111-111111111111")).toBe(true);
    const noisy = await telemetry(jsonRequest("https://vital-os.org/api/v1/telemetry", { ...payload, hostname: "x" }));
    expect(noisy.status).toBe(422);
  });

  it("rate limits an install id", async () => {
    let status = 0;
    for (let index = 0; index < 9; index += 1) {
      const response = await telemetry(jsonRequest("https://vital-os.org/api/v1/telemetry", { ...install, event: "heartbeat" }));
      status = response.status;
    }
    expect(status).toBe(429);
  });
});

describe("contact", () => {
  it("rejects a bad email and a newline in the name", () => {
    expect(validateContact({ name: "Ada", email: "nope", subject: "Hi", message: "Hello there" }).ok).toBe(false);
    const named = validateContact({ name: "Ada\nLovelace", email: "ada@example.com", subject: "Hi", message: "Hello" });
    expect(named.ok).toBe(false);
  });

  it("stores a valid message and swallows the honeypot", async () => {
    const saved = await contact(jsonRequest("https://vital-os.org/api/contact", {
      name: "Ada Lovelace",
      email: "ada@example.com",
      subject: "Install",
      message: "The disk check is clear.",
      locale: "en",
    }));
    expect(saved.status).toBe(200);
    expect(memory.contacts).toHaveLength(1);
    expect(memory.contacts[0]?.email).toBe("ada@example.com");

    const bot = await contact(jsonRequest("https://vital-os.org/api/contact", {
      name: "Bot",
      email: "bot@example.com",
      subject: "Buy",
      message: "Hello",
      fax_number: "555",
    }));
    expect(bot.status).toBe(200);
    expect(memory.contacts).toHaveLength(1);
  });
});

describe("download counter", () => {
  it("redirects without a cookie", async () => {
    const response = await download();
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toContain("VitalOS-0.2.1-amd64.iso");
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(response.headers.get("set-cookie")).toBeNull();
    expect(memory.downloads).toBe(1);
  });
});

describe("admin routes", () => {
  it("refuses catalog writes without a session", async () => {
    const response = await adminCatalog(new Request("https://vital-os.org/api/mgmt/catalog", { method: "POST" }));
    expect(response.status).toBe(401);
  });
});
