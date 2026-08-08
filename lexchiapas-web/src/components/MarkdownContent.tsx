import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownContentProps {
  content: string;
}

// Mapeo manual de componentes en vez del plugin @tailwindcss/typography (que
// requiere configuracion CSS-first adicional en Tailwind v4) -- para el
// rango de markdown que devuelve el LLM (encabezados, negritas, listas,
// separadores, y desde Fase 9 tablas comparativas) esto alcanza sin sumar
// otra dependencia de estilos.
//
// table/thead/tr/th/td (Fase 9, contenido visual): paleta zinc/emerald
// inline, NO las variables --series-N/--surface-1 del sistema de diseno de
// charts/ -- esas solo existen dentro de la clase .viz-root (dashboard y
// /explorar), que esta pagina del chat no tiene; usarlas aca se veria
// transparente/sin color.
const components: Components = {
  h1: ({ children }) => <p className="mt-2 mb-1 text-base font-semibold first:mt-0">{children}</p>,
  h2: ({ children }) => <p className="mt-2 mb-1 text-sm font-semibold first:mt-0">{children}</p>,
  h3: ({ children }) => <p className="mt-2 mb-1 text-sm font-semibold first:mt-0">{children}</p>,
  p: ({ children }) => <p className="my-1 first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-1 list-disc space-y-0.5 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-1 list-decimal space-y-0.5 pl-5">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  hr: () => <hr className="my-2 border-zinc-300 dark:border-zinc-700" />,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="underline">
      {children}
    </a>
  ),
  // La burbuja de chat es max-w-[85%] (ChatMessage.tsx) -- una tabla de 4
  // columnas la desborda en movil sin este scroll horizontal propio.
  table: ({ children }) => (
    <div className="my-2 -mx-1 overflow-x-auto">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="border-b border-zinc-300 dark:border-zinc-600">{children}</thead>
  ),
  tr: ({ children }) => (
    <tr className="border-b border-zinc-200 last:border-0 dark:border-zinc-700">{children}</tr>
  ),
  th: ({ children }) => <th className="px-2 py-1 text-left align-top font-semibold">{children}</th>,
  td: ({ children }) => <td className="px-2 py-1 align-top">{children}</td>,
  del: ({ children }) => <span className="line-through">{children}</span>,
  // No mapeados antes de Fase 9 -- el LLM tiene prohibido explicitamente
  // usar bloques de codigo (ver generator.py _FORMATO_CON_TABLAS), pero si
  // alguno se cuela igual, que se vea como texto plano de la paleta del
  // chat en vez de los estilos default del navegador (monospace con fondo).
  code: ({ children }) => <span>{children}</span>,
  pre: ({ children }) => <div className="whitespace-pre-wrap">{children}</div>,
};

// react-markdown en vez de un parser propio con dangerouslySetInnerHTML: el
// texto viene del LLM (no es contenido nuestro), asi que renderizarlo sin
// poder ejecutar HTML/scripts embebidos es lo que importa aqui, no solo el
// formato visual. remark-gfm (Fase 9): react-markdown v10 es CommonMark
// puro y no parsea tablas GFM sin este plugin -- sin el, el mapeo de
// componentes de tabla de arriba nunca se activaria, el LLM podria mandar
// una tabla perfecta y se veria como texto con pipes crudos.
export function MarkdownContent({ content }: MarkdownContentProps) {
  return (
    <div className="text-sm">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
