import "server-only";
import crypto from "node:crypto";

// Cookie propia del frontend (dominio Next.js), separada de la cookie de
// admin que emite el backend (dominio FastAPI) -- ver adminApi.ts para el
// porque: el Next server hace de BFF y reenvia x-admin-api-key en cada
// fetch server-side al backend, asi que nunca necesitamos que el browser
// tenga una cookie del backend.
export const SESSION_COOKIE_NAME = "lexchiapas_dashboard_session";
export const SESSION_MAX_AGE_SECONDS = 24 * 60 * 60;

function signingSecret(): string {
  const secret = process.env.ADMIN_SESSION_SECRET;
  if (!secret) {
    throw new Error("ADMIN_SESSION_SECRET no esta configurado (ver .env.local.example)");
  }
  return secret;
}

function sign(payload: string): string {
  return crypto.createHmac("sha256", signingSecret()).update(payload).digest("hex");
}

export function createSessionCookieValue(adminApiKey: string): string {
  const payload = Buffer.from(JSON.stringify({ key: adminApiKey, iat: Date.now() })).toString("base64url");
  return `${payload}.${sign(payload)}`;
}

export function readAdminApiKeyFromCookie(cookieValue: string | undefined): string | null {
  if (!cookieValue) return null;
  const [payload, signature] = cookieValue.split(".");
  if (!payload || !signature) return null;

  const expected = sign(payload);
  const signatureBuf = Buffer.from(signature);
  const expectedBuf = Buffer.from(expected);
  if (signatureBuf.length !== expectedBuf.length || !crypto.timingSafeEqual(signatureBuf, expectedBuf)) {
    return null;
  }

  try {
    const data = JSON.parse(Buffer.from(payload, "base64url").toString("utf-8")) as {
      key: string;
      iat: number;
    };
    if (Date.now() - data.iat > SESSION_MAX_AGE_SECONDS * 1000) return null;
    return data.key;
  } catch {
    return null;
  }
}
