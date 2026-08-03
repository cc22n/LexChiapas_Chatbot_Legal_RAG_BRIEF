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
      const response = await sendChatMessage(sessionId, text);
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
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
        {messages.map((message) => (
          <ChatMessage key={message.id} message={message} />
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
      <ChatInput onSend={handleSend} disabled={loading || !sessionId} />
      <p className="px-4 pb-3 text-center text-xs text-zinc-400 dark:text-zinc-600">
        <Link href="/explorar" className="hover:underline">
          Explorar relaciones entre leyes
        </Link>
      </p>
    </div>
  );
}
