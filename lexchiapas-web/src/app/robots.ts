import type { MetadataRoute } from "next";

// URL publica del sitio. Se toma de NEXT_PUBLIC_SITE_URL (definirla en el
// deploy, ver .env.local.example); fallback local para dev.
const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

// Fase 9.8/A12: robots.txt generado. El dashboard y el login (privados) NO
// deben indexarse; el resto (chat, explorar, paginas legales) si.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/dashboard", "/login"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
