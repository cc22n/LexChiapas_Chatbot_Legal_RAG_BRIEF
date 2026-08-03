interface EmptyStateProps {
  message: string;
}

// Para metricas que no son "cero" sino "todavia no se mide nada" --
// ej. jailbreak_attempts, que el backend manda en null a proposito porque
// Capa 3 de guardrails no persiste esos intentos todavia. Distinguir esto
// de un 0 real evita que el dashboard sugiera "cero intentos" cuando en
// realidad es "no lo sabemos".
export function EmptyState({ message }: EmptyStateProps) {
  return (
    <div className="flex items-center justify-center rounded-md border border-dashed border-[var(--gridline)] py-6 text-center text-sm text-[var(--text-muted)]">
      {message}
    </div>
  );
}
