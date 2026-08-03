const SESSION_STORAGE_KEY = "lexchiapas_session_id";

export function getOrCreateSessionId(): string {
  const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) return existing;

  const sessionId = crypto.randomUUID();
  window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  return sessionId;
}
