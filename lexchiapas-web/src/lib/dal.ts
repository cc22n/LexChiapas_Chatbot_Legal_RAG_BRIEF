import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { readAdminApiKeyFromCookie, SESSION_COOKIE_NAME } from "./adminSession";

// Se llama al inicio de cada Server Component protegido (dashboard/layout.tsx
// y cada page.tsx bajo dashboard/, por si layout.tsx no se re-renderiza en
// una navegacion client-side -- ver la nota "Layouts and auth checks" de la
// guia de auth de Next.js: los checks deben vivir cerca de donde se usan los
// datos, no solo en el layout.
export async function requireAdminApiKey(): Promise<string> {
  const cookieStore = await cookies();
  const adminApiKey = readAdminApiKeyFromCookie(cookieStore.get(SESSION_COOKIE_NAME)?.value);
  if (!adminApiKey) {
    redirect("/login");
  }
  return adminApiKey;
}
