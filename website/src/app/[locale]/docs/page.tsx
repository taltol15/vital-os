import Link from "next/link";
import type { Metadata } from "next";
import { dictionary } from "@/i18n";
import { listDocs } from "@/lib/docs";
import { localePrefix, siteUrl } from "@/lib/format";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = dictionary(locale);
  return {
    title: t.docs.title,
    description: t.docs.lede,
    alternates: {
      canonical: `${siteUrl()}${localePrefix(locale)}/docs`,
      languages: { en: `${siteUrl()}/docs`, he: `${siteUrl()}/he/docs` },
    },
  };
}

export default async function DocsIndex({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = dictionary(locale);
  const prefix = localePrefix(locale);
  const docs = listDocs(locale);
  return (
    <div className="shell">
      <header className="page-head">
        <p className="eyebrow">Vital OS</p>
        <h1>{t.docs.title}</h1>
        <p className="lede">{t.docs.lede}</p>
      </header>
      <div className="docs">
        <nav aria-label={t.docs.nav}>
          {docs.map((doc) => (
            <Link key={doc.slug} href={`${prefix}/docs/${doc.slug}`}>{doc.title}</Link>
          ))}
        </nav>
        <div className="stack">
          {docs.map((doc) => (
            <article className="card" key={doc.slug}>
              <h2><Link href={`${prefix}/docs/${doc.slug}`}>{doc.title}</Link></h2>
              <p>{doc.description}</p>
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}
