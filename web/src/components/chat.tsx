"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { sendMessage, resetChat } from "@/lib/api";
import { ScrollArea } from "@/components/ui/scroll-area";

interface Message {
  role: "user" | "assistant";
  content: string;
}

const SUGGESTIONS = [
  "What zoning types are available in the county?",
  "Show me residential zones near downtown",
  "What are the land use restrictions for zone R-1?",
  "Which parcels were rezoned in the last year?",
];

export function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const mutation = useMutation({
    mutationFn: sendMessage,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response },
      ]);
    },
  });

  const submitMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || mutation.isPending) return;

      setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
      setInput("");
      mutation.mutate({ message: trimmed, session_id: sessionId });
    },
    [mutation, sessionId]
  );

  const handleSubmit = useCallback(() => {
    submitMessage(input);
  }, [input, submitMessage]);

  const handleReset = useCallback(async () => {
    if (sessionId) await resetChat(sessionId);
    setMessages([]);
    setSessionId(null);
  }, [sessionId]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        Math.min(textareaRef.current.scrollHeight, 160) + "px";
    }
  }, [input]);

  return (
    <div className="flex h-dvh flex-col bg-background">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border/50 px-6 py-4">
        <h1 className="text-sm font-medium tracking-tight text-foreground">
          County GIS Chat
        </h1>
        {messages.length > 0 && (
          <button
            onClick={handleReset}
            className="text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            New chat
          </button>
        )}
      </header>

      {/* Messages */}
      <ScrollArea className="flex-1">
        <div className="mx-auto max-w-2xl px-6">
          {messages.length === 0 ? (
            <div className="flex h-[60vh] flex-col items-center justify-center">
              <div className="text-center">
                <h2 className="text-lg font-medium tracking-tight text-foreground">
                  County GIS Assistant
                </h2>
                <p className="mt-2 text-sm text-muted-foreground">
                  Ask questions about county zoning and GIS data.
                </p>
              </div>
              <div className="mt-8 grid w-full max-w-md grid-cols-1 gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => submitMessage(s)}
                    className="rounded-lg border border-border/60 px-4 py-3 text-left text-[13px] leading-snug text-muted-foreground transition-colors hover:border-border hover:bg-muted/50 hover:text-foreground"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="py-8 space-y-6">
              {messages.map((msg, i) => (
                <div key={i} className="flex gap-4">
                  <div
                    className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-medium ${
                      msg.role === "user"
                        ? "bg-foreground text-background"
                        : "bg-muted text-muted-foreground"
                    }`}
                  >
                    {msg.role === "user" ? "Y" : "A"}
                  </div>
                  <div className="min-w-0 pt-0.5">
                    <p className="text-xs font-medium text-muted-foreground mb-1.5">
                      {msg.role === "user" ? "You" : "Assistant"}
                    </p>
                    <div className="text-sm leading-relaxed text-foreground whitespace-pre-wrap break-words">
                      {msg.content}
                    </div>
                  </div>
                </div>
              ))}

              {mutation.isPending && (
                <div className="flex gap-4">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium text-muted-foreground">
                    A
                  </div>
                  <div className="pt-0.5">
                    <p className="text-xs font-medium text-muted-foreground mb-1.5">
                      Assistant
                    </p>
                    <div className="flex items-center gap-1.5 pt-1">
                      <span className="h-1 w-1 animate-pulse rounded-full bg-muted-foreground/40" />
                      <span className="h-1 w-1 animate-pulse rounded-full bg-muted-foreground/40 [animation-delay:150ms]" />
                      <span className="h-1 w-1 animate-pulse rounded-full bg-muted-foreground/40 [animation-delay:300ms]" />
                    </div>
                  </div>
                </div>
              )}

              {mutation.isError && (
                <div className="ml-11 text-sm text-destructive">
                  Failed to send message. Please try again.
                </div>
              )}

              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input */}
      <div className="border-t border-border/50 px-6 py-4">
        <div className="mx-auto max-w-2xl">
          <div className="relative flex items-end rounded-2xl border border-border bg-muted/30 transition-colors focus-within:border-foreground/20 focus-within:bg-background">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question..."
              rows={1}
              className="min-h-[48px] flex-1 resize-none bg-transparent px-4 py-3.5 text-sm leading-normal text-foreground placeholder:text-muted-foreground/70 focus:outline-none"
            />
            <button
              onClick={handleSubmit}
              disabled={!input.trim() || mutation.isPending}
              className="m-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-foreground text-background transition-opacity hover:opacity-80 disabled:opacity-30"
              aria-label="Send message"
            >
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M8 12V4M8 4L4 8M8 4L12 8"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </div>
          <p className="mt-2 text-center text-[11px] text-muted-foreground/50">
            Responses are generated from ingested county GIS data.
          </p>
        </div>
      </div>
    </div>
  );
}
