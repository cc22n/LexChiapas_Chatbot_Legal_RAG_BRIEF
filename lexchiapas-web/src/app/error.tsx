"use client";

// Error boundary de segmento (Fase 9.8/A11). Next 16.2: el prop de
// recuperacion es `unstable_retry` (no `reset`); debe ser client component.
// No se muestra error.message crudo (los errores de Server Components vienen
// genericos en prod, y volcar detalles internos no aporta al usuario).
export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-4 py-16 text-center">
      <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
        Algo salio mal
      </h1>
      <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
        Ocurrio un error inesperado al procesar tu solicitud. Puedes reintentar;
        si el problema persiste, vuelve a intentar en unos minutos.
      </p>
      {error.digest ? (
        <p className="mt-2 text-xs text-zinc-400 dark:text-zinc-500">
          Referencia: {error.digest}
        </p>
      ) : null}
      <button
        type="button"
        onClick={() => unstable_retry()}
        className="mt-6 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
      >
        Reintentar
      </button>
    </main>
  );
}
