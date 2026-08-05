import "server-only";
import crypto from "node:crypto";

// Cookie propia del frontend (dominio Next.js), separada de la cookie de
// admin que emite el backend (dominio FastAPI) -- ver adminApi.ts para el
// porque: el Next server hace de BFF y reenvia x-admin-api-key en cada
// fetch server-side al backend, asi que nunca necesitamos que el browser
// tenga una cookie del backend.
export const SESSION_COOKIE_NAME = "lexchiapas_dashboard_session";
export const SESSION_MAX_AGE_SECONDS = 24 * 60 * 60;

const ALGORITHM = "aes-256-gcm";
const IV_LENGTH = 12;

// BUG REAL encontrado (2026-08-04, revision de seguridad): esta cookie
// guardaba el admin_api_key real en base64 + firma HMAC -- la firma
// protege contra manipulacion, pero NO contra lectura: cualquiera con el
// valor crudo de la cookie (captura de logs, backup, una extension de
// browser con acceso a cookies) podia recuperar la API key maestra con solo
// decodificar base64, sin necesidad de romper nada criptografico. Se
// reemplaza la firma HMAC por cifrado autenticado (AES-256-GCM): el GCM
// authTag YA da integridad (reemplaza la firma manual), y ahora el payload
// tambien esta cifrado, asi que el valor de la cookie por si solo no revela
// el admin_api_key sin ADMIN_SESSION_SECRET (un secreto distinto, que nunca
// viaja en la cookie).
function encryptionKey(): Buffer {
  const secret = process.env.ADMIN_SESSION_SECRET;
  if (!secret) {
    throw new Error("ADMIN_SESSION_SECRET no esta configurado (ver .env.local.example)");
  }
  // SHA-256 del secreto para obtener siempre 32 bytes exactos (AES-256),
  // sin importar la longitud del valor que el usuario haya puesto en
  // ADMIN_SESSION_SECRET.
  return crypto.createHash("sha256").update(secret).digest();
}

export function createSessionCookieValue(adminApiKey: string): string {
  const payload = JSON.stringify({ key: adminApiKey, iat: Date.now() });
  const iv = crypto.randomBytes(IV_LENGTH);
  const cipher = crypto.createCipheriv(ALGORITHM, encryptionKey(), iv);
  const ciphertext = Buffer.concat([cipher.update(payload, "utf-8"), cipher.final()]);
  const authTag = cipher.getAuthTag();
  return [iv, ciphertext, authTag].map((buf) => buf.toString("base64url")).join(".");
}

export function readAdminApiKeyFromCookie(cookieValue: string | undefined): string | null {
  if (!cookieValue) return null;
  const parts = cookieValue.split(".");
  if (parts.length !== 3) return null;
  const [ivPart, ciphertextPart, authTagPart] = parts;

  try {
    const iv = Buffer.from(ivPart, "base64url");
    const ciphertext = Buffer.from(ciphertextPart, "base64url");
    const authTag = Buffer.from(authTagPart, "base64url");

    const decipher = crypto.createDecipheriv(ALGORITHM, encryptionKey(), iv);
    decipher.setAuthTag(authTag);
    const payload = Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString("utf-8");

    const data = JSON.parse(payload) as { key: string; iat: number };
    if (Date.now() - data.iat > SESSION_MAX_AGE_SECONDS * 1000) return null;
    return data.key;
  } catch {
    // Incluye fallo de autenticacion GCM (cookie manipulada/corrupta) y
    // cualquier error de parseo -- mismo comportamiento previo: tratar
    // como sesion invalida, nunca lanzar.
    return null;
  }
}
