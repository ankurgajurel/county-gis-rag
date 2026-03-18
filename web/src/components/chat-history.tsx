"use client";

import { useEffect, useState } from "react";
import { X, Trash2, MessageSquare } from "lucide-react";
import { fetchChatHistory, deleteChatSession, type HistoryItem } from "@/lib/api";

interface ChatHistoryProps {
  open: boolean;
  onClose: () => void;
  onSelect: (sessionId: string) => void;
  onNewChat: () => void;
  userEmail: string;
  currentSessionId: string | null;
}

function timeAgo(dateStr: string | null): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

export function ChatHistory({ open, onClose, onSelect, onNewChat, userEmail, currentSessionId }: ChatHistoryProps) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !userEmail) return;
    setLoading(true);
    fetchChatHistory(userEmail).then((data) => {
      setItems(data);
      setLoading(false);
    });
  }, [open, userEmail]);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    await deleteChatSession(id);
    setItems((prev) => prev.filter((item) => item.id !== id));
  };

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40 bg-black/20" onClick={onClose} />

      {/* Panel */}
      <div className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-border/50 bg-background shadow-lg">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/50 px-4 py-3">
          <h2 className="text-sm font-medium text-foreground">History</h2>
          <button
            onClick={onClose}
            className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* New Chat Button */}
        <div className="border-b border-border/50 p-3">
          <button
            onClick={() => {
              onNewChat();
              onClose();
            }}
            className="inline-flex w-full items-center justify-center gap-2 h-9 rounded-md border border-border/60 text-xs font-medium text-foreground transition-colors hover:bg-muted/50"
          >
            New chat
          </button>
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <p className="text-xs text-muted-foreground">Loading...</p>
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 px-4">
              <MessageSquare className="h-8 w-8 text-muted-foreground/30 mb-2" />
              <p className="text-xs text-muted-foreground">No conversations yet</p>
            </div>
          ) : (
            <div className="p-2 space-y-0.5">
              {items.map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    onSelect(item.id);
                    onClose();
                  }}
                  className={`group flex w-full items-start gap-2 rounded-md px-3 py-2.5 text-left transition-colors hover:bg-muted/50 ${
                    item.id === currentSessionId ? "bg-muted/50" : ""
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-foreground">
                      {item.title || "Untitled chat"}
                    </p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {timeAgo(item.updated_at)}
                    </p>
                  </div>
                  <button
                    onClick={(e) => handleDelete(e, item.id)}
                    className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground/0 transition-colors group-hover:text-muted-foreground hover:!text-destructive"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
