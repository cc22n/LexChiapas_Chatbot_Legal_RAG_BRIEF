interface Column {
  key: string;
  label: string;
  align?: "left" | "right";
}

interface DataTableProps {
  columns: Column[];
  rows: Record<string, React.ReactNode>[];
  emptyMessage?: string;
}

// Tabla simple para datos que no son series/comparaciones (errores de
// ingestion, etc.) -- columnas numericas usan tabular-nums para que
// alineen verticalmente, per el skill dataviz.
export function DataTable({ columns, rows, emptyMessage = "Sin datos todavia" }: DataTableProps) {
  if (rows.length === 0) {
    return <p className="py-4 text-sm text-[var(--text-muted)]">{emptyMessage}</p>;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-xs">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                className={`border-b border-[var(--gridline)] px-2 py-1.5 font-medium text-[var(--text-secondary)] ${
                  col.align === "right" ? "text-right" : "text-left"
                }`}
              >
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => (
                <td
                  key={col.key}
                  className={`border-b border-[var(--gridline)] px-2 py-1.5 text-[var(--text-primary)] [font-variant-numeric:tabular-nums] ${
                    col.align === "right" ? "text-right" : "text-left"
                  }`}
                >
                  {row[col.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
