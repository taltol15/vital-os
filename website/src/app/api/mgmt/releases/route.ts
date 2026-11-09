import { saveRelease } from "@/lib/admin-api";
import { empty, hasAuthCookie, readPayload } from "@/lib/http";

export const dynamic = "force-dynamic";

export async function POST(request: Request): Promise<Response> {
  if (!hasAuthCookie(request)) return empty(401);
  return saveRelease(request, await readPayload(request));
}
