# vital-os.org

The public site for Vital OS. It serves the pages, the signed Marketplace catalog, and the anonymous install count the desktop already calls.

The paths match the image:

| Desktop | This site |
| --- | --- |
| `GET /api/v1/catalog` and `/v1/catalog` | Signed catalog, `ETag`, `Cache-Control: public, max-age=60` |
| `GET /api/v1/public-key` | Raw ed25519 public key, standard base64 |
| `POST /api/v1/telemetry` | `install`, `heartbeat`, or `package` |
| `GET /api/v1/downloads/iso` and `/downloads/iso` | Adds one to the counter and redirects. No cookie |
| `https://vital-os.org/mgmt` | Admin. Not linked from the public pages. `noindex` |

The catalog signature is ed25519 over the canonical JSON used by `marketplace/python/vital_catalog.py` (sorted keys, no extra whitespace, `signature` removed). The private key is read from the environment on the server. It is not sent to the browser.

## Pages

- `/` landing page
- `/downloads` releases stored in Supabase
- `/docs` MDX scaffold. English is the body. Hebrew falls back to that body and says so
- `/contact` messages stored for an admin. No mail is sent
- `/he/...` the same pages in Hebrew for the interface
- `/mgmt` email login. A signed-in user who is not in `admin_allowlist` is refused

## Local

```bash
cd website
npm install
npm test
npm run typecheck
npm run lint
npm run build
npm run dev
```

Without Supabase or a signing key, the public pages render the seed releases and the catalog route answers 503. Tests sign a catalog with a throwaway key and check it with the distro verifier. `VITAL_PREVIEW=1` draws the admin dashboard from fixtures. That switch is ignored when `VERCEL` is set.

## Environment

Copy `.env.example`. Set the real values in Vercel, not in git.

| Variable | Secret | Role |
| --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | no | Project URL |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | no | Browser and anon server reads |
| `NEXT_PUBLIC_SITE_URL` | no | Canonical URLs. `https://vital-os.org` |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | Telemetry, contact insert, download counter, rate limits. Bypasses RLS |
| `VITAL_CATALOG_SIGNING_KEY` | yes | PKCS#8 PEM. Newlines may be `\n` |
| `VITAL_RATE_LIMIT_SALT` | yes | HMAC key for rate-limit hashes. 16 characters or more |
| `VITAL_LIVE_DAYS` | no | Optional. Default 14 |
| `VITAL_PREVIEW` | no | Local screenshots only. Never set this on Vercel |

## Database

Apply `supabase/migrations/20261109120000_init.sql` in the Supabase SQL editor before the first deploy. It creates the tables, turns on row level security, and seeds the GitHub releases through v0.2.1 plus the remote catalog items.

Anonymous reads are limited to published catalog rows and releases. Writes for telemetry, contact, and the download counter are functions granted to the service role only. Authenticated queries succeed only when `public.is_admin()` is true, which means the user id is in `admin_allowlist`. Creating an Auth user does not insert that row.

After you create the admin user in Supabase Auth (and confirm the email, or create the user already confirmed), insert the allowlist row yourself:

```sql
insert into public.admin_allowlist (user_id, email)
values ('00000000-0000-0000-0000-000000000000', 'you@example.com');
```

Turn off public sign-ups in the Auth settings as well. The site never calls sign-up, and the allowlist is the real gate.

## Signing key

`marketplace/keys/catalog.pub` is the production public key, as the one line of standard base64 the desktop verifier accepts. `VITAL_CATALOG_SIGNING_KEY` must be the matching ed25519 private PEM. A different private key makes a new image reject the catalog.

Machines installed from v0.2.1 still have the old placeholder file. They will not trust a catalog signed with this key. There is no way to push the new public key to a system that is already installed. The next ISO is what carries it.

`GET /api/v1/public-key` returns the key this server is using. The desktop does not fetch that URL. It uses the file baked into the image.

## Vercel

- Root directory: `website`
- Framework preset: Next.js
- Build command: `npm run build` (the default `next build`)
- Install command: `npm install`
- Output: the Next.js default. Do not set a static export. The catalog and telemetry routes need the server
- Node.js: 22

Do not deploy from a pull request until the migration has been applied and the three secrets are set. A build without them still succeeds. At runtime the catalog and telemetry routes fail closed (503) until the signing key and the service role are present. The downloads page keeps showing the seed releases if the database is not configured.

## Counts

`POST /api/v1/telemetry` accepts the four fields the current image sends. It also accepts `event: "package"` plus `package_id` (the catalog id). Older images never send that event, so they keep working. A current Marketplace reports a package only after a successful install or update, and only when the Welcome switch is on. The detail is in `PRIVACY.md`.

Rate-limit rows store a hash, a count, and an expiry. They do not store an address. The contact form stores the message the person typed and nothing about the network.

## What is seeded

Releases v0.1.0.1, v0.1.1, v0.2.0, and v0.2.1, with the asset sizes and SHA-256 digests from GitHub. v0.2.1 is the recommended image. Its ISO digest is `372eda7e6253df3490dbe96e480e8aaf2760bf9f8b3bfedca3622bf00d313f15`.

The signed catalog starts with Celluloid, Firefox, GIMP, and Inkscape. Icons are the original tiles, served from `/catalog/icons/`. Vital Example Note is seeded as an unpublished draft. Vital Assistant is not in the remote catalog until a real `https://` package URL exists. The image still ships it, and the bundled catalog still lists it.
