"use client";

import { useCallback, useEffect, useRef, useState, type ComponentRef } from "react";
import ReactMarkdown from "react-markdown";
import { useUser, useClerk } from "@clerk/nextjs";
import { streamChat, resetChat } from "@/lib/api";
import { Thinking, type ReasoningBlock } from "@/components/thinking";
import { MapPanel } from "@/components/map-panel";

interface Message {
  role: "user" | "assistant";
  content: string;
  /** Raw streaming reasoning text (while reasoning is in progress) */
  reasoningText?: string;
  /** Parsed reasoning blocks (after reasoning completes) */
  reasoning?: ReasoningBlock[];
}

const SUGGESTIONS = [
  "What's the zoning for 425 Fawell Blvd in Naperville?",
  "Compare residential zoning regulations across all municipalities",
  "Find the 10 highest assessed properties in Naperville",
  "Which GIS layers have flood zone data?",
  "What are the setback requirements for R-1 in Wheaton?",
];

export function Chat() {
  const { user } = useUser();
  const { signOut } = useClerk();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(true);
  const [toolStatus, setToolStatus] = useState<string[] | null>(null);
  const [mapGeojson, setMapGeojson] = useState<GeoJSON.FeatureCollection | null>(null);
  const [mapVisible, setMapVisible] = useState(true);
  const hasMapData = mapGeojson !== null && (mapGeojson.features?.length ?? 0) > 0;
  const showMap = hasMapData && mapVisible;
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const collapseScheduledRef = useRef(false);

  const submitMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isStreaming) return;

      setError(null);
      setIsStreaming(true);
      setInput("");
      collapseScheduledRef.current = false;
      setIsThinkingExpanded(true);
      setToolStatus(null);

      setMessages((prev) => [
        ...prev,
        { role: "user", content: trimmed },
        { role: "assistant", content: "" },
      ]);

      await streamChat(
        { message: trimmed, session_id: sessionId },
        {
          onSessionId: (id) => setSessionId(id),
          onReasoningDelta: (content) => {
            setIsThinkingExpanded(true);
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  reasoningText: (last.reasoningText || "") + content,
                };
              }
              return updated;
            });
          },
          onReasoningDone: (blocks) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  reasoningText: undefined,
                  reasoning: [...(last.reasoning || []), ...blocks],
                };
              }
              return updated;
            });
          },
          onToolStatus: (tools) => setToolStatus(tools),
          onToolStatusEnd: () => setToolStatus(null),
          onMapData: (geojson) => {
            setMapGeojson(geojson);
            setMapVisible(true);
          },
          onToken: (token) => {
            if (!collapseScheduledRef.current) {
              collapseScheduledRef.current = true;
              setTimeout(() => setIsThinkingExpanded(false), 300);
            }
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  content: last.content + token,
                };
              }
              return updated;
            });
          },
          onDone: () => setIsStreaming(false),
          onError: (err) => {
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last?.role === "assistant") {
                updated[updated.length - 1] = {
                  ...last,
                  reasoning: undefined,
                  reasoningText: undefined,
                  content: "",
                };
              }
              return updated.length > 0 &&
                updated[updated.length - 1]?.content === ""
                ? updated.slice(0, -1)
                : updated;
            });
            setError(err.message);
            setIsStreaming(false);
          },
        }
      );
    },
    [isStreaming, sessionId]
  );

  const handleSubmit = useCallback(() => {
    submitMessage(input);
  }, [input, submitMessage]);

  const handleReset = useCallback(async () => {
    if (sessionId) await resetChat(sessionId);
    setMessages([]);
    setSessionId(null);
    setError(null);
    setMapGeojson(null);
    setMapVisible(true);
  }, [sessionId]);

  const handleFeatureClick = useCallback(
    (properties: Record<string, unknown>) => {
      if (properties.pin) {
        setInput(`Tell me about parcel ${properties.pin}`);
      } else if (properties.layer_name && properties.feature_id) {
        setInput(
          `What is ${properties.layer_name} feature ${properties.feature_id}?`
        );
      }
      textareaRef.current?.focus();
    },
    []
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  useEffect(() => {
    if (!menuOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [menuOpen]);

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

  const hasThinking = (msg: Message) =>
    (msg.reasoning && msg.reasoning.length > 0) ||
    (msg.reasoningText && msg.reasoningText.length > 0);

  return (
    <div className="flex h-dvh flex-col bg-background">
      {/* Header */}
      <header className="flex shrink-0 items-center justify-between border-b border-border/50 px-6 py-4">
        <h1 className="text-sm font-medium tracking-tight text-foreground">
          County GIS Chat
        </h1>
        <div className="flex items-center gap-4">
          {hasMapData && !mapVisible && (
            <button
              onClick={() => setMapVisible(true)}
              className="flex items-center gap-1.5 rounded-md border border-border/60 px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-border hover:bg-muted/50 hover:text-foreground"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6" />
                <line x1="8" y1="2" x2="8" y2="18" />
                <line x1="16" y1="6" x2="16" y2="22" />
              </svg>
              Show map
            </button>
          )}
          {messages.length > 0 && (
            <button
              onClick={handleReset}
              className="text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              New chat
            </button>
          )}
          {user && (
            <div className="relative" ref={menuRef}>
              <button
                onClick={() => setMenuOpen((v) => !v)}
                className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full overflow-hidden ring-1 ring-border/60 transition-shadow hover:ring-border focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {user.imageUrl ? (
                  <img
                    src={user.imageUrl}
                    alt=""
                    className="h-full w-full object-cover"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <span className="flex h-full w-full items-center justify-center bg-foreground text-background text-xs font-medium">
                    {user.firstName?.[0] || user.emailAddresses[0]?.emailAddress[0]?.toUpperCase() || "U"}
                  </span>
                )}
              </button>
              {menuOpen && (
                <div className="absolute right-0 top-full mt-1.5 min-w-[140px] rounded-md border border-border bg-popover p-1 shadow-md">
                  <button
                    onClick={() => {
                      setMenuOpen(false);
                      signOut({ redirectUrl: "/sign-in" });
                    }}
                    className="flex w-full items-center rounded-sm px-3 py-1.5 text-xs text-popover-foreground transition-colors hover:bg-muted"
                  >
                    Sign out
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </header>

      {/* Messages + Map */}
      <div className="flex flex-1 overflow-hidden">
        <div className={`overflow-y-auto transition-all duration-300 ${showMap ? "w-1/2" : "w-full"}`}>
          <div className={`mx-auto px-6 ${showMap ? "max-w-xl" : "max-w-2xl"}`}>
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
                  {SUGGESTIONS.map((s, i) => (
                    <button
                      key={s}
                      onClick={() => submitMessage(s)}
                      className={`rounded-lg border border-border/60 px-4 py-3 text-left text-[13px] leading-snug text-muted-foreground transition-colors hover:border-border hover:bg-muted/50 hover:text-foreground ${
                        i === SUGGESTIONS.length - 1 ? "sm:col-span-2 sm:mx-auto sm:w-fit sm:text-center" : ""
                      }`}
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
                      {msg.role === "assistant" && hasThinking(msg) && (
                        <div className="mt-3 mb-3">
                          <Thinking
                            streamingText={msg.reasoningText}
                            blocks={msg.reasoning}
                            toolStatus={i === messages.length - 1 ? toolStatus : null}
                            expanded={i === messages.length - 1 ? isThinkingExpanded : false}
                            onToggle={() => {
                              if (i === messages.length - 1) {
                                setIsThinkingExpanded((prev) => !prev);
                              }
                            }}
                          />
                        </div>
                      )}
                      {msg.role === "assistant" ? (
                        <div className="prose prose-sm prose-neutral dark:prose-invert max-w-none text-sm leading-relaxed [&_pre]:rounded-lg [&_pre]:bg-muted [&_pre]:p-3 [&_code]:rounded [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:text-[13px] [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_ul]:space-y-1 [&_ol]:space-y-1 [&_p]:my-2 first:[&_p]:mt-0 last:[&_p]:mb-0 [&_table]:text-sm [&_th]:px-3 [&_th]:py-1.5 [&_td]:px-3 [&_td]:py-1.5 [&_th]:border [&_td]:border [&_th]:border-border [&_td]:border-border [&_th]:bg-muted">
                          {msg.content ? (
                            <ReactMarkdown>{msg.content}</ReactMarkdown>
                          ) : (
                            isStreaming &&
                            !hasThinking(msg) && (
                              <div className="flex items-center gap-1.5 pt-1">
                                <span className="h-1 w-1 animate-pulse rounded-full bg-muted-foreground/40" />
                                <span className="h-1 w-1 animate-pulse rounded-full bg-muted-foreground/40 [animation-delay:150ms]" />
                                <span className="h-1 w-1 animate-pulse rounded-full bg-muted-foreground/40 [animation-delay:300ms]" />
                              </div>
                            )
                          )}
                        </div>
                      ) : (
                        <div className="text-sm leading-relaxed text-foreground whitespace-pre-wrap break-words">
                          {msg.content}
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {error && (
                  <div className="ml-11 text-sm text-destructive">
                    Failed to send message. Please try again.
                  </div>
                )}

                <div ref={bottomRef} />
              </div>
            )}
          </div>
        </div>

        {showMap && (
          <div className="w-1/2 shrink-0 border-l border-border/50">
            <MapPanel
              geojson={mapGeojson}
              onFeatureClick={handleFeatureClick}
              onClose={() => setMapVisible(false)}
            />
          </div>
        )}
      </div>

      {/* Input — sticky bottom */}
      <div className="sticky bottom-0 shrink-0 border-t border-border/50 bg-background px-6 py-4">
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
              disabled={!input.trim() || isStreaming}
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
