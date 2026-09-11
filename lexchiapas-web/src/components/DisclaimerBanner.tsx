import Link from "next/link";

export function DisclaimerBanner() {
  return (
    <div className="w-full border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
      LexChiapas es informativo y no sustituye la asesoria de un abogado. Responde
      unicamente sobre leyes y reglamentos del Estado de Chiapas.{" "}
      <Link href="/privacidad" className="underline hover:no-underline">
        Aviso de privacidad
      </Link>{" "}
      &middot;{" "}
      <Link href="/terminos" className="underline hover:no-underline">
        Terminos
      </Link>
    </div>
  );
}
