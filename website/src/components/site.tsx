import Image from "next/image";
import Link from "next/link";
import { dictionary } from "@/i18n";
import { localePrefix } from "@/lib/format";

export function Mark({ className = "" }: { className?: string }) {
  return (
    <span className={`mark-wrap ${className}`}>
      <span className="glow" aria-hidden="true" />
      <svg viewBox="0 0 128 128" role="img" aria-label="Vital OS">
        <title>Vital OS</title>
        <circle className="ring" cx="64" cy="64" r="49" fill="none" stroke="#C6A56A" strokeWidth="1.35" />
        <circle cx="64" cy="64" r="43.25" fill="none" stroke="#F3EEE4" strokeOpacity="0.28" strokeWidth="0.6" />
        <path d="M39 48.5 L64 86.5 L89 48.5" fill="none" stroke="#F3EEE4" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="64" cy="86.5" r="2.55" fill="#C6A56A" />
      </svg>
    </span>
  );
}

export function SiteHeader({ locale, path }: { locale: string; path: string }) {
  const t = dictionary(locale);
  const prefix = localePrefix(locale);
  const href = (page: string) => `${prefix}${page}` || "/";
  const enHref = path === "/" ? "/" : path;
  const heHref = path === "/" ? "/he" : `/he${path}`;
  const links = [
    { href: href("/downloads"), label: t.nav.downloads, current: path.startsWith("/downloads") },
    { href: href("/docs"), label: t.nav.docs, current: path.startsWith("/docs") },
    { href: href("/contact"), label: t.nav.contact, current: path.startsWith("/contact") },
  ];
  return (
    <header className="site-header">
      <a className="skip" href="#content">{t.skip}</a>
      <div className="header-bar">
        <Link className="brand" href={href("/")}>
          <Image src="/brand/vital-symbol.svg" alt="" width={28} height={28} />
          <Image src="/brand/vital-wordmark.svg" alt="Vital OS" width={132} height={23} />
        </Link>
        <nav className="nav-bar" aria-label={t.nav.primary}>
          {links.map((link) => (
            <Link key={link.href} href={link.href} aria-current={link.current ? "page" : undefined}>{link.label}</Link>
          ))}
        </nav>
        <div className="header-tools">
          <nav className="locale" aria-label={t.localeLabel}>
            <a href={enHref} hrefLang="en" lang="en" aria-current={locale === "en" ? "page" : undefined}>EN</a>
            <a href={heHref} hrefLang="he" lang="he" aria-current={locale === "he" ? "page" : undefined}>HE</a>
          </nav>
          <Link className="button button-small" href={href("/downloads")}>{t.nav.download}</Link>
          <details className="nav-disclosure">
            <summary>{t.nav.menu}</summary>
            <div className="nav-panel">
              {links.map((link) => (
                <Link key={link.href} href={link.href} aria-current={link.current ? "page" : undefined}>{link.label}</Link>
              ))}
            </div>
          </details>
        </div>
      </div>
    </header>
  );
}

export function SiteFooter({ locale }: { locale: string }) {
  const t = dictionary(locale);
  const prefix = localePrefix(locale);
  return (
    <footer className="site-footer">
      <div className="shell footer-bar">
        <div>
          <p style={{ margin: "0 0 0.3rem" }}>{t.footer.rights}</p>
          <p style={{ margin: 0 }}>{t.footer.trademark}</p>
        </div>
        <div className="footer-links">
          <Link href={`${prefix}/docs/privacy`}>{t.footer.privacy}</Link>
          <a href="https://github.com/taltol15/vital-os">{t.footer.source}</a>
        </div>
      </div>
    </footer>
  );
}
