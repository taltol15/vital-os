import type { Metadata } from "next";
import { IBM_Plex_Mono, Inter, Noto_Sans_Hebrew } from "next/font/google";
import { headers } from "next/headers";
import { direction } from "@/i18n";
import { siteUrl } from "@/lib/format";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const hebrew = Noto_Sans_Hebrew({ subsets: ["hebrew"], variable: "--font-hebrew", display: "swap", weight: ["400", "500", "600"] });
const plex = IBM_Plex_Mono({ subsets: ["latin"], variable: "--font-plex", display: "swap", weight: ["400", "500"] });

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl()),
  title: { default: "Vital OS", template: "%s · Vital OS" },
  description: "Vital OS is a personal GNOME desktop based on Ubuntu 24.04 LTS. Graphite, ivory, and champagne. Original artwork.",
  applicationName: "Vital OS",
  authors: [{ name: "Vital OS", url: "https://github.com/taltol15/vital-os" }],
  openGraph: {
    type: "website",
    siteName: "Vital OS",
    title: "Vital OS",
    description: "A quiet GNOME desktop. Graphite, ivory, and one champagne accent.",
  },
  twitter: { card: "summary_large_image", title: "Vital OS", description: "A quiet GNOME desktop. Graphite, ivory, and one champagne accent." },
  robots: { index: true, follow: true },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = (await headers()).get("x-vital-locale") === "he" ? "he" : "en";
  return (
    <html lang={locale} dir={direction(locale)} className={`${inter.variable} ${hebrew.variable} ${plex.variable}`}>
      <body>{children}</body>
    </html>
  );
}
