import type { RetrievedChunk } from "@/lib/types";

interface CitationListProps {
  citations: RetrievedChunk[];
}

export function CitationList({ citations }: CitationListProps) {
  if (citations.length === 0) return null;

  return (
    <div className="mt-2 flex flex-col gap-1">
      <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
        Fuentes citadas:
      </span>
      {citations.map((chunk) => (
        <details
          key={chunk.chunk_id}
          className="rounded border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs dark:border-zinc-700 dark:bg-zinc-900"
        >
          <summary className="cursor-pointer font-medium text-zinc-700 dark:text-zinc-300">
            {chunk.document_nombre}
            {chunk.articulo_numero ? `, Articulo ${chunk.articulo_numero}` : ""}
          </summary>
          <p className="mt-1 whitespace-pre-wrap text-zinc-600 dark:text-zinc-400">
            {chunk.content}
          </p>
        </details>
      ))}
    </div>
  );
}
