import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Aviso de privacidad - LexChiapas",
  description:
    "Que datos recopila LexChiapas, con que finalidad, por cuanto tiempo y como ejercer tus derechos ARCO.",
};

// Fase 9.8/C7: aviso de privacidad minimo. El bot persiste conversaciones de
// ciudadanos (tabla messages/conversations), lo que activa obligaciones bajo
// la LFPDPPP -- antes no habia ninguna pagina legal. Contenido informativo;
// los datos entre corchetes los completa el responsable antes de publicar.
export default function PrivacidadPage() {
  return (
    <main className="mx-auto w-full max-w-2xl flex-1 px-4 py-10">
      <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">
        Aviso de privacidad
      </h1>
      <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
        Ultima actualizacion: septiembre de 2026
      </p>

      <div className="mt-6 space-y-6 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
        <section>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Que datos recopilamos
          </h2>
          <p className="mt-2">
            LexChiapas guarda el contenido de las conversaciones que mantienes con
            el asistente (tus preguntas y las respuestas generadas) y un
            identificador de sesion tecnico que permite dar continuidad a la
            conversacion. No pedimos ni requerimos tu nombre, correo, telefono ni
            ningun dato que te identifique personalmente para usar el chat.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Con que finalidad
          </h2>
          <p className="mt-2">
            Usamos esos datos unicamente para operar y mejorar el asistente:
            responder tus preguntas, medir la calidad de las respuestas y detectar
            fallas. No vendemos ni compartimos tus conversaciones con terceros con
            fines comerciales.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Terceros que procesan datos
          </h2>
          <p className="mt-2">
            Para generar las respuestas, el texto de tu pregunta se envia a
            proveedores de modelos de lenguaje (por ejemplo NVIDIA NIM y otros
            proveedores de respaldo) que lo procesan para producir la respuesta.
            No les enviamos datos que te identifiquen, solo el texto necesario para
            responder.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Por cuanto tiempo
          </h2>
          <p className="mt-2">
            Conservamos las conversaciones el tiempo necesario para los fines
            anteriores. Puedes solicitar que eliminemos las conversaciones
            asociadas a tu sesion escribiendo al contacto de abajo.
          </p>
        </section>

        <section>
          <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-100">
            Tus derechos y contacto
          </h2>
          <p className="mt-2">
            Puedes solicitar el acceso, rectificacion, cancelacion u oposicion
            (derechos ARCO) sobre tus datos, o hacer cualquier consulta de
            privacidad, escribiendo a{" "}
            <span className="font-medium text-zinc-900 dark:text-zinc-100">
              [correo de contacto del responsable]
            </span>
            .
          </p>
        </section>

        <section className="rounded-md border border-amber-200 bg-amber-50 p-4 text-amber-900 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-200">
          LexChiapas es una herramienta informativa y no sustituye la asesoria de
          un abogado. Las respuestas pueden contener errores; verifica siempre la
          fuente oficial de la ley.
        </section>
      </div>

      <div className="mt-8 text-sm">
        <Link href="/" className="text-blue-600 hover:underline dark:text-blue-400">
          &larr; Volver al inicio
        </Link>
        <span className="mx-2 text-zinc-400">|</span>
        <Link href="/terminos" className="text-blue-600 hover:underline dark:text-blue-400">
          Terminos de uso
        </Link>
      </div>
    </main>
  );
}
