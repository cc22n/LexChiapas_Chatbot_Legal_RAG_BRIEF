"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ChatInput } from "@/components/ChatInput";
import { ChatMessage } from "@/components/ChatMessage";
import { ApiError, sendChatMessage } from "@/lib/api";
import { getOrCreateSessionId } from "@/lib/session";
import type { ChatMessageData } from "@/lib/types";

const WELCOME_MESSAGE: ChatMessageData = {
  id: "welcome",
  role: "assistant",
  content:
    "Hola, soy LexChiapas. Respondo preguntas sobre leyes y reglamentos del Estado de Chiapas citando la fuente. No doy asesoria legal profesional: para tu caso especifico, consulta a un abogado.",
};

export default function Home() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessageData[]>([WELCOME_MESSAGE]);
  const [loading, setLoading] = useState(false);
  // Switch de registro (idea evaluada en conversacion con Gemini,
  // 2026-08-10): "cotidiano" es el comportamiento historico por defecto,
  // "tecnico" pide lenguaje juridico formal -- ver
  // app.rag.generator._ESTILO_TECNICO/_ESTILO_COTIDIANO en el backend. Vive
  // en memoria (no localStorage): es una preferencia de ESTA sesion de
  // chat, no una configuracion persistente de la cuenta.
  const [technical, setTechnical] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setSessionId(getOrCreateSessionId());
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend(text: string) {
    if (!sessionId) return;

    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: "user", content: text },
    ]);
    setLoading(true);

    try {
      const response = await sendChatMessage(sessionId, text, technical);
      setMessages((prev) => [
        ...prev,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          content: response.answer,
          citations: response.retrieved_chunks,
          messageId: response.message_id,
          grounded: response.grounded,
          outOfScope: response.out_of_scope,
          agentTrace: response.agent_trace,
        },
      ]);
    } catch (err) {
      const content =
        err instanceof ApiError
          ? err.message
          : "Hubo un problema conectando con el servidor. Intenta de nuevo en un momento.";
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), role: "assistant", content, isError: true },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col">
      {/* Encabezado para estructura de landmark/heading; oculto visualmente
          (el chat no necesita un titulo visible) pero anunciado por lectores
          de pantalla. Fase 9.8/A12. */}
      <h1 className="sr-only">Chat de LexChiapas, asistente legal de Chiapas</h1>
      {/* role="log" + aria-live="polite": un lector de pantalla anuncia las
          respuestas nuevas y el estado "Buscando..." (que vive dentro) sin
          robar el foco. Fase 9.8/A12 (WCAG 4.1.3). */}
      <div
        className="flex-1 space-y-3 overflow-y-auto px-4 py-4"
        role="log"
        aria-live="polite"
        aria-relevant="additions"
        aria-busy={loading}
      >
        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} sessionId={sessionId} />
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-zinc-100 px-4 py-2 text-sm text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400">
              Buscando en las leyes de Chiapas...
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="flex items-center justify-center gap-2 px-4 pb-1 text-xs">
        <span className="text-zinc-500 dark:text-zinc-400">Respuestas:</span>
        <div
          role="radiogroup"
          aria-label="Estilo de respuesta"
          className="inline-flex overflow-hidden rounded-full border border-zinc-300 dark:border-zinc-700"
        >
          <button
            type="button"
            role="radio"
            aria-checked={!technical}
            onClick={() => setTechnical(false)}
            className={`px-3 py-1 transition ${
              !technical
                ? "bg-emerald-600 text-white"
                : "bg-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
            }`}
          >
            Cotidiano
          </button>
          <button
            type="button"
            role="radio"
            aria-checked={technical}
            onClick={() => setTechnical(true)}
            className={`px-3 py-1 transition ${
              technical
                ? "bg-emerald-600 text-white"
                : "bg-transparent text-zinc-500 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-200"
            }`}
          >
            Técnico
          </button>
        </div>
      </div>
      <ChatInput onSend={handleSend} disabled={loading || !sessionId} />
      <p className="px-4 pb-3 text-center text-xs text-zinc-400 dark:text-zinc-600">
        <Link href="/explorar" className="hover:underline">
          Explorar relaciones entre leyes
        </Link>
      </p>
    </main>
  );
}
