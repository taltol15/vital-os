import { redirect } from "next/navigation";
import { AdminFrame } from "@/components/admin-frame";
import { CatalogForm } from "@/components/catalog-form";
import { currentAdmin } from "@/lib/admin-read";
import { previewEnabled } from "@/lib/preview";

export const dynamic = "force-dynamic";

export default async function NewCatalogItem({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const preview = previewEnabled();
  const admin = await currentAdmin();
  if (!admin && !preview) redirect("/mgmt/login");
  const query = await searchParams;
  return (
    <AdminFrame current="catalog" email={admin?.email} preview={preview}>
      <header className="page-head">
        <p className="eyebrow">Marketplace</p>
        <h1>New package</h1>
      </header>
      <CatalogForm error={query.error} />
    </AdminFrame>
  );
}
