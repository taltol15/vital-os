# Vital Marketplace

Vital Marketplace is the catalog browser in the Vital OS app grid, plus a small service Tal can run to publish items. The desktop falls back to the catalog shipped in the image when the server is unreachable.

## Catalog document

`schema/catalog-item.schema.json` describes one item. `schema/catalog.schema.json` describes the document returned by `GET /v1/catalog`.

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
catalog_url=
public_key=/usr/share/vitalos/marketplace/catalog.pub
bundled_catalog=/usr/share/vitalos/marketplace/catalog.json
```

`catalog_url` should be the full `GET /v1/catalog` URL once a server exists. The app verifies the ed25519 `signature` with the public key. If the URL is empty, the key is still a placeholder, or the server cannot be reached, it uses the bundled catalog. Unsigned remote catalogs are rejected.

Install, update, and remove go through `pkexec /usr/libexec/vital-marketplace-helper`. The polkit action is `org.vitalos.marketplace.manage`.

## Server

Python, FastAPI, and SQLite.

| Endpoint | Auth | Role |
| --- | --- | --- |
| `GET /v1/catalog` | none | Canonical JSON catalog, `ETag`, `Cache-Control: public, max-age=60`. `If-None-Match` returns 304 |
| `GET /v1/public-key` | none | Raw ed25519 public key, standard base64 |
| `GET /v1/artifacts/{sha256}` | none | Bytes previously uploaded by an admin |
| `POST /v1/admin/items` | bearer | Create an item. Invalid schema returns 422 |
| `PUT /v1/admin/items/{id}` | bearer | Replace an item |
| `DELETE /v1/admin/items/{id}` | bearer | Delete an item |
| `POST /v1/admin/artifacts` | bearer | Upload bytes. The response is the SHA-256 and path |

There is no unauthenticated admin route. Tokens are created with the CLI and stored as SHA-256. Admin routes are limited to 30 requests a minute per token (`VITAL_MARKET_RATE_LIMIT`).

When `VITAL_MARKET_SIGNING_KEY_FILE` points at an ed25519 PEM key, `GET /v1/catalog` includes `signature`. The private key stays on the server.

```bash
python3 -m pip install -r marketplace/server/requirements.txt
export VITAL_MARKET_DB=/var/lib/vital-market/market.db
export VITAL_MARKET_DATA=/var/lib/vital-market
export VITAL_MARKET_SIGNING_KEY_FILE=/etc/vital/market.key
uvicorn vital_market.app:app --app-dir marketplace/server --host 127.0.0.1 --port 8080
```

### CLI

```bash
marketplace/cli/vital-market keygen --private /etc/vital/market.key --public catalog.pub
marketplace/cli/vital-market token create --db /var/lib/vital-market/market.db --name tal
marketplace/cli/vital-market publish --server http://127.0.0.1:8080 --token "$TOKEN" item.json
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

## Decisions still open

- The public hostname for the catalog. `catalog_url` is empty until that exists.
- Where the ed25519 private key lives, and who can replace `catalog.pub` in the image. The repository ships a placeholder, not a private key.
