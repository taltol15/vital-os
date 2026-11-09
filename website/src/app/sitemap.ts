import type { MetadataRoute } from "next";
import { listDocs } from "@/lib/docs";
import { siteUrl } from "@/lib/format";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = siteUrl();
  const paths = ["", "/downloads", "/contact", "/docs", ...listDocs("en").map((doc) => `/docs/${doc.slug}`)];
  return paths.flatMap((path) => [
    {
      url: `${base}${path || "/"}`,
      lastModified: new Date("2026-10-05"),
      alternates: { languages: { en: `${base}${path || "/"}`, he: `${base}/he${path}` } },
    },
  ]);
}
