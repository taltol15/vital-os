import { createPrivateKey, createPublicKey, sign, type KeyObject } from "node:crypto";

export type Signer = {
  publicB64: string;
  sign(payload: Buffer): string;
};

function pemFromEnv(raw: string): string {
  const trimmed = raw.trim();
  return trimmed.includes("\\n") ? trimmed.replace(/\\n/g, "\n") : trimmed;
}

export function signerFromPem(pem: string): Signer {
  const privateKey: KeyObject = createPrivateKey(pemFromEnv(pem));
  if (privateKey.asymmetricKeyType !== "ed25519") {
    throw new Error("signing key must be ed25519");
  }
  const der = createPublicKey(privateKey).export({ type: "spki", format: "der" });
  const raw = Buffer.from(der).subarray(-32);
  if (raw.length !== 32) throw new Error("ed25519 public key was not 32 bytes");
  return {
    publicB64: raw.toString("base64"),
    sign(payload: Buffer) {
      return sign(null, payload, privateKey).toString("base64");
    },
  };
}

export function loadSigner(): Signer | null {
  const raw = process.env.VITAL_CATALOG_SIGNING_KEY;
  if (!raw || !raw.trim()) return null;
  return signerFromPem(raw);
}
