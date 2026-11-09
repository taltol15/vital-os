import { json } from "@/lib/http";
import { loadSigner } from "@/lib/sign";

export const dynamic = "force-dynamic";

export async function GET(): Promise<Response> {
  const signer = loadSigner();
  if (!signer) return json({ error: "signing key is not configured" }, 404);
  return json({ alg: "ed25519", public_key: signer.publicB64 }, 200, {
    "Cache-Control": "public, max-age=300",
  });
}
