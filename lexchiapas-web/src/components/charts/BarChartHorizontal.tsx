interface BarDatum {
  label: string;
  value: number;
  colorVar?: string;
}

interface BarChartHorizontalProps {
  data: BarDatum[];
  colorVar?: string;
  valueFormatter?: (value: number) => string;
  emptyMessage?: string;
}

// Barra horizontal de una sola serie: <=24px de grueso (usamos 16px), 4px
// redondeado en la punta (data-end), cuadrada en la base -- mark spec del
// skill dataviz. Una sola serie no lleva leyenda (el titulo de la
// ChartCard ya dice que se grafica); el valor va directo en la punta como
// direct label.
export function BarChartHorizontal({
  data,
  colorVar = "--series-1",
  valueFormatter = (v) => v.toLocaleString("es-MX"),
  emptyMessage = "Sin datos todavia",
}: BarChartHorizontalProps) {
  if (data.length === 0) {
    return <p className="py-4 text-sm text-[var(--text-muted)]">{emptyMessage}</p>;
  }

  const max = Math.max(...data.map((d) => d.value), 1);

  return (
    <ul className="flex flex-col gap-3">
      {data.map((d) => {
        const widthPct = Math.max((d.value / max) * 100, 2);
        return (
          <li key={d.label} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between gap-2 text-xs">
              <span className="truncate text-[var(--text-secondary)]">{d.label}</span>
              <span className="shrink-0 font-medium text-[var(--text-primary)] [font-variant-numeric:tabular-nums]">
                {valueFormatter(d.value)}
              </span>
            </div>
            <div className="h-4 w-full overflow-hidden rounded-sm bg-[var(--gridline)]/40">
              <div
                className="h-4 rounded-r-[4px]"
                style={{ width: `${widthPct}%`, backgroundColor: `var(${d.colorVar ?? colorVar})` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
