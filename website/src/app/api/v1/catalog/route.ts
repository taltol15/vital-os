import { buildCatalog, issuedStamp } from "@/lib/catalog";
import { sha256Hex } from "@/lib/canonical";
import { json } from "@/lib/http";
import { loadSigner } from "@/lib/sign";
import { listPublishedCatalog } from "@/lib/store";

export const dynamic = "force-dynamic";

export async function GET(request: Request): Promise<Response> {
  const signer = loadSigner();
  if (!signer) return json({ error: "signing key is not configured" }, 503);
  let rows: Awaited<ReturnType<typeof listPublishedCatalog>>;
  try {
    rows = await listPublishedCatalog();
  } catch {
    return json({ error: "catalog could not be read" }, 500);
  }
  if (!rows.length) return json({ error: "catalog is empty" }, 503);
  let body: string;
  try {
    body = buildCatalog(
      rows.map((row) => row.item),
      issuedStamp(rows.map((row) => row.updated_at)),
      signer,
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "catalog is invalid";
    return json({ error: message }, 500);
  }
  const etag = `"${sha256Hex(body)}"`;
  const headers = {
    ETag: etag,
    "Cache-Control": "public, max-age=60",
  };
  if (request.headers.get("if-none-match") === etag) {
    return new Response(null, { status: 304, headers });
  }
  return new Response(body, {
    status: 200,
    headers: { ...headers, "Content-Type": "application/json; charset=utf-8" },
  });
}
