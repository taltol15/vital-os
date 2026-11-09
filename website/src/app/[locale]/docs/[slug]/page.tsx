import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { MDXRemote } from "next-mdx-remote/rsc";
import { Kbd } from "@/components/mdx";
import { dictionary } from "@/i18n";
import { listDocs, readDoc } from "@/lib/docs";
import { localePrefix, siteUrl } from "@/lib/format";

export function generateStaticParams() {
  return listDocs("en").flatMap((doc) => [
    { locale: "en", slug: doc.slug },
    { locale: "he", slug: doc.slug },
  ]);
}

export async function generateMetadata({ params }: { params: Promise<{ locale: string; slug: string }> }): Promise<Metadata> {
  const { locale, slug } = await params;
  const doc = readDoc(locale, slug);
  if (!doc) return {};
  const prefix = localePrefix(locale);
  return {
    title: doc.title,
    description: doc.description,
    alternates: {
      canonical: `${siteUrl()}${prefix}/docs/${slug}`,
      languages: { en: `${siteUrl()}/docs/${slug}`, he: `${siteUrl()}/he/docs/${slug}` },
    },
  };
}

export default async function DocPage({ params }: { params: Promise<{ locale: string; slug: string }> }) {
  const { locale, slug } = await params;
  const doc = readDoc(locale, slug);
  if (!doc) notFound();
  const t = dictionary(locale);
  const prefix = localePrefix(locale);
  const docs = listDocs(locale);
  return (
    <div className="shell">
      <header className="page-head">
        <p className="eyebrow">Docs</p>
        <h1>{doc.title}</h1>
      </header>
      <div className="docs">
        <nav aria-label={t.docs.nav}>
          {docs.map((item) => (
            <Link key={item.slug} href={`${prefix}/docs/${item.slug}`} aria-current={item.slug === slug ? "page" : undefined}>{item.title}</Link>
          ))}
        </nav>
        <article>
          <p className="scaffold">{t.docs.scaffold}</p>
          {doc.fallback ? <p className="scaffold">{t.docs.english}</p> : null}
          <MDXRemote
            source={doc.body}
            components={{ Kbd }}
            options={{ blockJS: true, blockDangerousJS: true }}
          />
        </article>
      </div>
    </div>
  );
}
