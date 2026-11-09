import type { MetadataRoute } from "next";
import { siteUrl } from "@/lib/format";

export default function robots(): MetadataRoute.Robots {
  const base = siteUrl();
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/mgmt", "/api/"] },
    sitemap: `${base}/sitemap.xml`,
    host: base,
  };
}
