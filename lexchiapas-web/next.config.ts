import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  // Este equipo resuelve "localhost" a ::1 (IPv6) primero (ver
  // web_dev_environment_gotchas), por eso el frontend/pruebas siempre usan
  // 127.0.0.1 -- Next.js 16 bloquea por defecto requests dev cross-origin
  // que no vengan de "localhost", asi que hay que declarar 127.0.0.1
  // explicitamente o las rutas /api/* devuelven 404 en vez de ejecutarse.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
