interface StatTileProps {
  label: string;
  value: string;
  delta?: {
    text: string;
    direction: "up" | "down";
    good: boolean;
  };
}

// Contrato de figura del skill dataviz: label en sentence case sin dos
// puntos, value en cifras proporcionales (nunca tabular-nums a este tamano),
// delta opcional con color = direccion x si "arriba" es bueno aqui.
export function StatTile({ label, value, delta }: StatTileProps) {
  const deltaColor = delta
    ? delta.good
      ? "text-[var(--status-good)]"
      : "text-[var(--status-critical)]"
    : "";

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-4">
      <p className="text-xs text-[var(--text-secondary)]">{label}</p>
      <p className="mt-1 text-3xl font-semibold text-[var(--text-primary)]">{value}</p>
      {delta && (
        <p className={`mt-1 text-xs font-medium ${deltaColor}`}>
          {delta.direction === "up" ? "↑" : "↓"} {delta.text}
        </p>
      )}
    </div>
  );
}
