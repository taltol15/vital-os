import type { ContactMessage, TelemetryRecord } from "@/lib/types";

type InstallRow = {
  install_id: string;
  os_version: string;
  first_seen: string;
  last_seen: string;
  saw_install: boolean;
  last_heartbeat: string | null;
};

export const memory = {
  installs: new Map<string, InstallRow>(),
  heartbeats: new Set<string>(),
  packages: new Set<string>(),
  downloads: 0,
  contacts: [] as ContactMessage[],
  rates: new Map<string, { hits: number; expires: number }>(),
  nextContactId: 1,
};

export function resetMemory(): void {
  memory.installs.clear();
  memory.heartbeats.clear();
  memory.packages.clear();
  memory.downloads = 0;
  memory.contacts = [];
  memory.rates.clear();
  memory.nextContactId = 1;
}

export function memoryConsume(hash: string, limit: number, now = Date.now()): boolean {
  const current = memory.rates.get(hash);
  if (!current || current.expires <= now) {
    memory.rates.set(hash, { hits: 1, expires: now + 60 * 60 * 1000 });
    return true;
  }
  if (current.hits >= limit) return false;
  current.hits += 1;
  return true;
}

export function memoryRecordTelemetry(record: TelemetryRecord, now = new Date()): void {
  const stamp = now.toISOString();
  const existing = memory.installs.get(record.install_id);
  const row: InstallRow = existing ?? {
    install_id: record.install_id,
    os_version: record.os_version,
    first_seen: stamp,
    last_seen: stamp,
    saw_install: false,
    last_heartbeat: null,
  };
  row.os_version = record.os_version;
  row.last_seen = stamp;
  if (record.event === "install") row.saw_install = true;
  if (record.event === "heartbeat") {
    row.last_heartbeat = stamp;
    memory.heartbeats.add(`${stamp.slice(0, 10)}|${record.install_id}`);
  }
  if (record.event === "package" && record.package_id) {
    memory.packages.add(`${record.package_id}|${record.install_id}`);
  }
  memory.installs.set(record.install_id, row);
}

export function memoryAddContact(input: Omit<ContactMessage, "id" | "created_at" | "read_at">): void {
  memory.contacts.push({
    ...input,
    id: memory.nextContactId,
    created_at: new Date().toISOString(),
    read_at: null,
  });
  memory.nextContactId += 1;
}
