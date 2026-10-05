# Vital Marketplace

Vital Marketplace is the catalog browser in the Vital OS app grid, plus a small service Tal can run to publish items. The desktop falls back to the catalog shipped in the image when the server is unreachable.

## Catalog document

`schema/catalog-item.schema.json` describes one item. `schema/catalog.schema.json` describes the document returned by `GET /api/v1/catalog`. The same routes are also mounted at `/v1/...` so older clients keep working. `/api/v1` is the canonical prefix.

An item has an id, name, summary, description, icon (`url` and `sha256`), version, category, publisher, homepage, license, install method, optional screenshots, and `min_os_version`. Install methods:

| Method | Fields | What the helper does |
| --- | --- | --- |
| `apt` | `package` | `apt-get install` or `remove` |
| `flatpak` | `flatpak_id` | `flatpak install` from Flathub, or uninstall |
| `deb` | `url`, `sha256` | Download, require the SHA-256 match, then `apt-get install` the file |
| `script` | `url`, `sha256` | Same check. The app shows the script and asks before it runs |

`deb` and `script` URLs must be `https://` or `bundled://` (a file inside the catalog directory, used by the offline sample). The helper downloads again and refuses the file if the digest differs. `checksum` on an item is the SHA-256 of its canonical JSON with `checksum` and `signature` removed.

The sample catalog is `catalog/catalog.json`, generated from `catalog/sources/` by `tools/build_catalog.py`. It lists Firefox and Celluloid (apt), GIMP and Inkscape (Flathub), and **Vital Example Note**, a script marked `"example": true` that only prints a line. Icons in the sample are original tiles, not upstream logos. A `.deb` uses the same `url` and `sha256` fields as the script.

## Client

`/etc/vital/marketplace.conf`:

```
catalog_url=https://vital-os.org/api/v1/catalog
public_key=/etc/vital/marketplace.pub
bundled_catalog=/usr/share/vitalos/marketplace/catalog.json
```

The app verifies the ed25519 `signature` with `/etc/vital/marketplace.pub`. If `catalog_url` is empty, the key is still the placeholder in this repository, or the server cannot be reached, it uses the bundled catalog and shows a banner that the sample is unsigned. Unsigned remote catalogs are rejected. A copy of the same public file is also installed at `/usr/share/vitalos/marketplace/catalog.pub`.

Install, update, and remove go through `pkexec /usr/libexec/vital-marketplace-helper`. The polkit action is `org.vitalos.marketplace.manage`.

## Server

Python, FastAPI, and SQLite.

| Endpoint | Auth | Role |
| --- | --- | --- |
| `GET /api/v1/catalog` | none | Canonical JSON catalog, `ETag`, `Cache-Control: public, max-age=60`. `If-None-Match` returns 304. Includes `signature` when the signing key is configured and the catalog is not empty |
| `GET /api/v1/public-key` | none | Raw ed25519 public key, standard base64 |
| `GET /api/v1/artifacts/{sha256}` | none | Bytes previously uploaded by an admin |
| `GET /api/v1/downloads/iso` | none | Adds one to the ISO download counter and redirects to `VITAL_ISO_URL` when set. No cookie |
| `POST /api/v1/telemetry` | none | Anonymous install or heartbeat. See [PRIVACY.md](../PRIVACY.md) |
| `POST /api/v1/admin/items` | bearer | Create an item. Invalid schema returns 422 |
| `PUT /api/v1/admin/items/{id}` | bearer | Replace an item |
| `DELETE /api/v1/admin/items/{id}` | bearer | Delete an item |
| `POST /api/v1/admin/artifacts` | bearer | Upload bytes. The response is the SHA-256 and path |
| `DELETE /api/v1/admin/tokens/{id}` | bearer | Revoke a token and its browser sessions |
| `/mgmt` | session cookie | Browser UI for the same writes. The cookie is not accepted on `/api` |

There is no unauthenticated write route. Tokens are created with the CLI and stored as SHA-256. Bearer routes are limited to 30 requests a minute per token (`VITAL_MARKET_RATE_LIMIT`).

When `VITAL_MARKET_SIGNING_KEY_FILE` points at an ed25519 PEM key, `GET /api/v1/catalog` includes `signature`. The private key stays on the server. The process reads it on each request. Uvicorn is started with `--no-access-log`.

### Browser UI

`https://vital-os.org/mgmt` is server-rendered HTML on the same process. Sign in by pasting a bearer token. The response sets an `HttpOnly` cookie named `vital_mgmt`, `SameSite=Strict`, `Path=/mgmt`, for two hours (`VITAL_MGMT_SESSION_TTL`). `Secure` is set when the request is HTTPS or `X-Forwarded-Proto` is `https`. Caddy sends that header. Do not expose port 8080 publicly, or a client could spoof the header.

