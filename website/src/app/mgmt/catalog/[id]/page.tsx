import { notFound, redirect } from "next/navigation";
import { AdminFrame } from "@/components/admin-frame";
import { CatalogForm } from "@/components/catalog-form";
import { currentAdmin, loadCatalog } from "@/lib/admin-read";
import { supabaseConfigured } from "@/lib/env";
import { previewEnabled } from "@/lib/preview";
import { userClient } from "@/lib/supabase/server";

export const dynamic = "force-dynamic";

export default async function EditCatalogItem({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ error?: string }>;
}) {
  const { id } = await params;
  const query = await searchParams;
  const preview = previewEnabled();
  const admin = await currentAdmin();
  if (!admin && !preview) redirect("/mgmt/login");
  const rows = await loadCatalog();
  const row = rows.find((item) => item.id === id);
  if (!row) notFound();
  let versions: { id: number; version: string; created_at: string }[] = [];
  if (admin && supabaseConfigured()) {
    const supabase = await userClient();
    const history = await supabase
      .from("catalog_item_versions")
      .select("id, version, created_at")
      .eq("item_id", id)
      .order("created_at", { ascending: false });
    versions = (history.data ?? []) as typeof versions;
  }
  return (
    <AdminFrame current="catalog" email={admin?.email} preview={preview}>
      <header className="page-head">
        <p className="eyebrow">Marketplace</p>
        <h1>{row.document.name}</h1>
      </header>
      <CatalogForm item={row.document} published={row.published} error={query.error} />
      {versions.length ? (
        <section>
          <h2>Versions</h2>
          <table>
            <thead><tr><th>Version</th><th>Saved</th></tr></thead>
            <tbody>
              {versions.map((version) => (
                <tr key={version.id}><td className="mono">{version.version}</td><td>{version.created_at}</td></tr>
              ))}
            </tbody>
          </table>
        </section>
      ) : null}
      <form action="/api/mgmt/catalog" method="post" className="form">
        <input type="hidden" name="op" value="delete" />
        <input type="hidden" name="id" value={row.id} />
        <label className="field"><span>Type yes to delete</span><input name="confirm" /></label>
        <button className="button button-danger" type="submit">Delete</button>
      </form>
    </AdminFrame>
  );
}
