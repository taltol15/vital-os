import { redirect } from "next/navigation";
import { AdminFrame } from "@/components/admin-frame";
import { currentAdmin, loadReleaseRows } from "@/lib/admin-read";
import { formatBytes } from "@/lib/format";
import { previewEnabled } from "@/lib/preview";
import type { ReleaseRecord } from "@/lib/types";

export const dynamic = "force-dynamic";

function ReleaseEditor({ release, error }: { release?: ReleaseRecord; error?: string }) {
  const when = release ? release.published_at.slice(0, 16) : "";
  return (
    <form className="form" action="/api/mgmt/releases" method="post">
      {error ? <p className="banner banner-warn" role="alert">{error}</p> : null}
      {release?.id ? <input type="hidden" name="id" value={release.id} /> : null}
      <label className="field"><span>Version</span><input name="version" defaultValue={release?.version ?? ""} required /></label>
      <label className="field"><span>Published at</span><input name="published_at" type="datetime-local" defaultValue={when} required /></label>
      <label className="field"><span>Filename</span><input name="filename" defaultValue={release?.filename ?? ""} required /></label>
      <label className="field"><span>Size in bytes</span><input name="size_bytes" defaultValue={release?.size_bytes ?? ""} required /></label>
      <label className="field"><span>SHA-256</span><input name="sha256" defaultValue={release?.sha256 ?? ""} required className="mono" /></label>
      <label className="field"><span>ISO URL</span><input name="download_url" defaultValue={release?.download_url ?? ""} required /></label>
      <label className="field"><span>SHA256SUMS URL</span><input name="sums_url" defaultValue={release?.sums_url ?? ""} /></label>
      <label className="field"><span>Notes file URL</span><input name="readme_url" defaultValue={release?.readme_url ?? ""} /></label>
      <label className="field"><span>Release notes</span><textarea name="notes" defaultValue={release?.notes ?? ""} /></label>
      <label className="check"><input type="checkbox" name="recommended" defaultChecked={release?.recommended} /> Recommended</label>
      <label className="check"><input type="checkbox" name="archived" defaultChecked={release?.archived} /> Archived</label>
      <label className="check"><input type="checkbox" name="prerelease" defaultChecked={release?.prerelease} /> Prerelease</label>
      <button className="button" type="submit">{release ? "Save release" : "Add release"}</button>
    </form>
  );
}

export default async function ReleasesPage({ searchParams }: { searchParams: Promise<{ error?: string; version?: string }> }) {
  const preview = previewEnabled();
  const admin = await currentAdmin();
  if (!admin && !preview) redirect("/mgmt/login");
  const query = await searchParams;
  const releases = await loadReleaseRows();
  const editing = releases.find((release) => release.version === query.version);
  return (
    <AdminFrame current="releases" email={admin?.email} preview={preview}>
      <header className="page-head">
        <p className="eyebrow">Downloads</p>
        <h1>Releases</h1>
        <p className="lede">These rows are the downloads page. The recommended row is where the counted ISO link redirects.</p>
      </header>
      <table>
        <thead><tr><th>Version</th><th>Size</th><th>Flags</th></tr></thead>
        <tbody>
          {releases.map((release) => (
            <tr key={release.version}>
              <td><a href={`/mgmt/releases?version=${encodeURIComponent(release.version)}`}>{release.version}</a></td>
              <td>{formatBytes(release.size_bytes, "en")}</td>
              <td>{[release.recommended ? "recommended" : "", release.archived ? "archived" : ""].filter(Boolean).join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2 style={{ marginTop: "1.5rem" }}>{editing ? `Edit ${editing.version}` : "Add a release"}</h2>
      <ReleaseEditor release={editing} error={query.error} />
    </AdminFrame>
  );
}
