import Link from "next/link";

// Pagina 404 (Fase 9.8/A11). Server component sin props (convencion Next 16).
// Reemplaza la pantalla cruda de Next para rutas inexistentes.
export default function NotFound() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-4 py-16 text-center">
      <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
        Pagina no encontrada
      </h1>
      <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
        La pagina que buscas no existe o cambio de direccion.
      </p>
      <Link
        href="/"
        className="mt-6 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
      >
        Volver al inicio
      </Link>
    </main>
  );
}
