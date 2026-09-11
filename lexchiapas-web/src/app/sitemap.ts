import type { MetadataRoute } from "next";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000";

// Fase 9.8/A12: solo rutas PUBLICAS indexables. /dashboard y /login quedan
// fuera (privados) -- consistente con el Disallow de robots.ts.
export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return ["/", "/explorar", "/privacidad", "/terminos"].map((path) => ({
    url: `${SITE_URL}${path}`,
    lastModified: now,
    changeFrequency: "monthly",
    priority: path === "/" ? 1 : 0.6,
  }));
}
