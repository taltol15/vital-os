import { empty } from "@/lib/http";
import { incrementDownloads } from "@/lib/store";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  try {
    const result = await incrementDownloads();
    if (!result.url) return empty(204);
    return new Response(null, {
      status: 302,
      headers: {
        Location: result.url,
        "Cache-Control": "no-store",
      },
    });
  } catch {
    return empty(503);
  }
}
