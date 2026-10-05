"""Server-rendered pages for the /mgmt admin UI."""

from __future__ import annotations

import html
from typing import Mapping


def esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def sparkline(values: list[int]) -> str:
    if not values:
        values = [0]
    width = 280
    height = 72
    peak = max(values) or 1
    step = width / max(len(values) - 1, 1)
    points: list[str] = []
    for index, value in enumerate(values):
        x = index * step
        y = height - 8 - (value / peak) * (height - 16)
        points.append(f"{x:.1f},{y:.1f}")
    last = values[-1]
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="Heartbeats over the last {len(values)} days, latest {last}">'
        '<polyline fill="none" stroke="#d4bc86" stroke-width="2" '
        f'points="{" ".join(points)}" />'
        "</svg>"
    )


def page(title: str, body: str, *, authed: bool) -> str:
    nav = ""
    if authed:
        nav = """
        <nav>
          <a href="/mgmt">Overview</a>
          <a href="/mgmt/items">Items</a>
          <a href="/mgmt/items/new">New item</a>
          <a href="/mgmt/tokens">Tokens</a>
        </nav>
        """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="robots" content="noindex">
  <title>{esc(title)} · Vital OS</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #08090c;
      --card: #12161c;
      --line: #2a3140;
      --text: #f3eee4;
      --muted: #8c8578;
      --gold: #d4bc86;
      --danger: #c45c4a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 15px/1.45 "IBM Plex Sans", "Inter", sans-serif;
    }}
    header, main {{ width: min(960px, calc(100% - 32px)); margin: 0 auto; }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: center;
      padding: 20px 0 8px;
    }}
    h1 {{ font-size: 22px; font-weight: 560; margin: 0; }}
    h2 {{ font-size: 16px; margin: 0 0 8px; }}
    nav {{ display: flex; gap: 14px; flex-wrap: wrap; }}
    a {{ color: var(--gold); text-decoration: none; }}
    main {{ padding-bottom: 48px; }}
    .cards {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }}
    .card, form.panel, .list, .note {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px;
    }}
    .card p {{ margin: 4px 0 0; color: var(--muted); font-size: 13px; }}
    .metric {{ font-size: 32px; letter-spacing: -0.03em; }}
    .spark {{ width: 100%; height: 72px; margin-top: 8px; }}
    label {{ display: block; margin: 10px 0 4px; color: var(--muted); font-size: 13px; }}
    input, textarea, select {{
      width: 100%;
      background: #0c0f14;
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
    }}
    textarea {{ min-height: 88px; }}
    button, .button {{
      background: var(--gold);
      color: #14110c;
      border: 0;
      border-radius: 999px;
      padding: 8px 14px;
      font: inherit;
      cursor: pointer;
    }}
    button.danger {{ background: var(--danger); color: white; }}
    .row {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); }}
    .error {{ color: #f0c2ba; }}
    .muted {{ color: var(--muted); }}
    .stack {{ display: grid; gap: 12px; }}
    @media (max-width: 720px) {{ .cards {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{esc(title)}</h1>
    {nav}
  </header>
  <main class="stack">
    {body}
  </main>
</body>
</html>
"""


def login_page(error: str = "") -> str:
    message = f'<p class="error">{esc(error)}</p>' if error else ""
    body = f"""
    <form class="panel" method="post" action="/mgmt/login" autocomplete="off">
      <h2>Sign in</h2>
      <p class="muted">Paste an admin token from <code>vital-market token create</code>. The browser gets a cookie that lasts two hours. The token itself is not stored in the cookie.</p>
      {message}
      <label for="token">Admin token</label>
      <input id="token" name="token" type="password" required autocomplete="off">
      <p><button type="submit">Sign in</button></p>
    </form>
    """
    return page("Management", body, authed=False)


def dashboard(stats: Mapping[str, object], csrf: str, *, warning: str = "") -> str:
    beats = [int(value) for value in stats["heartbeats"]]  # type: ignore[index]
    labels = list(stats["days"])  # type: ignore[arg-type]
    label = " · ".join(f"{day[5:]} {count}" for day, count in zip(labels, beats))
    warn = f'<p class="error">{esc(warning)}</p>' if warning else ""
    body = f"""
    {warn}
    <section class="cards">
      <article class="card"><h2>Downloads</h2><div class="metric">{esc(stats["downloads"])}</div><p>ISO link hits. No cookies.</p></article>
      <article class="card"><h2>Installs</h2><div class="metric">{esc(stats["installs"])}</div><p>Distinct install ids that reported an install.</p></article>
      <article class="card"><h2>Live</h2><div class="metric">{esc(stats["live"])}</div><p>Heartbeats in the last {esc(stats["live_days"])} days.</p></article>
    </section>
    <section class="card">
      <h2>Heartbeats, last 7 days</h2>
      {sparkline(beats)}
      <p class="muted">{esc(label)}</p>
    </section>
    <form class="panel" method="post" action="/mgmt/publish">
      <input type="hidden" name="csrf" value="{esc(csrf)}">
      <h2>Publish</h2>
      <p class="muted">The public catalog is signed on each read when the server has its private key. Publish sets a new issue time so clients pick up a new signature.</p>
      <button type="submit">Publish catalog</button>
    </form>
    <form class="panel" method="post" action="/mgmt/logout">
      <input type="hidden" name="csrf" value="{esc(csrf)}">
      <button type="submit">Sign out</button>
    </form>
    """
    return page("Overview", body, authed=True)


def items_page(items: list[dict], csrf: str) -> str:
    del csrf
    rows = []
    for item in items:
        rows.append(
            "<tr>"
            f"<td><a href=\"/mgmt/items/{esc(item['id'])}\">{esc(item['name'])}</a></td>"
            f"<td>{esc(item['id'])}</td>"
            f"<td>{esc(item.get('version', ''))}</td>"
            f"<td>{esc(item.get('install', {}).get('method', ''))}</td>"
            "</tr>"
        )
    empty = "<p class=\"muted\">No items yet.</p>" if not rows else ""
    body = f"""
    <section class="list">
      <div class="row"><h2>Catalog items</h2><a class="button" href="/mgmt/items/new">New item</a></div>
      {empty}
      <table>
        <thead><tr><th>Name</th><th>Id</th><th>Version</th><th>Install</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """
    return page("Items", body, authed=True)


def _field(name: str, label: str, value: str, *, kind: str = "text") -> str:
    return (
        f'<label for="{esc(name)}">{esc(label)}</label>'
        f'<input id="{esc(name)}" name="{esc(name)}" type="{esc(kind)}" value="{esc(value)}">'
    )


def item_form(csrf: str, item: dict | None, error: str = "") -> str:
    current = item or {}
    install = current.get("install") or {}
    icon = current.get("icon") or {}
    creating = item is None
    action = "/mgmt/items" if creating else f"/mgmt/items/{esc(current.get('id', ''))}"
    message = f'<p class="error">{esc(error)}</p>' if error else ""
    delete = ""
    if not creating:
        delete = f"""
        <form class="panel" method="post" action="/mgmt/items/{esc(current.get('id', ''))}/delete">
          <input type="hidden" name="csrf" value="{esc(csrf)}">
          <label><input type="checkbox" name="confirm" value="yes"> Delete this item</label>
          <p><button class="danger" type="submit">Delete</button></p>
        </form>
        """
    body = f"""
    <form class="panel" method="post" action="{action}" enctype="multipart/form-data">
      <input type="hidden" name="csrf" value="{esc(csrf)}">
      <h2>{"New item" if creating else "Edit item"}</h2>
      {message}
      {_field("id", "Id", str(current.get("id", "")))}
      {_field("name", "Name", str(current.get("name", "")))}
      {_field("summary", "Summary", str(current.get("summary", "")))}
      <label for="description">Description</label>
      <textarea id="description" name="description">{esc(current.get("description", ""))}</textarea>
      {_field("version", "Version", str(current.get("version", "system")))}
      {_field("category", "Category", str(current.get("category", "")))}
      {_field("publisher", "Publisher", str(current.get("publisher", "")))}
      {_field("homepage", "Homepage", str(current.get("homepage", "https://")))}
      {_field("license", "License", str(current.get("license", "")))}
      {_field("min_os_version", "Minimum Vital OS version", str(current.get("min_os_version", "0.1.0")))}
      <label for="method">Install method</label>
      <select id="method" name="method">
        {''.join(
            f'<option value="{esc(method)}"{" selected" if install.get("method", "apt") == method else ""}>{esc(method)}</option>'
            for method in ("apt", "flatpak", "deb", "script")
        )}
      </select>
      {_field("package", "Apt package", str(install.get("package", "")))}
      {_field("flatpak_id", "Flatpak id", str(install.get("flatpak_id", "")))}
      {_field("url", "Deb or script URL", str(install.get("url", "")))}
      {_field("sha256", "Deb or script SHA-256", str(install.get("sha256", "")))}
      <label for="artifact_file">Or upload a deb/script (SHA-256 is computed here)</label>
      <input id="artifact_file" name="artifact_file" type="file">
      {_field("icon_url", "Icon URL", str(icon.get("url", "")))}
      {_field("icon_sha256", "Icon SHA-256", str(icon.get("sha256", "")))}
      <label for="icon_file">Or upload an icon</label>
      <input id="icon_file" name="icon_file" type="file">
      <label><input type="checkbox" name="example" value="yes" {"checked" if current.get("example") else ""}> Example item</label>
      <p><button type="submit">Save</button></p>
    </form>
    {delete}
    """
    return page("Item", body, authed=True)


def artifact_page(csrf: str, sha256: str, url: str) -> str:
    body = f"""
    <section class="panel">
      <h2>Upload stored</h2>
      <p>SHA-256</p>
      <p><code>{esc(sha256)}</code></p>
      <p>URL</p>
      <p><code>{esc(url)}</code></p>
      <p class="muted">Paste these into a deb, script, or icon field. The bytes are public at that path. Nothing here is a private key.</p>
      <form method="get" action="/mgmt/items/new">
        <input type="hidden" name="csrf" value="{esc(csrf)}">
        <button type="submit">Back to items</button>
      </form>
    </section>
    """
    return page("Upload", body, authed=True)


def tokens_page(rows: list[tuple[int, str, str]], csrf: str) -> str:
    body_rows = []
    for token_id, name, created in rows:
        body_rows.append(
            "<tr>"
            f"<td>{esc(token_id)}</td>"
            f"<td>{esc(name)}</td>"
            f"<td>{esc(created)}</td>"
            "<td><form method=\"post\" "
            f"action=\"/mgmt/tokens/{esc(token_id)}/revoke\">"
            f"<input type=\"hidden\" name=\"csrf\" value=\"{esc(csrf)}\">"
            "<button class=\"danger\" type=\"submit\">Revoke</button></form></td>"
            "</tr>"
        )
    body = f"""
    <section class="list">
      <h2>Admin tokens</h2>
      <p class="muted">Names only. The secret is shown once by the CLI and is not stored. Revoking deletes the hash and any browser sessions that used it.</p>
      <table>
        <thead><tr><th>Id</th><th>Name</th><th>Created</th><th></th></tr></thead>
        <tbody>{''.join(body_rows)}</tbody>
      </table>
    </section>
    """
    return page("Tokens", body, authed=True)
