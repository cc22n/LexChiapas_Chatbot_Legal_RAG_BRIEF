"use client";

import { useState } from "react";
import { ApiError, sendFeedback } from "@/lib/api";
import type { ChatMessageData, FeedbackRating } from "@/lib/types";
import { CitationList } from "./CitationList";
import { MarkdownContent } from "./MarkdownContent";
import { TraceAccordion } from "./TraceAccordion";

interface ChatMessageProps {
  message: ChatMessageData;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const [rating, setRating] = useState<FeedbackRating | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const isUser = message.role === "user";

  async function handleFeedback(newRating: FeedbackRating) {
    if (rating || message.messageId === undefined) return;
    setRating(newRating);
    setFeedbackError(null);
    try {
      await sendFeedback(message.messageId, newRating);
    } catch (err) {
      setRating(null);
      setFeedbackError(err instanceof ApiError ? err.message : "No se pudo enviar tu feedback.");
    }
  }

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm ${
          isUser
            ? "bg-emerald-600 text-white"
            : message.isError
              ? "bg-red-50 text-red-800 dark:bg-red-950 dark:text-red-200"
              : "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
        }`}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <MarkdownContent content={message.content} />
        )}

        {!isUser && message.citations && message.grounded && (
          <CitationList citations={message.citations} />
        )}

        {!isUser && <TraceAccordion trace={message.agentTrace} />}

        {!isUser && message.messageId !== undefined && !message.isError && (
          <div className="mt-2 flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
            {rating ? (
              <span>Gracias por tu feedback.</span>
            ) : (
              <>
                <span>Te sirvio esta respuesta?</span>
                <button
                  type="button"
                  onClick={() => handleFeedback("util")}
                  className="rounded px-2 py-0.5 hover:bg-zinc-200 dark:hover:bg-zinc-700"
                >
                  Si
                </button>
                <button
                  type="button"
                  onClick={() => handleFeedback("no_util")}
                  className="rounded px-2 py-0.5 hover:bg-zinc-200 dark:hover:bg-zinc-700"
                >
                  No
                </button>
              </>
            )}
            {feedbackError && <span className="text-red-500">{feedbackError}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
