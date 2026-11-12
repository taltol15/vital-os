import Image from "next/image";
import Link from "next/link";
import type { Metadata } from "next";
import { dictionary } from "@/i18n";
import { Mark } from "@/components/site";
import { fill, localePrefix, siteUrl } from "@/lib/format";
import { recommendedRelease } from "@/lib/store";

export async function generateMetadata({ params }: { params: Promise<{ locale: string }> }): Promise<Metadata> {
  const { locale } = await params;
  const prefix = localePrefix(locale);
  return {
    alternates: {
      canonical: `${siteUrl()}${prefix || "/"}`,
      languages: { en: siteUrl(), he: `${siteUrl()}/he` },
    },
  };
}

export default async function HomePage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const t = dictionary(locale);
  const prefix = localePrefix(locale);
  const release = await recommendedRelease();
  const version = release?.version ?? "0.2.1";
  const vars = { version };
  return (
    <>
      <div className="shell">
        <section className="hero">
          <div>
            <p className="eyebrow">{fill(t.hero.eyebrow, vars)}</p>
            <h1>{t.hero.title}</h1>
            <p className="lede">{t.hero.lede}</p>
            <div className="hero-actions">
              <Link className="button" href={`${prefix}/downloads`}>{fill(t.hero.primary, vars)}</Link>
              <Link className="button button-ghost" href={`${prefix}/docs/getting-started`}>{t.hero.secondary}</Link>
            </div>
            <p className="meta-line">{t.hero.meta}</p>
          </div>
          <Mark />
        </section>
        <figure className="shot">
          <Image
            src="/screenshots/desktop.png"
            alt={t.desktop.alt}
            width={1920}
            height={1080}
            priority
            sizes="(min-width: 960px) 1120px, 100vw"
          />
          <figcaption>{t.desktop.caption}</figcaption>
        </figure>
        <section className="section">
          <p className="kicker">{t.features.eyebrow}</p>
          <h2>{t.features.title}</h2>
          <div className="feature-grid">
            {t.features.items.map((item, index) => (
              <article className="card" key={item.title}>
                <p className="index">0{index + 1}</p>
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="section split">
          <div>
            <p className="kicker">{t.assistant.eyebrow}</p>
            <h2>{t.assistant.title}</h2>
            <p className="lede">{t.assistant.lede}</p>
            {t.assistant.points.map((point) => (
              <div className="point" key={point.title}>
                <h3>{point.title}</h3>
                <p>{point.body}</p>
              </div>
            ))}
          </div>
          <div className="terminal">
            <p className="kicker">{t.assistant.terminalLabel}</p>
            <pre>
              <span className="prompt">$ </span>vital ask &quot;how do I see listening ports&quot;{"\n"}
              ss -lptn{"\n"}
              Lists listening sockets.{"\n"}
              Run it? [y/N]
            </pre>
          </div>
        </section>
        <section className="section privacy-grid">
          <div>
            <p className="kicker">{t.privacy.eyebrow}</p>
            <h2>{t.privacy.title}</h2>
            <p className="lede">{t.privacy.lede}</p>
            <p><Link href={`${prefix}/docs/privacy`}>{t.privacy.link}</Link></p>
          </div>
          <dl>
            {t.privacy.rows.map((row) => (
              <div className="pair" key={row.term}>
                <dt>{row.term}</dt>
                <dd>{row.detail}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section className="section">
          <p className="kicker">{t.gallery.eyebrow}</p>
          <h2>{t.gallery.title}</h2>
          <div className="gallery">
            {t.gallery.items.map((item) => (
              <figure className="shot" key={item.src}>
                <Image src={item.src} alt={item.alt} width={item.width} height={item.height} sizes="(min-width: 960px) 360px, 100vw" />
                <figcaption>{item.caption}</figcaption>
              </figure>
            ))}
          </div>
        </section>
        <section className="band">
          <div>
            <h2>{t.cta.title}</h2>
            <p className="lede">{t.cta.lede}</p>
          </div>
          <div className="hero-actions">
            {/* Full navigation so the counter runs and the browser follows the redirect. */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a className="button" href="/api/v1/downloads/iso">{t.cta.button}</a>
            <Link className="button button-ghost" href={`${prefix}/downloads`}>{t.cta.secondary}</Link>
          </div>
        </section>
      </div>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify({
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            name: "Vital OS",
            applicationCategory: "OperatingSystem",
            operatingSystem: "Linux",
            softwareVersion: version,
            offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
            downloadUrl: `${siteUrl()}/downloads`,
          }),
        }}
      />
    </>
  );
}
