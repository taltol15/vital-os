import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { SiteFooter, SiteHeader } from "@/components/site";
import { isLocale } from "@/i18n";

export const dynamic = "force-dynamic";

export function generateStaticParams() {
  return [{ locale: "en" }, { locale: "he" }];
}

export default async function LocaleLayout({ children, params }: { children: React.ReactNode; params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  if (!isLocale(locale)) notFound();
  const path = (await headers()).get("x-vital-path") || "/";
  return (
    <>
      <SiteHeader locale={locale} path={path} />
      <main id="content">{children}</main>
      <SiteFooter locale={locale} />
    </>
  );
}
