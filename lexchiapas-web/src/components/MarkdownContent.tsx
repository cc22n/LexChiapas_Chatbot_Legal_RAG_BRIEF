import ReactMarkdown, { type Components } from "react-markdown";

interface MarkdownContentProps {
  content: string;
}

// Mapeo manual de componentes en vez del plugin @tailwindcss/typography (que
// requiere configuracion CSS-first adicional en Tailwind v4) -- para el
// rango de markdown que devuelve el LLM (encabezados, negritas, listas,
// separadores) esto alcanza sin sumar otra dependencia.
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
};

// react-markdown en vez de un parser propio con dangerouslySetInnerHTML: el
// texto viene del LLM (no es contenido nuestro), asi que renderizarlo sin
// poder ejecutar HTML/scripts embebidos es lo que importa aqui, no solo el
// formato visual.
export function MarkdownContent({ content }: MarkdownContentProps) {
  return (
    <div className="text-sm">
      <ReactMarkdown components={components}>{content}</ReactMarkdown>
    </div>
  );
}
