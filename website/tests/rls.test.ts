import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sql = readdirSync(path.join(root, "supabase/migrations"))
  .filter((name) => name.endsWith(".sql"))
  .map((name) => readFileSync(path.join(root, "supabase/migrations", name), "utf8"))
  .join("\n");

const tables = [
  "admin_allowlist",
  "catalog_items",
  "catalog_item_versions",
  "releases",
  "contact_messages",
  "installs",
  "heartbeat_days",
  "package_installs",
  "counters",
  "rate_buckets",
];

describe("row level security", () => {
  it("enables and forces RLS on every table", () => {
    for (const table of tables) {
      expect(sql).toContain(`alter table public.${table} enable row level security`);
      expect(sql).toContain(`alter table public.${table} force row level security`);
    }
  });

  it("lets anonymous clients read only the public catalog and releases", () => {
    expect(sql).toContain("create policy catalog_public_read");
    expect(sql).toContain("using (published)");
    expect(sql).toContain("create policy releases_public_read");
    expect(sql).not.toMatch(/for (insert|update|delete|all) to anon/i);
    expect(sql).toContain("revoke all on function public.record_telemetry");
    expect(sql).toContain("revoke all on function public.insert_contact");
    expect(sql).toContain("grant execute on function public.record_telemetry(uuid, text, text, text) to service_role");
    expect(sql).toContain("grant execute on function public.admin_stats(integer) to authenticated");
  });

  it("gates authenticated writes on the allowlist", () => {
    const policies = sql.match(/create policy [\s\S]*?;/g) ?? [];
    const authenticated = policies.filter((policy) => policy.includes("to authenticated"));
    expect(authenticated.length).toBeGreaterThan(5);
    for (const policy of authenticated) {
      expect(policy).toContain("public.is_admin()");
    }
  });

  it("does not grant anonymous insert on telemetry or messages", () => {
    expect(sql).not.toContain("grant insert on public.installs to anon");
    expect(sql).not.toContain("grant insert on public.contact_messages to anon");
    expect(sql).not.toContain("grant select on public.installs to anon");
    expect(sql).not.toContain("grant select on public.contact_messages to anon");
    expect(sql).toContain("372eda7e6253df3490dbe96e480e8aaf2760bf9f8b3bfedca3622bf00d313f15");
  });
});

describe("secrets stay out of the tree", () => {
  it("leaves secret env values empty in the example", () => {
    const example = readFileSync(path.join(root, ".env.example"), "utf8");
    expect(example).toContain("SUPABASE_SERVICE_ROLE_KEY=\n");
    expect(example).toContain("VITAL_CATALOG_SIGNING_KEY=\n");
    expect(example).not.toContain("BEGIN PRIVATE KEY");
    expect(example).not.toContain("service_role");
  });
});
