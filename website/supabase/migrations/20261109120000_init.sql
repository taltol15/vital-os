-- Vital OS website schema.
-- Apply in the Supabase SQL editor, or with the Supabase CLI, before the site
-- is asked to read or write. The service role bypasses RLS and is used only
-- by server routes for telemetry, the download counter, contact insert, and
-- rate limits. The anon key can read published catalog rows and releases.
-- Authenticated users can do nothing until their user id is inserted into
-- admin_allowlist. Public sign-up does not grant that row.

create extension if not exists pgcrypto;

create table public.admin_allowlist (
  user_id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  created_at timestamptz not null default now()
);

create table public.catalog_items (
  id text primary key check (id ~ '^[A-Za-z0-9][A-Za-z0-9._+-]{1,80}$'),
  document jsonb not null,
  published boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.catalog_item_versions (
  id bigint generated always as identity primary key,
  item_id text not null references public.catalog_items (id) on delete cascade,
  version text not null,
  document jsonb not null,
  created_at timestamptz not null default now()
);

create table public.releases (
  id bigint generated always as identity primary key,
  version text not null unique,
  published_at timestamptz not null,
  notes text not null default '',
  sha256 text not null check (sha256 ~ '^[a-f0-9]{64}$'),
  size_bytes bigint not null check (size_bytes >= 0),
  filename text not null,
  download_url text not null,
  sums_url text,
  readme_url text,
  recommended boolean not null default false,
  archived boolean not null default false,
  prerelease boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index releases_one_recommended on public.releases (recommended) where recommended;

create table public.contact_messages (
  id bigint generated always as identity primary key,
  name text not null check (char_length(name) between 1 and 80),
  email text not null check (char_length(email) between 3 and 120),
  subject text not null check (char_length(subject) between 1 and 120),
  message text not null check (char_length(message) between 1 and 5000),
  created_at timestamptz not null default now(),
  read_at timestamptz
);

create table public.installs (
  install_id uuid primary key,
  os_version text not null,
  first_seen timestamptz not null default now(),
  last_seen timestamptz not null default now(),
  saw_install boolean not null default false,
  last_heartbeat timestamptz
);

create table public.heartbeat_days (
  day date not null,
  install_id uuid not null references public.installs (install_id) on delete cascade,
  primary key (day, install_id)
);

create table public.package_installs (
  package_id text not null,
  install_id uuid not null,
  first_seen timestamptz not null default now(),
  primary key (package_id, install_id)
);

create table public.counters (
  name text primary key,
  value bigint not null default 0
);

insert into public.counters (name, value) values ('downloads', 0);

create table public.rate_buckets (
  bucket_hash text primary key,
  hits integer not null,
  expires_at timestamptz not null
);

create index rate_buckets_expires_idx on public.rate_buckets (expires_at);
create index installs_heartbeat_idx on public.installs (last_heartbeat);
create index heartbeat_days_day_idx on public.heartbeat_days (day);

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger catalog_items_touch
  before update on public.catalog_items
  for each row execute function public.touch_updated_at();

create trigger releases_touch
  before update on public.releases
  for each row execute function public.touch_updated_at();

create or replace function public.is_admin()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.admin_allowlist where user_id = auth.uid()
  );
$$;

create or replace function public.consume_rate(bucket text, max_hits integer, window_seconds integer)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  current_hits integer;
begin
  delete from public.rate_buckets where expires_at < now();
  insert into public.rate_buckets (bucket_hash, hits, expires_at)
  values (bucket, 1, now() + make_interval(secs => window_seconds))
  on conflict (bucket_hash) do update
    set hits = public.rate_buckets.hits + 1
  returning hits into current_hits;
  return current_hits <= max_hits;
end;
$$;

create or replace function public.record_telemetry(
  p_install uuid,
  p_version text,
  p_event text,
  p_package text
) returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_event not in ('install', 'heartbeat', 'package') then
    raise exception 'bad event';
  end if;
  if p_version !~ '^[0-9A-Za-z][0-9A-Za-z._+-]{0,31}$' then
    raise exception 'bad version';
  end if;
  insert into public.installs (install_id, os_version, first_seen, last_seen, saw_install, last_heartbeat)
  values (
    p_install,
    p_version,
    now(),
    now(),
    p_event = 'install',
    case when p_event = 'heartbeat' then now() else null end
  )
  on conflict (install_id) do update set
    os_version = excluded.os_version,
    last_seen = now(),
    saw_install = public.installs.saw_install or excluded.saw_install,
    last_heartbeat = coalesce(excluded.last_heartbeat, public.installs.last_heartbeat);

  if p_event = 'heartbeat' then
    insert into public.heartbeat_days (day, install_id)
    values ((now() at time zone 'utc')::date, p_install)
    on conflict do nothing;
  elsif p_event = 'package' then
    if p_package is null or p_package !~ '^[A-Za-z0-9][A-Za-z0-9._+-]{1,80}$' then
      raise exception 'bad package';
    end if;
    insert into public.package_installs (package_id, install_id, first_seen)
    values (p_package, p_install, now())
    on conflict do nothing;
  end if;
end;
$$;

create or replace function public.increment_downloads()
returns text
language plpgsql
security definer
set search_path = public
as $$
declare
  target text;
begin
  insert into public.counters (name, value) values ('downloads', 1)
  on conflict (name) do update set value = public.counters.value + 1;
  select download_url into target from public.releases where recommended = true limit 1;
  return target;
end;
$$;

create or replace function public.insert_contact(
  p_name text,
  p_email text,
  p_subject text,
  p_message text
) returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if char_length(btrim(p_name)) < 1 or char_length(p_name) > 80 then
    raise exception 'bad name';
  end if;
  if char_length(btrim(p_email)) < 3 or char_length(p_email) > 120 or position('@' in p_email) = 0 then
    raise exception 'bad email';
  end if;
  if char_length(btrim(p_subject)) < 1 or char_length(p_subject) > 120 then
    raise exception 'bad subject';
  end if;
  if char_length(btrim(p_message)) < 1 or char_length(p_message) > 5000 then
    raise exception 'bad message';
  end if;
  insert into public.contact_messages (name, email, subject, message)
  values (btrim(p_name), btrim(p_email), btrim(p_subject), btrim(p_message));
end;
$$;

create or replace function public.admin_stats(live_days integer)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  days jsonb;
  beats jsonb;
  versions jsonb;
  packages jsonb;
begin
  if not public.is_admin() then
    raise exception 'not allowed' using errcode = '42501';
  end if;
  if live_days is null or live_days < 1 or live_days > 90 then
    live_days := 14;
  end if;

  select coalesce(jsonb_agg(day order by day), '[]'::jsonb)
    into days
  from (
    select to_char(d::date, 'YYYY-MM-DD') as day
    from generate_series((now() at time zone 'utc')::date - 6, (now() at time zone 'utc')::date, interval '1 day') as d
  ) series;

  select coalesce(jsonb_agg(n order by day), '[]'::jsonb)
    into beats
  from (
    select series.day, count(heartbeat_days.install_id) as n
    from (
      select (d::date) as day
      from generate_series((now() at time zone 'utc')::date - 6, (now() at time zone 'utc')::date, interval '1 day') as d
    ) series
    left join public.heartbeat_days on heartbeat_days.day = series.day
    group by series.day
    order by series.day
  ) counted;

  select coalesce(jsonb_agg(jsonb_build_object('os_version', os_version, 'count', n) order by n desc, os_version), '[]'::jsonb)
    into versions
  from (
    select os_version, count(*) as n
    from public.installs
    group by os_version
  ) grouped;

  select coalesce(jsonb_agg(jsonb_build_object('package_id', package_id, 'count', n) order by n desc, package_id), '[]'::jsonb)
    into packages
  from (
    select package_id, count(*) as n
    from public.package_installs
    group by package_id
  ) grouped;

  return jsonb_build_object(
    'downloads', coalesce((select value from public.counters where name = 'downloads'), 0),
    'installs', (select count(*) from public.installs where saw_install),
    'live', (
      select count(*) from public.installs
      where last_heartbeat is not null
        and last_heartbeat >= now() - make_interval(days => live_days)
    ),
    'liveDays', live_days,
    'days', days,
    'heartbeats', beats,
    'versions', versions,
    'packages', packages,
    'unreadMessages', (select count(*) from public.contact_messages where read_at is null)
  );
end;
$$;

alter table public.admin_allowlist enable row level security;
alter table public.catalog_items enable row level security;
alter table public.catalog_item_versions enable row level security;
alter table public.releases enable row level security;
alter table public.contact_messages enable row level security;
alter table public.installs enable row level security;
alter table public.heartbeat_days enable row level security;
alter table public.package_installs enable row level security;
alter table public.counters enable row level security;
alter table public.rate_buckets enable row level security;

alter table public.admin_allowlist force row level security;
alter table public.catalog_items force row level security;
alter table public.catalog_item_versions force row level security;
alter table public.releases force row level security;
alter table public.contact_messages force row level security;
alter table public.installs force row level security;
alter table public.heartbeat_days force row level security;
alter table public.package_installs force row level security;
alter table public.counters force row level security;
alter table public.rate_buckets force row level security;

revoke all on table public.admin_allowlist from anon, authenticated;
revoke all on table public.catalog_items from anon, authenticated;
revoke all on table public.catalog_item_versions from anon, authenticated;
revoke all on table public.releases from anon, authenticated;
revoke all on table public.contact_messages from anon, authenticated;
revoke all on table public.installs from anon, authenticated;
revoke all on table public.heartbeat_days from anon, authenticated;
revoke all on table public.package_installs from anon, authenticated;
revoke all on table public.counters from anon, authenticated;
revoke all on table public.rate_buckets from anon, authenticated;

grant select on public.releases to anon;
grant select on public.catalog_items to anon;
grant select, insert, update, delete on public.catalog_items to authenticated;
grant select, insert, delete on public.catalog_item_versions to authenticated;
grant select, insert, update, delete on public.releases to authenticated;
grant select, update on public.contact_messages to authenticated;
grant select on public.installs to authenticated;
grant select on public.heartbeat_days to authenticated;
grant select on public.package_installs to authenticated;
grant select on public.counters to authenticated;
grant select on public.admin_allowlist to authenticated;

grant all on table public.admin_allowlist to service_role;
grant all on table public.catalog_items to service_role;
grant all on table public.catalog_item_versions to service_role;
grant all on table public.releases to service_role;
grant all on table public.contact_messages to service_role;
grant all on table public.installs to service_role;
grant all on table public.heartbeat_days to service_role;
grant all on table public.package_installs to service_role;
grant all on table public.counters to service_role;
grant all on table public.rate_buckets to service_role;

create policy catalog_public_read on public.catalog_items
  for select to anon
  using (published);

create policy catalog_admin_all on public.catalog_items
  for all to authenticated
  using (public.is_admin())
  with check (public.is_admin());

create policy catalog_versions_admin on public.catalog_item_versions
  for all to authenticated
  using (public.is_admin())
  with check (public.is_admin());

create policy releases_public_read on public.releases
  for select to anon
  using (true);

create policy releases_admin_all on public.releases
  for all to authenticated
  using (public.is_admin())
  with check (public.is_admin());

create policy messages_admin_read on public.contact_messages
  for select to authenticated
  using (public.is_admin());

create policy messages_admin_update on public.contact_messages
  for update to authenticated
  using (public.is_admin())
  with check (public.is_admin());

create policy installs_admin_read on public.installs
  for select to authenticated
  using (public.is_admin());

create policy heartbeats_admin_read on public.heartbeat_days
  for select to authenticated
  using (public.is_admin());

create policy packages_admin_read on public.package_installs
  for select to authenticated
  using (public.is_admin());

create policy counters_admin_read on public.counters
  for select to authenticated
  using (public.is_admin());

create policy allowlist_admin_read on public.admin_allowlist
  for select to authenticated
  using (public.is_admin());

revoke all on function public.is_admin() from public, anon;
grant execute on function public.is_admin() to authenticated, service_role;

revoke all on function public.consume_rate(text, integer, integer) from public, anon, authenticated;
grant execute on function public.consume_rate(text, integer, integer) to service_role;

revoke all on function public.record_telemetry(uuid, text, text, text) from public, anon, authenticated;
grant execute on function public.record_telemetry(uuid, text, text, text) to service_role;

revoke all on function public.increment_downloads() from public, anon, authenticated;
grant execute on function public.increment_downloads() to service_role;

revoke all on function public.insert_contact(text, text, text, text) from public, anon, authenticated;
grant execute on function public.insert_contact(text, text, text, text) to service_role;

revoke all on function public.admin_stats(integer) from public, anon;
grant execute on function public.admin_stats(integer) to authenticated;

revoke all on function public.touch_updated_at() from public, anon, authenticated;

-- Seed. Checksums and dates match the GitHub releases verified for this commit.
insert into public.releases (version, published_at, notes, sha256, size_bytes, filename, download_url, sums_url, readme_url, recommended, archived, prerelease) values ('0.2.1', '2026-10-05T21:05:26Z', 'Vital OS v0.2.1 hybrid live and install ISO. Join any .part files, then check SHA256SUMS. Secure Boot is not supported in this release.', '372eda7e6253df3490dbe96e480e8aaf2760bf9f8b3bfedca3622bf00d313f15', 1940025344, 'VitalOS-0.2.1-amd64.iso', 'https://github.com/taltol15/vital-os/releases/download/v0.2.1/VitalOS-0.2.1-amd64.iso', 'https://github.com/taltol15/vital-os/releases/download/v0.2.1/SHA256SUMS', 'https://github.com/taltol15/vital-os/releases/download/v0.2.1/README-download.txt', true, false, false);
insert into public.releases (version, published_at, notes, sha256, size_bytes, filename, download_url, sums_url, readme_url, recommended, archived, prerelease) values ('0.2.0', '2026-10-05T18:49:17Z', 'Vital OS v0.2.0 hybrid live and install ISO. Join any .part files, then check SHA256SUMS. Secure Boot is not supported in this release.', '20f87c13b34a0823260c7076654948867153973e64be891d7a57439c359b691e', 1940011008, 'VitalOS-0.2.0-amd64.iso', 'https://github.com/taltol15/vital-os/releases/download/v0.2.0/VitalOS-0.2.0-amd64.iso', 'https://github.com/taltol15/vital-os/releases/download/v0.2.0/SHA256SUMS', 'https://github.com/taltol15/vital-os/releases/download/v0.2.0/README-download.txt', false, true, false);
insert into public.releases (version, published_at, notes, sha256, size_bytes, filename, download_url, sums_url, readme_url, recommended, archived, prerelease) values ('0.1.1', '2026-10-05T17:31:28Z', 'Vital OS v0.1.1 hybrid live and install ISO. Join any .part files, then check SHA256SUMS. Secure Boot is not supported in this release.', 'c2f156acabbb92919298d67f48568680e462369e984da851780ca64bb1b1268a', 1939980288, 'VitalOS-0.1.1-amd64.iso', 'https://github.com/taltol15/vital-os/releases/download/v0.1.1/VitalOS-0.1.1-amd64.iso', 'https://github.com/taltol15/vital-os/releases/download/v0.1.1/SHA256SUMS', 'https://github.com/taltol15/vital-os/releases/download/v0.1.1/README-download.txt', false, true, false);
insert into public.releases (version, published_at, notes, sha256, size_bytes, filename, download_url, sums_url, readme_url, recommended, archived, prerelease) values ('0.1.0.1', '2026-10-05T14:52:49Z', 'Vital OS v0.1.0.1 hybrid live and install ISO. Join any .part files, then check SHA256SUMS. Secure Boot is not supported in this release.', '777ec93feb129ea1918283c29201be5b74406ffa679abff6f62f5e86629b7b80', 1943822336, 'VitalOS-0.1.0-amd64.iso', 'https://github.com/taltol15/vital-os/releases/download/v0.1.0.1/VitalOS-0.1.0-amd64.iso', 'https://github.com/taltol15/vital-os/releases/download/v0.1.0.1/SHA256SUMS', 'https://github.com/taltol15/vital-os/releases/download/v0.1.0.1/README-download.txt', false, true, false);
insert into public.catalog_items (id, document, published) values ('celluloid', $doc${"id":"celluloid","name":"Celluloid","summary":"A small GTK video player.","description":"Celluloid plays local video and audio through mpv. It is part of the curated Vital OS set. The catalog icon is original.","version":"system","category":"Media","publisher":"Celluloid contributors","homepage":"https://celluloid-player.github.io/","license":"GPL-3.0-or-later","install":{"method":"apt","package":"celluloid"},"min_os_version":"0.1.0","icon":{"url":"https://vital-os.org/catalog/icons/media.svg","sha256":"ec2e5087bc21b0b948b76d2acdc6276ff7412b4ae86aeb39ee4d0903409da48d"},"screenshots":[]}$doc$::jsonb, true);
insert into public.catalog_item_versions (item_id, version, document) values ('celluloid', 'system', $doc${"id":"celluloid","name":"Celluloid","summary":"A small GTK video player.","description":"Celluloid plays local video and audio through mpv. It is part of the curated Vital OS set. The catalog icon is original.","version":"system","category":"Media","publisher":"Celluloid contributors","homepage":"https://celluloid-player.github.io/","license":"GPL-3.0-or-later","install":{"method":"apt","package":"celluloid"},"min_os_version":"0.1.0","icon":{"url":"https://vital-os.org/catalog/icons/media.svg","sha256":"ec2e5087bc21b0b948b76d2acdc6276ff7412b4ae86aeb39ee4d0903409da48d"},"screenshots":[]}$doc$::jsonb);
insert into public.catalog_items (id, document, published) values ('firefox', $doc${"id":"firefox","name":"Firefox","summary":"Web browser from Mozilla's apt archive.","description":"Firefox is already part of the Vital OS image, installed from packages.mozilla.org rather than a snap. Marketplace can reinstall it with apt if it has been removed. The icon in this catalog is an original Vital tile, not the Firefox logo.","version":"system","category":"Internet","publisher":"Mozilla","homepage":"https://www.mozilla.org/firefox/","license":"MPL-2.0","install":{"method":"apt","package":"firefox"},"min_os_version":"0.1.0","icon":{"url":"https://vital-os.org/catalog/icons/web.svg","sha256":"907a8d99a5a0192213888ebbaa8ee90829bad5124ae4989a5502a5faf016705b"},"screenshots":[]}$doc$::jsonb, true);
insert into public.catalog_item_versions (item_id, version, document) values ('firefox', 'system', $doc${"id":"firefox","name":"Firefox","summary":"Web browser from Mozilla's apt archive.","description":"Firefox is already part of the Vital OS image, installed from packages.mozilla.org rather than a snap. Marketplace can reinstall it with apt if it has been removed. The icon in this catalog is an original Vital tile, not the Firefox logo.","version":"system","category":"Internet","publisher":"Mozilla","homepage":"https://www.mozilla.org/firefox/","license":"MPL-2.0","install":{"method":"apt","package":"firefox"},"min_os_version":"0.1.0","icon":{"url":"https://vital-os.org/catalog/icons/web.svg","sha256":"907a8d99a5a0192213888ebbaa8ee90829bad5124ae4989a5502a5faf016705b"},"screenshots":[]}$doc$::jsonb);
insert into public.catalog_items (id, document, published) values ('gimp', $doc${"id":"gimp","name":"GIMP","summary":"Image editor, installed from Flathub.","description":"GNU Image Manipulation Program. Vital Marketplace installs the Flathub build org.gimp.GIMP. Flathub must be reachable the first time. The catalog icon is an original tile, not the GIMP mascot.","version":"flathub","category":"Graphics","publisher":"The GIMP team","homepage":"https://www.gimp.org/","license":"GPL-3.0-or-later","install":{"method":"flatpak","flatpak_id":"org.gimp.GIMP"},"min_os_version":"0.1.0","icon":{"url":"https://vital-os.org/catalog/icons/graphics.svg","sha256":"43378af7614c00c2b58d120c36f62bd03d9bf65f8c98e88218acb4e080afa322"},"screenshots":[]}$doc$::jsonb, true);
insert into public.catalog_item_versions (item_id, version, document) values ('gimp', 'flathub', $doc${"id":"gimp","name":"GIMP","summary":"Image editor, installed from Flathub.","description":"GNU Image Manipulation Program. Vital Marketplace installs the Flathub build org.gimp.GIMP. Flathub must be reachable the first time. The catalog icon is an original tile, not the GIMP mascot.","version":"flathub","category":"Graphics","publisher":"The GIMP team","homepage":"https://www.gimp.org/","license":"GPL-3.0-or-later","install":{"method":"flatpak","flatpak_id":"org.gimp.GIMP"},"min_os_version":"0.1.0","icon":{"url":"https://vital-os.org/catalog/icons/graphics.svg","sha256":"43378af7614c00c2b58d120c36f62bd03d9bf65f8c98e88218acb4e080afa322"},"screenshots":[]}$doc$::jsonb);
insert into public.catalog_items (id, document, published) values ('inkscape', $doc${"id":"inkscape","name":"Inkscape","summary":"Vector drawing, installed from Flathub.","description":"Inkscape edits SVG drawings. Vital Marketplace installs org.inkscape.Inkscape from Flathub. The catalog icon is original.","version":"flathub","category":"Graphics","publisher":"The Inkscape team","homepage":"https://inkscape.org/","license":"GPL-2.0-or-later","install":{"method":"flatpak","flatpak_id":"org.inkscape.Inkscape"},"min_os_version":"0.1.0","icon":{"url":"https://vital-os.org/catalog/icons/draw.svg","sha256":"0750766b662117e0af37f539b87a19ff160215b018709edcf9e2266e6a21f424"},"screenshots":[]}$doc$::jsonb, true);
insert into public.catalog_item_versions (item_id, version, document) values ('inkscape', 'flathub', $doc${"id":"inkscape","name":"Inkscape","summary":"Vector drawing, installed from Flathub.","description":"Inkscape edits SVG drawings. Vital Marketplace installs org.inkscape.Inkscape from Flathub. The catalog icon is original.","version":"flathub","category":"Graphics","publisher":"The Inkscape team","homepage":"https://inkscape.org/","license":"GPL-2.0-or-later","install":{"method":"flatpak","flatpak_id":"org.inkscape.Inkscape"},"min_os_version":"0.1.0","icon":{"url":"https://vital-os.org/catalog/icons/draw.svg","sha256":"0750766b662117e0af37f539b87a19ff160215b018709edcf9e2266e6a21f424"},"screenshots":[]}$doc$::jsonb);
insert into public.catalog_items (id, document, published) values ('vital-example-note', $doc${"id":"vital-example-note","name":"Vital Example Note","summary":"Example script. It prints one line and changes nothing.","description":"This entry exists so the script installer can be reviewed. It is not a product. Marketplace shows the script and asks before it runs. The helper downloads it again and refuses it if the SHA-256 does not match. It stays unpublished until an administrator turns it on.","version":"0.1.0","category":"Examples","publisher":"Vital OS","homepage":"https://github.com/taltol15/vital-os","license":"GPL-3.0-or-later","install":{"method":"script","url":"https://vital-os.org/catalog/examples/vital-demo-note.sh","sha256":"f987cbd9f870a513ad46ff21824769f27eede70a0174529b7cc304e06692a19f"},"example":true,"min_os_version":"0.1.0","icon":{"url":"https://vital-os.org/catalog/icons/example.svg","sha256":"de734f21beea944dbe5925ffec76bc2911f21fd1a6688bce2471693a084db112"},"screenshots":[]}$doc$::jsonb, false);
insert into public.catalog_item_versions (item_id, version, document) values ('vital-example-note', '0.1.0', $doc${"id":"vital-example-note","name":"Vital Example Note","summary":"Example script. It prints one line and changes nothing.","description":"This entry exists so the script installer can be reviewed. It is not a product. Marketplace shows the script and asks before it runs. The helper downloads it again and refuses it if the SHA-256 does not match. It stays unpublished until an administrator turns it on.","version":"0.1.0","category":"Examples","publisher":"Vital OS","homepage":"https://github.com/taltol15/vital-os","license":"GPL-3.0-or-later","install":{"method":"script","url":"https://vital-os.org/catalog/examples/vital-demo-note.sh","sha256":"f987cbd9f870a513ad46ff21824769f27eede70a0174529b7cc304e06692a19f"},"example":true,"min_os_version":"0.1.0","icon":{"url":"https://vital-os.org/catalog/icons/example.svg","sha256":"de734f21beea944dbe5925ffec76bc2911f21fd1a6688bce2471693a084db112"},"screenshots":[]}$doc$::jsonb);

grant usage, select on all sequences in schema public to authenticated, service_role;
