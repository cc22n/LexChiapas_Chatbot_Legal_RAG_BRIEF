interface SeriesSpec {
  key: string;
  label: string;
  colorVar: string;
}

interface LineChartPoint {
  x: string;
  values: Record<string, number | null>;
}

interface LineChartProps {
  /** Debe venir ordenado cronologicamente ascendente (el caller invierte el DESC que manda el backend). */
  data: LineChartPoint[];
  series: SeriesSpec[];
  formatValue?: (value: number) => string;
  formatX?: (x: string) => string;
  emptyMessage?: string;
}

const WIDTH = 640;
const HEIGHT = 220;
const PADDING_LEFT = 40;
const PADDING_RIGHT = 12;
const PADDING_TOP = 12;
const PADDING_BOTTOM = 28;
const PLOT_W = WIDTH - PADDING_LEFT - PADDING_RIGHT;
const PLOT_H = HEIGHT - PADDING_TOP - PADDING_BOTTOM;

function niceMax(value: number): number {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const steps = [1, 2, 2.5, 5, 10];
  for (const step of steps) {
    const candidate = step * magnitude;
    if (candidate >= value) return candidate;
  }
  return 10 * magnitude;
}

function defaultFormatX(x: string): string {
  const d = new Date(x);
  if (Number.isNaN(d.getTime())) return x;
  return d.toLocaleDateString("es-MX", { day: "2-digit", month: "2-digit" });
}

// Grafica de lineas multi-serie a mano en SVG (sin libreria), siguiendo los
// mark specs del skill dataviz: linea 2px, marcador final >=8px con anillo
// de superficie de 2px, gridlines hairline, leyenda solo si hay 2+ series,
// direct label al final de cada linea (nunca el texto con el color de la
// serie -- la identidad la lleva el punto/swatch, no el texto).
export function LineChart({
  data,
  series,
  formatValue = (v) => v.toLocaleString("es-MX"),
  formatX = defaultFormatX,
  emptyMessage = "Sin datos todavia",
}: LineChartProps) {
  if (data.length === 0) {
    return <p className="py-4 text-sm text-[var(--text-muted)]">{emptyMessage}</p>;
  }

  const allValues = data.flatMap((d) => series.map((s) => d.values[s.key]).filter((v): v is number => v != null));
  const yMax = niceMax(Math.max(...allValues, 0));
  const yTicks = [0, yMax * 0.25, yMax * 0.5, yMax * 0.75, yMax];

  const xAt = (i: number) => (data.length === 1 ? PADDING_LEFT : PADDING_LEFT + (i / (data.length - 1)) * PLOT_W);
  const yAt = (value: number) => PADDING_TOP + PLOT_H - (value / yMax) * PLOT_H;

  const xLabelIndexes =
    data.length <= 6 ? data.map((_, i) => i) : [0, Math.floor((data.length - 1) / 2), data.length - 1];

  return (
    <div>
      {series.length >= 2 && (
        <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--text-secondary)]">
          {series.map((s) => (
            <li key={s.key} className="flex items-center gap-1.5">
              <span
                className="inline-block h-2 w-2 rounded-full"
                style={{ backgroundColor: `var(${s.colorVar})` }}
              />
              {s.label}
            </li>
          ))}
        </ul>
      )}
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" role="img" aria-label="Serie de tiempo">
        {yTicks.map((tick) => (
          <g key={tick}>
            <line
              x1={PADDING_LEFT}
              x2={WIDTH - PADDING_RIGHT}
              y1={yAt(tick)}
              y2={yAt(tick)}
              stroke="var(--gridline)"
              strokeWidth={1}
            />
            <text
              x={PADDING_LEFT - 8}
              y={yAt(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={10}
              fill="var(--text-muted)"
            >
              {Math.round(tick).toLocaleString("es-MX")}
            </text>
          </g>
        ))}

        {xLabelIndexes.map((i) => (
          <text
            key={i}
            x={xAt(i)}
            y={HEIGHT - PADDING_BOTTOM + 16}
            textAnchor="middle"
            fontSize={10}
            fill="var(--text-muted)"
          >
            {formatX(data[i].x)}
          </text>
        ))}

        {series.map((s) => {
          const points = data
            .map((d, i) => {
              const v = d.values[s.key];
              return v == null ? null : `${xAt(i)},${yAt(v)}`;
            })
            .filter((p): p is string => p != null);
          if (points.length === 0) return null;

          const lastIndex = data.findLastIndex((d) => d.values[s.key] != null);
          const lastValue = lastIndex >= 0 ? data[lastIndex].values[s.key] : null;

          return (
            <g key={s.key}>
              <polyline
                points={points.join(" ")}
                fill="none"
                stroke={`var(${s.colorVar})`}
                strokeWidth={2}
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              {lastIndex >= 0 && lastValue != null && (
                <>
                  <circle
                    cx={xAt(lastIndex)}
                    cy={yAt(lastValue)}
                    r={4}
                    fill={`var(${s.colorVar})`}
                    stroke="var(--surface-1)"
                    strokeWidth={2}
                  />
                  <text
                    x={Math.min(xAt(lastIndex) + 6, WIDTH - PADDING_RIGHT - 2)}
                    y={yAt(lastValue)}
                    textAnchor={xAt(lastIndex) + 6 > WIDTH - PADDING_RIGHT - 2 ? "end" : "start"}
                    dominantBaseline="middle"
                    fontSize={10}
                    fill="var(--text-secondary)"
                  >
                    {formatValue(lastValue)}
                  </text>
                </>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
