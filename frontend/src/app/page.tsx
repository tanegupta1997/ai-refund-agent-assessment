"use client";

import { useEffect, useRef, useState } from "react";
import { sendChatMessage } from "@/lib/api";
import type { ChatMessage } from "@/types";

const EXAMPLE_PROMPTS = [
  "I'd like a refund for a recent order",
  "My item arrived damaged",
  "I never received my package",
];

function VerdictBadge({ verdict }: { verdict: string }) {
  if (verdict === "approved") {
    return (
      <span className="inline-block mt-2 px-3 py-1 rounded-full text-xs font-medium bg-green-900 text-green-300">
        ✅ Refund Approved
      </span>
    );
  }
  if (verdict === "denied") {
    return (
      <span className="inline-block mt-2 px-3 py-1 rounded-full text-xs font-medium bg-red-900 text-red-300">
        ❌ Refund Denied
      </span>
    );
  }
  if (verdict === "escalated") {
    return (
      <span className="inline-block mt-2 px-3 py-1 rounded-full text-xs font-medium bg-yellow-900 text-yellow-300">
        ⏳ Under Review
      </span>
    );
  }
  return null;
}

function TypingIndicator() {
  return (
    <div className="flex justify-start mb-4">
      <div className="bg-gray-800 rounded-2xl rounded-bl-sm px-4 py-3 flex gap-1 items-center">
        <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]" />
        <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]" />
        <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const time = new Date(message.timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div className={`flex mb-4 ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[80%] ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        <div
          className={`px-4 py-3 ${
            isUser
              ? "bg-blue-600 text-white rounded-2xl rounded-br-sm"
              : "bg-gray-800 text-gray-100 rounded-2xl rounded-bl-sm"
          }`}
        >
          <p className="text-sm whitespace-pre-wrap leading-relaxed">{message.content}</p>
        </div>

        {!isUser && message.verdict && <VerdictBadge verdict={message.verdict} />}

        {!isUser && message.injection_detected && (
          <span className="inline-block mt-1 px-2 py-0.5 rounded text-xs text-gray-500 bg-gray-800">
            🛡️ Security check ran
          </span>
        )}

        <span className="text-xs text-gray-500 mt-1 px-1">{time}</span>
      </div>
    </div>
  );
}

function EmptyState({ onChipClick }: { onChipClick: (text: string) => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 text-center">
      <div className="text-5xl mb-4">💬</div>
      <h2 className="text-xl font-semibold text-white mb-2">
        How can we help you today?
      </h2>
      <p className="text-gray-400 mb-8 text-sm">
        Describe your refund request below
      </p>
      <div className="flex flex-col gap-2 w-full max-w-sm">
        {EXAMPLE_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            onClick={() => onChipClick(prompt)}
            className="text-sm text-gray-300 border border-gray-700 rounded-xl px-4 py-3 hover:bg-gray-800 hover:border-gray-600 transition-colors text-left"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [conversationId, setConversationId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setConversationId(crypto.randomUUID());
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  function resizeTextarea() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 112)}px`; // max ~4 rows
  }

  async function handleSend() {
    const text = inputText.trim();
    if (!text || isLoading) return;

    const userMsg: ChatMessage = {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    setIsLoading(true);
    setIsTyping(true);
    setError(null);

    const history = [...messages, userMsg]
      .slice(-10)
      .map((m) => ({ role: m.role, content: m.content }));

    try {
      const response = await sendChatMessage({
        conversation_id: conversationId,
        message: text,
        conversation_history: history,
      });

      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: response.reply,
        timestamp: new Date().toISOString(),
        verdict: response.verdict,
        refund_request_id: response.refund_request_id,
        injection_detected: response.injection_detected,
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: "Sorry, something went wrong. Please try again.",
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setIsTyping(false);
      setIsLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="flex flex-col h-screen max-w-[720px] mx-auto">
      {/* Header */}
      <header className="flex-none px-4 py-4 border-b border-gray-800 bg-gray-950">
        <div className="flex items-baseline gap-2">
          <span className="text-white font-bold text-lg">🛍️ Support</span>
          <span className="text-gray-400 text-sm">Refund Assistant</span>
        </div>
      </header>

      {/* Message area */}
      <main className="flex-1 overflow-y-auto px-4 py-4 scroll-smooth">
        {messages.length === 0 && !isTyping ? (
          <EmptyState onChipClick={(text) => setInputText(text)} />
        ) : (
          <>
            {messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
            ))}
            {isTyping && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </>
        )}
      </main>

      {/* Error banner */}
      {error && (
        <div className="flex-none px-4 py-2 bg-red-900/50 text-red-300 text-xs text-center">
          {error}
        </div>
      )}

      {/* Input bar */}
      <footer className="flex-none border-t border-gray-800 bg-gray-900 px-4 py-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={inputText}
            onChange={(e) => {
              setInputText(e.target.value);
              resizeTextarea();
            }}
            onKeyDown={handleKeyDown}
            placeholder="Describe your refund request..."
            rows={1}
            disabled={isLoading}
            className="flex-1 resize-none bg-gray-800 text-white placeholder-gray-500 rounded-xl px-4 py-3 text-sm outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 leading-relaxed"
          />
          <button
            onClick={handleSend}
            disabled={isLoading || !inputText.trim()}
            aria-label="Send message"
            className="flex-none w-10 h-10 flex items-center justify-center rounded-xl bg-blue-600 hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors text-white font-bold text-lg"
          >
            ➤
          </button>
        </div>
        <p className="text-xs text-gray-600 mt-2 text-center">
          Enter to send · Shift+Enter for new line
        </p>
      </footer>
    </div>
  );
}
