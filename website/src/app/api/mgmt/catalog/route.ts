import { deleteCatalog, saveCatalog } from "@/lib/admin-api";
import { empty, hasAuthCookie, readPayload } from "@/lib/http";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  if (!hasAuthCookie(request)) return empty(401);
  const fields = await readPayload(request);
  if (fields.op === "delete") return deleteCatalog(request, fields);
  return saveCatalog(request, fields);
}