Forms post back to `/mgmt` with a CSRF token stored on the session. A missing or wrong token is 403. Writes without a session are 401. The cookie is not sent to `/api/v1`, and `/api/v1/admin` still requires the bearer token. The CLI stays on bearer tokens.

From the UI you can list, create, edit, and delete items, upload an icon or a deb/script (the SHA-256 and the public URL are shown), publish (sets a new catalog issue time so the next response is re-signed), and revoke tokens by name. The secret is never shown again.

### First run

On the server, as root:

```bash
mkdir -p /etc/vital /var/lib/vital-market
vital-market keygen --private /etc/vital/market.key --public /etc/vital/marketplace.pub
chown vital-market:vital-market /etc/vital/market.key
chmod 600 /etc/vital/market.key
vital-market token create --db /var/lib/vital-market/market.db --name tal
```

`keygen` writes an ed25519 PEM private key (mode 600) and a one-line base64 public key (mode 644). Copy that public file over `marketplace/keys/catalog.pub` in this repository and rebuild the ISO. Clients verify the catalog against the copy baked into `/etc/vital/marketplace.pub`. Until that rebuild, they keep the unsigned sample and show the banner.

The token prints once. Open `https://vital-os.org/mgmt` and paste it. Keep an offline copy of `/etc/vital/market.key`. Do not commit it, email it, or put it in the image.

### Rotating the key

Old images trust the public key they were built with. Replacing the private key without a new ISO makes those images reject the catalog and fall back to the unsigned sample.

```bash
cp -a /etc/vital/market.key /root/market.key.backup
vital-market keygen --force --private /etc/vital/market.key --public /etc/vital/marketplace.pub
chown vital-market:vital-market /etc/vital/market.key
chmod 600 /etc/vital/market.key
```

Put the new public file in `marketplace/keys/catalog.pub`, rebuild the ISO, and ship that image. Keep the previous private key offline until you are sure you no longer need to sign with it. There is no way to push a new public key to machines that are already installed.

### DNS and TLS

`vital-os.org` is the public hostname. Point an A record, an AAAA record, or both, at the server. A CNAME is fine for a name that is not the zone apex. Open TCP 80 and 443 only. `deploy/Caddyfile.example` obtains a certificate and reverse-proxies to `127.0.0.1:8080`. It discards access logs so client addresses are not stored. A commented `www` redirect is in that file; enable it only after `www.vital-os.org` resolves, or certificate issuance will fail.

Set `VITAL_ISO_URL` to the final ISO URL. `GET /api/v1/downloads/iso` counts the hit and redirects there. The example Caddyfile can serve files from `/var/lib/vital-market/releases/`.

Anonymous counts are documented in [PRIVACY.md](../PRIVACY.md). The live window defaults to 14 days (`VITAL_LIVE_DAYS`).

```bash
python3 -m pip install -r marketplace/server/requirements.txt
export VITAL_MARKET_DB=/var/lib/vital-market/market.db
export VITAL_MARKET_DATA=/var/lib/vital-market
export VITAL_MARKET_SIGNING_KEY_FILE=/etc/vital/market.key
uvicorn vital_market.app:app --app-dir marketplace/server --host 127.0.0.1 --port 8080
```

### CLI

```bash
marketplace/cli/vital-market keygen --private /etc/vital/market.key --public /etc/vital/marketplace.pub
marketplace/cli/vital-market token create --db /var/lib/vital-market/market.db --name tal
marketplace/cli/vital-market publish --server https://vital-os.org --token "$TOKEN" item.json
```

`token create` prints the bearer token once. Do not commit it.

### Run it

`deploy/docker-compose.yml` builds `server/Dockerfile` and binds port 8080 to localhost. Put Caddy, or another reverse proxy, in front for TLS. `deploy/Caddyfile.example` is a starting point. `deploy/vital-market.service` is the same process under systemd, also bound to localhost.

```bash
cd marketplace
docker compose -f deploy/docker-compose.yml up --build
```

Mount the private key from the host. Compose reads `VITAL_MARKET_KEY_FILE` and defaults to `./market.key`, which is gitignored.

## Tests

```bash
python3 -m pip install -r marketplace/server/requirements.txt
python3 -m pytest marketplace/server/tests marketplace/python/tests
( cd apps/vital-welcome && python3 -m unittest test_identity.py )
```

## Decisions

- The public hostname is `vital-os.org`. The API base is `https://vital-os.org/api/v1`.
- The private key lives only at `/etc/vital/market.key` on the catalog server. The repository ships a placeholder public file, not a private key.
- Where the ISO file itself is hosted is still chosen at deploy time with `VITAL_ISO_URL`. The counter URL does not change.
