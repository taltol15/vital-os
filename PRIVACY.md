# Privacy

Vital OS counts installs without building a profile of you. This page is the whole data model. If a future change collects anything else, this file has to change in the same commit.

## What is collected

Three numbers, shown only as counts in the admin UI at `https://vital-os.org/mgmt`:

| Count | Meaning |
| --- | --- |
| Downloads | How many times something requested the ISO link |
| Installs | How many distinct installs reported that they were installed |
| Live | How many of those installs sent a check-in in the last 14 days |

A check-in chart on that page shows, for each of the last 7 days, how many distinct installs checked in. It is a count per day, not a list of machines.

## What a computer sends

Each installed system keeps a random UUID v4 in `/var/lib/vitalos/telemetry/install_id` (mode 600). That file is created on the machine. It is not derived from the hostname, username, MAC address, serial number, disk id, or any other hardware fact.

The only request is `POST https://vital-os.org/api/v1/telemetry` with this JSON and nothing else:

```json
{"install_id":"...","os_version":"0.1.0","event":"install","ts":"2026-10-05T12:00:00Z"}
```

`event` is `install` or `heartbeat`. `os_version` is the version string from the image, such as `0.1.0`. `ts` is the clock on the computer at send time. The server checks that `ts` looks like a timestamp, then discards it. The server stores its own receipt time.

The same post is used for a weekly check-in (`event` = `heartbeat`).

The client does not send an app list, Marketplace browsing, searches, crash reports, location, or account names. Marketplace installs are a separate action you take in that app. They are not part of this count.

## When it is sent

The switch in Vital Welcome is on by default. The wording on that page is the notice: a random id, the OS version, and a weekly check-in go to vital-os.org, and turning the switch off sends nothing.

The install report is sent when you finish Vital Welcome with the switch left on. If Welcome never runs, a oneshot timer tries once 15 minutes after boot. A second timer sends a check-in about 20 minutes after boot and then at most weekly. Both timers are skipped on the live ISO (`boot=casper`). The installer does not send the report.

If the network is down, the client exits quietly and tries again on a later boot. A failed install report is not marked sent.

Turn the count off in Vital Welcome, or as an administrator:

```bash
sudo vital-telemetry-ctl off
```

`vital-telemetry-ctl on` turns it back on. The setting is `/etc/vital/telemetry.conf`. Members of the `sudo` group can change it without an extra password prompt. While it is off, the client does not create an install id and does not call the server.

## What the server stores

SQLite keeps, for each install id: the OS version, the first time it was seen, the last time it was seen, whether an install event arrived, and the last heartbeat time. Heartbeat days are stored as a date plus the install id, so the 7-day chart can be drawn. The download counter is a single integer.

The server does not have a column for an IP address, hostname, account, or the client timestamp.

Rate limits live in process memory only. For telemetry, the key is the install id plus a hash of the client address mixed with a salt that changes at UTC midnight. That hash is not written to SQLite. At midnight the salt and the address buckets are dropped, so the hashes cannot be matched up the next day. Admin login attempts are limited the same way: memory only, not a log of addresses.

Uvicorn is started with `--no-access-log`. The example Caddyfile discards access logs. Do not turn on proxy logs that record client addresses for this host. If you enable them to debug an outage, delete them within 24 hours.

The catalog, its signature, and uploaded packages are public on purpose. They are not telemetry.

## ISO downloads

The public download link is `https://vital-os.org/api/v1/downloads/iso` (also `/downloads/iso`). Each GET adds one to the download counter and redirects to `VITAL_ISO_URL` when that is set. The response sets no cookie and is marked `Cache-Control: no-store`. It does not identify the downloader.

## What this is not

Ubuntu's crash reporter (`whoopsie`) can still be installed because Settings depends on it. Its service is masked and `report_crashes` is false. Vital OS does not send crash dumps.

Apps you install, including Firefox, keep their own update checks. Those are not this count.
