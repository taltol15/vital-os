import type { ContactMessage, DashboardStats } from "@/lib/types";

export function previewEnabled(): boolean {
  return process.env.VITAL_PREVIEW === "1" && !process.env.VERCEL;
}

export function previewStats(): DashboardStats {
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setUTCDate(date.getUTCDate() - (6 - index));
    return date.toISOString().slice(0, 10);
  });
  return {
    downloads: 1284,
    installs: 316,
    live: 149,
    liveDays: 14,
    days,
    heartbeats: [18, 22, 19, 27, 24, 31, 28],
    versions: [
      { os_version: "0.2.1", count: 204 },
      { os_version: "0.2.0", count: 71 },
      { os_version: "0.1.1", count: 41 },
    ],
    packages: [
      { package_id: "firefox", count: 40 },
      { package_id: "gimp", count: 22 },
      { package_id: "inkscape", count: 17 },
      { package_id: "celluloid", count: 11 },
    ],
    unreadMessages: 2,
  };
}

export function previewMessages(): ContactMessage[] {
  return [
    {
      id: 1,
      name: "Noa Levi",
      email: "noa@example.com",
      subject: "Installer asked for a larger disk",
      message: "Calamares stopped before the copy and asked for 16 GiB. Writing it down so the docs mention the hypervisor field.",
      created_at: "2026-10-06T09:12:00Z",
      read_at: null,
    },
    {
      id: 2,
      name: "Itai Cohen",
      email: "itai@example.com",
      subject: "Marketplace sample banner",
      message: "The desktop still says the bundled catalog is unsigned. Is the public key baked in only after a new ISO?",
      created_at: "2026-10-06T11:40:00Z",
      read_at: null,
    },
  ];
}

export function emptyStats(): DashboardStats {
  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date();
    date.setUTCDate(date.getUTCDate() - (6 - index));
    return date.toISOString().slice(0, 10);
  });
  return {
    downloads: 0,
    installs: 0,
    live: 0,
    liveDays: 14,
    days,
    heartbeats: [0, 0, 0, 0, 0, 0, 0],
    versions: [],
    packages: [],
    unreadMessages: 0,
  };
}
