"use client";

// Fallback para errores del root layout (Fase 9.8/A11). global-error REEMPLAZA
// el root layout cuando se activa, asi que debe declarar sus propios
// <html>/<body> (Next 16.2). Metadata/generateMetadata no aplican aca (client
// component); se usa el componente <title> de React. Solo se dispara si el
// propio layout raiz falla -- es el ultimo recurso.
export default function GlobalError({
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <html lang="es">
      <body style={{ margin: 0, fontFamily: "system-ui, sans-serif", background: "#fafafa", color: "#18181b" }}>
        <title>Error - LexChiapas</title>
        <main
          style={{
            maxWidth: "42rem",
            margin: "0 auto",
            padding: "4rem 1rem",
            textAlign: "center",
          }}
        >
          <h1 style={{ fontSize: "1.5rem", fontWeight: 600 }}>Algo salio mal</h1>
          <p style={{ marginTop: "0.75rem", fontSize: "0.875rem", color: "#52525b" }}>
            Ocurrio un error inesperado. Intenta recargar la pagina.
          </p>
          <button
            type="button"
            onClick={() => unstable_retry()}
            style={{
              marginTop: "1.5rem",
              borderRadius: "0.375rem",
              background: "#059669",
              color: "#fff",
              border: "none",
              padding: "0.5rem 1rem",
              fontSize: "0.875rem",
              cursor: "pointer",
            }}
          >
            Reintentar
          </button>
        </main>
      </body>
    </html>
  );
}
