import type { NextConfig } from "next";

// Fase 9.8/A4: headers de seguridad para todas las rutas. Se incluyen los de
// alto valor y bajo riesgo (anti-clickjacking, anti-sniffing, HSTS,
// Referrer/Permissions-Policy). NO se pone Content-Security-Policy aca a
// proposito: una CSP estricta en Next.js requiere nonces por request via
// middleware (ver node_modules/next/dist/docs/01-app/02-guides/
// content-security-policy.md), o rompe los scripts/estilos inline que Next
// inyecta para hidratacion -- se deja como follow-up del Bloque 1 para
// hacerlo bien con nonce, en vez de un 'unsafe-inline' que no aporta.
const SECURITY_HEADERS = [
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

const nextConfig: NextConfig = {
  /* config options here */
  // Este equipo resuelve "localhost" a ::1 (IPv6) primero (ver
  // web_dev_environment_gotchas), por eso el frontend/pruebas siempre usan
  // 127.0.0.1 -- Next.js 16 bloquea por defecto requests dev cross-origin
  // que no vengan de "localhost", asi que hay que declarar 127.0.0.1
  // explicitamente o las rutas /api/* devuelven 404 en vez de ejecutarse.
  allowedDevOrigins: ["127.0.0.1"],
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
