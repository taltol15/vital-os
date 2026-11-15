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

The only request is `POST https://vital-os.org/api/v1/telemetry`. An install or a weekly check-in sends this JSON and nothing else:

```json
{"install_id":"...","os_version":"0.2.1","event":"install","ts":"2026-10-05T12:00:00Z"}
```

`event` is `install` or `heartbeat`. `os_version` is the version string from the image, such as `0.2.1`. `ts` is the clock on the computer at send time. The server checks that `ts` looks like a timestamp, then discards it. The server stores its own receipt time.

The same post is used for a weekly check-in (`event` = `heartbeat`).

After a successful Marketplace install or update, and only while this switch is on, the client may send one more shape. `event` is `package`, and `package_id` is the catalog item id (for example `gimp`). It is not a list of every program on the computer, and it is not sent for browsing or search.

```json
{"install_id":"...","os_version":"0.2.1","event":"package","package_id":"gimp","ts":"2026-10-05T12:00:00Z"}
```

The client does not send Marketplace browsing, searches, crash reports, location, or account names.

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

For each install id the server keeps the OS version, the first time it was seen, the last time it was seen, whether an install event arrived, and the last heartbeat time. Heartbeat days are stored as a date plus the install id, so the 7-day chart can be drawn. A package report stores the catalog item id and the install id, so the admin page can count machines per item. The download counter is a single integer.

The reference catalog process keeps those rows in SQLite. The website at vital-os.org keeps the same columns in Postgres. Neither database has a column for an IP address, a hostname, an account, or the client timestamp.

The Python server keeps rate limits in process memory only. The website has no shared process memory, so it stores a hash of the install id or of the client address, mixed with a secret and the current UTC hour. The table has the hash, a hit count, and an expiry. It has no address column. Expired rows are deleted. The hash is not useful after the hour changes or the secret is rotated.

The website contact form is separate from this count. It stores the name, email, subject, and message that were typed into the form, so an administrator can read them. It does not store an address. A hidden field that a person does not see, and a rate limit, drop automated posts. The form does not send email.

Uvicorn is started with `--no-access-log`. The example Caddyfile discards access logs. Do not turn on proxy logs that record client addresses for this host. If you enable them to debug an outage, delete them within 24 hours.

The catalog, its signature, and uploaded packages are public on purpose. They are not telemetry.

## Vital Assistant

Vital Assistant is a separate program. It is not part of the install count above.

Questions you type are sent only to the provider that answers that request: xAI Grok (`https://api.x.ai`), an OpenAI-compatible address you enter, Ollama on this computer, or the optional local llama.cpp model on this computer. They are not sent to vital-os.org. They are not included in telemetry. The overlay and the terminal show the provider name for each reply. If the Grok key is missing or the network request fails, and a local model is installed, the local model answers instead.

An API key is stored in the system keyring (libsecret) under the schema `org.vitalos.Assistant`. It is not written to a config file, not printed by `vital status`, and not sent anywhere except as the bearer token on the request to the provider you chose. The action log redacts bearer tokens and key-shaped strings. `vital disconnect` deletes the key. Removing the package does not delete a key already in your keyring; run `vital disconnect` first if you want it gone.

A local history of questions and answers is stored only on this computer, in `~/.local/state/vitalos/assistant/history.jsonl` (mode 0600). It is not uploaded. Settings can erase it. `history_enabled=0` stops new entries. The action log next to it records allowlisted system actions (what was asked, whether you approved it, the argv, and the result). It does not record the API key.

The working directory, last command, exit code, stderr, and distro name are included only when `send_context=1`, when you run `vital explain`, or when the optional failed-command hint is on (`shell_hook=1`). The hint is off by default. It suggests a fix and does not run it. Stderr is copied into the runtime directory only while the hint is on.

Files, the active window title and app, the clipboard, and a screenshot are off by default. Settings only reveals the controls. Each question starts with them off, and turning one on is the consent for that question. The window title is read from the GNOME extension at that moment; focus changes are not saved. A screenshot uses the desktop portal, which shows its own dialog. If any of those four is included and you have not allowed a remote send, the request stays on the local model when one is installed, and is refused when one is not. Nothing is sent in that refusal. Key files (`id_rsa`, `.pem`, `.ssh`) are not attached. The local Qwen model is text-only, so it does not receive screenshot pixels.

A suggested command runs only after you confirm. `y` is enough for an ordinary command. A command that looks like `rm -rf`, `dd`, `mkfs`, `chmod -R 777`, or a similar destructive action is refused unless you type `yes` or type the command itself. Text piped into `vital ask` is treated as context and is never the confirmation. Allowlisted system actions that change the computer show the exact command and wait. Privileged installs go through polkit. There is no root shell.

## ISO downloads

The public download link is `https://vital-os.org/api/v1/downloads/iso` (also `/downloads/iso`). Each GET adds one to the download counter and redirects to `VITAL_ISO_URL` when that is set. The response sets no cookie and is marked `Cache-Control: no-store`. It does not identify the downloader.

## What this is not

Ubuntu's crash reporter (`whoopsie`) can still be installed because Settings depends on it. Its service is masked and `report_crashes` is false. Vital OS does not send crash dumps.

Apps you install, including Firefox, keep their own update checks. Those are not this count.
