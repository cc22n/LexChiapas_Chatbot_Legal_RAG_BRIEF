import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { verifyAdminApiKey } from "@/lib/adminApi";
import { createSessionCookieValue, SESSION_COOKIE_NAME, SESSION_MAX_AGE_SECONDS } from "@/lib/adminSession";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const adminApiKey = typeof body?.admin_api_key === "string" ? body.admin_api_key.trim() : "";
  if (!adminApiKey) {
    return NextResponse.json({ error: "admin_api_key requerido" }, { status: 422 });
  }

  const valid = await verifyAdminApiKey(adminApiKey);
  if (!valid) {
    return NextResponse.json({ error: "Clave de administrador invalida" }, { status: 401 });
  }

  const cookieStore = await cookies();
  cookieStore.set(SESSION_COOKIE_NAME, createSessionCookieValue(adminApiKey), {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: SESSION_MAX_AGE_SECONDS,
    path: "/",
  });

  return NextResponse.json({ ok: true });
}
