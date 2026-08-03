import type { ReactNode } from "react";

interface Column {
  key: string;
  label: string;
}

interface ChartCardProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  /** Filas para la vista de tabla (el gemelo accesible de toda grafica). */
  tableColumns?: Column[];
  tableRows?: Record<string, ReactNode>[];
}

// Cada grafica vive dentro de este <figure>: titulo + subtitulo, el cuerpo
// (SVG/HTML de la grafica), y un <details> nativo con la tabla equivalente
// -- el "table-view toggle" que pide el skill dataviz como gemelo de
// accesibilidad de toda grafica. Sin JS, igual que CitationList.tsx.
export function ChartCard({ title, subtitle, children, tableColumns, tableRows }: ChartCardProps) {
  return (
    <figure className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <figcaption className="mb-3">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>
        {subtitle && <p className="text-xs text-[var(--text-secondary)]">{subtitle}</p>}
      </figcaption>
      {children}
      {tableColumns && tableRows && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
            Ver como tabla
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr>
                  {tableColumns.map((col) => (
                    <th
                      key={col.key}
                      className="border-b border-[var(--gridline)] px-2 py-1 font-medium text-[var(--text-secondary)]"
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {tableRows.map((row, i) => (
                  <tr key={i}>
                    {tableColumns.map((col) => (
                      <td
                        key={col.key}
                        className="border-b border-[var(--gridline)] px-2 py-1 text-[var(--text-primary)] [font-variant-numeric:tabular-nums]"
                      >
                        {row[col.key]}
                      </td>
                    ))}
                  </tr>
                ))}
                {tableRows.length === 0 && (
                  <tr>
                    <td colSpan={tableColumns.length} className="px-2 py-2 text-[var(--text-muted)]">
                      Sin datos
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </figure>
  );
}
