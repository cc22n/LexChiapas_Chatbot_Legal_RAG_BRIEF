import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Terminos de uso - LexChiapas",
  description:
    "Condiciones de uso de LexChiapas: caracter informativo, limitaciones y responsabilidad.",
};

// Fase 9.8/C7: terminos de uso minimos, complementan el aviso de privacidad.
export default function TerminosPage() {
  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-10">
      <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
        Terminos de uso
      </h1>
      <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
        Ultima actualizacion: septiembre de 2026
      </p>

      <div className="mt-6 space-y-6 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
        <section>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Que es LexChiapas
          </h2>
          <p className="mt-2">
            LexChiapas es un asistente informativo que responde preguntas sobre
            leyes y reglamentos del Estado de Chiapas, citando la ley y el
            articulo cuando encuentra fundamento. Es un proyecto de caracter
            educativo e informativo.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            No es asesoria legal
          </h2>
          <p className="mt-2">
            LexChiapas no sustituye la asesoria de un abogado ni constituye una
            opinion juridica profesional. Las respuestas se generan de forma
            automatica y pueden contener errores, estar desactualizadas o no
            aplicar a tu caso concreto. Antes de tomar cualquier decision con
            efectos legales, consulta la fuente oficial de la ley y a un
            profesional.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Uso aceptable
          </h2>
          <p className="mt-2">
            Te comprometes a usar el servicio de buena fe, sin intentar
            vulnerarlo, sobrecargarlo, ni emplearlo para fines ilicitos. Podemos
            limitar la frecuencia de uso para mantener el servicio disponible para
            todos.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Limitacion de responsabilidad
          </h2>
          <p className="mt-2">
            El servicio se ofrece &ldquo;tal cual&rdquo;, sin garantias sobre la
            exactitud o disponibilidad. No nos hacemos responsables por decisiones
            tomadas con base en las respuestas del asistente.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Privacidad
          </h2>
          <p className="mt-2">
            El tratamiento de tus datos se rige por nuestro{" "}
            <Link href="/privacidad" className="text-blue-600 hover:underline dark:text-blue-400">
              aviso de privacidad
            </Link>
            .
          </p>
        </section>
      </div>

      <div className="mt-8 text-sm">
        <Link href="/" className="text-blue-600 hover:underline dark:text-blue-400">
          &larr; Volver al inicio
        </Link>
        <span className="mx-2 text-zinc-400">|</span>
        <Link href="/privacidad" className="text-blue-600 hover:underline dark:text-blue-400">
          Aviso de privacidad
        </Link>
      </div>
    </main>
  );
}
