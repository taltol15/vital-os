import { createHash, generateKeyPairSync } from "node:crypto";
import { readFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import { GET as getCatalog } from "@/app/api/v1/catalog/route";
import { GET as getKey } from "@/app/api/v1/public-key/route";
import { itemChecksum } from "@/lib/canonical";
import { signerFromPem } from "@/lib/sign";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "../..");

afterEach(() => {
  delete process.env.VITAL_CATALOG_SIGNING_KEY;
  delete process.env.VITAL_DATA_DRIVER;
});

describe("catalog canonical form", () => {
  it("matches checksums the distro already published", () => {
    const catalog = JSON.parse(readFileSync(path.join(repo, "marketplace/catalog/catalog.json"), "utf8")) as {
      items: Record<string, unknown>[];
    };
    for (const item of catalog.items) {
      expect(itemChecksum(item)).toBe(item.checksum);
    }
  });
});

describe("signed catalog", () => {
  it("round-trips through the distro verifier", async () => {
    const { privateKey } = generateKeyPairSync("ed25519");
    const pem = privateKey.export({ type: "pkcs8", format: "pem" }).toString();
    process.env.VITAL_CATALOG_SIGNING_KEY = pem;
    process.env.VITAL_DATA_DRIVER = "memory";
    const signer = signerFromPem(pem);
    const response = await getCatalog(new Request("https://vital-os.org/api/v1/catalog"));
    expect(response.status).toBe(200);
    const catalog = await response.json();
    expect(catalog.signature.alg).toBe("ed25519");
    expect(catalog.signature.key_id).toBe("vital-catalog");
    const key = await getKey();
    expect(key.status).toBe(200);
    const published = (await key.json()) as { public_key: string };
    expect(published.public_key).toBe(signer.publicB64);

    const script = `
import json, sys
from vital_catalog import validate_catalog, verify_catalog_signature
catalog = json.load(sys.stdin)
public = sys.argv[1]
errors = validate_catalog(catalog)
assert errors == [], errors
assert verify_catalog_signature(catalog, public)
catalog["name"] = "Tampered"
assert verify_catalog_signature(catalog, public) is False
print("ok")
`;
    const result = spawnSync("python3", ["-c", script, signer.publicB64], {
      input: JSON.stringify(catalog),
      cwd: repo,
      encoding: "utf8",
      env: { ...process.env, PYTHONPATH: path.join(repo, "marketplace/python") },
    });
    expect(result.status, result.stderr).toBe(0);
    expect(result.stdout).toContain("ok");
    expect(createHash("sha256").update(JSON.stringify(catalog)).digest("hex")).toHaveLength(64);
  });
});
