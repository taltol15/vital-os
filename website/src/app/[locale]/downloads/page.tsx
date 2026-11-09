import type { Metadata } from "next";
import { CopyButton } from "@/components/copy-button";
import { dictionary } from "@/i18n";
import { formatBytes, formatDate, localePrefix, siteUrl } from "@/lib/format";
import { renderSimpleMarkdown } from "@/lib/markdown";
import { listReleases } from "@/lib/store";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = dictionary(locale);
  const prefix = localePrefix(locale);
  return {
    title: t.downloads.title,
    description: t.downloads.lede,
    alternates: {
      canonical: `${siteUrl()}${prefix}/downloads`,
      languages: { en: `${siteUrl()}/downloads`, he: `${siteUrl()}/he/downloads` },
    },
  };
}

export default async function DownloadsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = dictionary(locale);
  const releases = [...(await listReleases())].sort((a, b) => Number(b.recommended) - Number(a.recommended) || (a.published_at < b.published_at ? 1 : -1));
  return (
    <div className="shell">
      <header className="page-head">
        <p className="eyebrow">Vital OS</p>
        <h1>{t.downloads.title}</h1>
        <p className="lede">{t.downloads.lede}</p>
      </header>
      {releases.length === 0 ? <p>{t.downloads.empty}</p> : null}
      <div className="release-list">
        {releases.map((release) => (
          <article className="card release" key={release.version} id={`v${release.version}`}>
            <header>
              <h2>{release.version}</h2>
              <div className="badges">
                {release.recommended ? <span className="badge">{t.downloads.recommended}</span> : null}
                {release.archived ? <span className="badge badge-quiet">{t.downloads.archived}</span> : null}
                {release.prerelease ? <span className="badge badge-quiet">{t.downloads.prerelease}</span> : null}
              </div>
            </header>
            <p className="facts">
              <span>{t.downloads.released} {formatDate(release.published_at, locale)}</span>
              <span>{t.downloads.size} {formatBytes(release.size_bytes, locale)} · {release.size_bytes.toLocaleString(locale === "he" ? "he-IL" : "en-GB")} bytes</span>
              <span className="mono">{release.filename}</span>
            </p>
            <div className="checksum">
              <div>
                <div className="index">{t.downloads.sha}</div>
                <code>{release.sha256}</code>
              </div>
              <CopyButton value={release.sha256} label={t.downloads.copy} copied={t.downloads.copied} />
            </div>
            <div className="links">
              {release.recommended ? (
                // eslint-disable-next-line @next/next/no-html-link-for-pages -- the route counts the hit, then redirects
                <a href="/api/v1/downloads/iso">{t.downloads.counted}</a>
              ) : null}
              <a href={release.download_url}>{t.downloads.iso}</a>
              {release.sums_url ? <a href={release.sums_url}>{t.downloads.sums}</a> : null}
              {release.readme_url ? <a href={release.readme_url}>{t.downloads.readme}</a> : null}
            </div>
            <div>
              <h3>{t.downloads.notes}</h3>
              <div className="notes" dangerouslySetInnerHTML={{ __html: renderSimpleMarkdown(release.notes) }} />
            </div>
          </article>
        ))}
      </div>
      <section className="card verify">
        <h2>{t.downloads.verifyTitle}</h2>
        <p>{t.downloads.verifyBody}</p>
        <pre>{`sha256sum -c SHA256SUMS`}</pre>
      </section>
    </div>
  );
}
