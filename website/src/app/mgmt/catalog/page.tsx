import Link from "next/link";
import { redirect } from "next/navigation";
import { AdminFrame } from "@/components/admin-frame";
import { currentAdmin, loadCatalog } from "@/lib/admin-read";
import { previewEnabled } from "@/lib/preview";

export const dynamic = "force-dynamic";

export default async function CatalogPage() {
  const preview = previewEnabled();
  const admin = await currentAdmin();
  if (!admin && !preview) redirect("/mgmt/login");
  const rows = await loadCatalog();
  return (
    <AdminFrame current="catalog" email={admin?.email} preview={preview}>
      <header className="page-head">
        <p className="eyebrow">Marketplace</p>
        <h1>Packages</h1>
        <p className="lede">Published rows are signed into <span className="mono">/api/v1/catalog</span> on each read. The private key never leaves the server.</p>
        <p><Link className="button button-small" href="/mgmt/catalog/new">New package</Link></p>
      </header>
      <table>
        <thead><tr><th>Name</th><th>Id</th><th>Version</th><th>Method</th><th>State</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id}>
              <td><Link href={`/mgmt/catalog/${row.id}`}>{row.document.name}</Link></td>
              <td className="mono">{row.id}</td>
              <td className="mono">{row.document.version}</td>
              <td>{row.document.install.method}</td>
              <td>{row.published ? "Published" : "Draft"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </AdminFrame>
  );
}
