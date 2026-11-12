import type { Metadata } from "next";
import { ContactForm } from "@/components/contact-form";
import { dictionary, isLocale } from "@/i18n";
import { localePrefix, siteUrl } from "@/lib/format";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const t = dictionary(locale);
  return {
    title: t.contact.title,
    description: t.contact.lede,
    alternates: {
      canonical: `${siteUrl()}${localePrefix(locale)}/contact`,
      languages: { en: `${siteUrl()}/contact`, he: `${siteUrl()}/he/contact` },
    },
  };
}

export default async function ContactPage({
  params,
  searchParams,
}: {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ sent?: string; error?: string }>;
}) {
  const { locale } = await params;
  if (!isLocale(locale)) return null;
  const query = await searchParams;
  const t = dictionary(locale);
  const initial = query.sent ? "sent" : query.error;
  return (
    <div className="shell">
      <header className="page-head">
        <p className="eyebrow">Vital OS</p>
        <h1>{t.contact.title}</h1>
        <p className="lede">{t.contact.lede}</p>
      </header>
      <ContactForm locale={locale} dict={t.contact} initial={initial} />
    </div>
  );
}
