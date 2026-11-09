export type InstallMethod = "apt" | "flatpak" | "deb" | "script";

export type CatalogItem = {
  id: string;
  name: string;
  summary: string;
  description: string;
  icon: { url: string; sha256: string };
  version: string;
  category: string;
  publisher: string;
  homepage: string;
  license: string;
  install: {
    method: InstallMethod;
    package?: string;
    flatpak_id?: string;
    url?: string;
    sha256?: string;
  };
  screenshots?: { url: string; sha256: string }[];
  min_os_version: string;
  example?: boolean;
  checksum?: string;
  signature?: string;
};

export type CatalogSignature = {
  alg: "ed25519";
  key_id: string;
  value: string;
};

export type CatalogDocument = {
  format: 1;
  name: string;
  issued: string;
  items: CatalogItem[];
  signature?: CatalogSignature;
};

export type SeedItem = {
  published: boolean;
  updated_at: string;
  document: CatalogItem;
};

export type ReleaseRecord = {
  id?: number;
  version: string;
  published_at: string;
  notes: string;
  sha256: string;
  size_bytes: number;
  filename: string;
  download_url: string;
  sums_url: string | null;
  readme_url: string | null;
  recommended: boolean;
  archived: boolean;
  prerelease: boolean;
};

export type ContactMessage = {
  id: number;
  name: string;
  email: string;
  subject: string;
  message: string;
  created_at: string;
  read_at: string | null;
};

export type VersionCount = { os_version: string; count: number };
export type PackageCount = { package_id: string; count: number };

export type DashboardStats = {
  downloads: number;
  installs: number;
  live: number;
  liveDays: number;
  days: string[];
  heartbeats: number[];
  versions: VersionCount[];
  packages: PackageCount[];
  unreadMessages: number;
};

export type TelemetryRecord = {
  install_id: string;
  os_version: string;
  event: "install" | "heartbeat" | "package";
  package_id?: string;
};
