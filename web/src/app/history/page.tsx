"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import { Trash2, MessageSquare, ArrowLeft, Plus } from "lucide-react";
import { fetchChatHistory, deleteChatSession, type HistoryItem } from "@/lib/api";

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

export default function HistoryPage() {
  const { user, isLoaded } = useUser();
  const router = useRouter();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);

  const userEmail = user?.emailAddresses[0]?.emailAddress || "";

  useEffect(() => {
    if (!isLoaded) return;
    if (!userEmail) {
      router.replace("/sign-in");
      return;
    }
    fetchChatHistory(userEmail).then((data) => {
      setItems(data);
      setLoading(false);
    });
  }, [isLoaded, userEmail, router]);

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    await deleteChatSession(id);
    setItems((prev) => prev.filter((item) => item.id !== id));
  };

  return (
    <div className="flex h-dvh flex-col bg-background">
      {/* Header */}
      <header className="flex shrink-0 items-center justify-between border-b border-border/50 px-6 py-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.push("/")}
            className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
            aria-label="Back to chat"
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <h1 className="text-sm font-medium tracking-tight text-foreground">
            Chat History
          </h1>
        </div>
        <button
          onClick={() => router.push("/")}
          className="inline-flex items-center gap-1.5 rounded-md border border-border/60 px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-muted/50"
        >
          <Plus className="h-3.5 w-3.5" />
          New chat
        </button>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-2xl px-6 py-8">
          {loading ? (
            <div className="flex items-center justify-center py-20">
              <p className="text-sm text-muted-foreground">Loading...</p>
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20">
              <MessageSquare className="h-10 w-10 text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground">No conversations yet</p>
              <button
                onClick={() => router.push("/")}
                className="mt-4 rounded-md border border-border/60 px-4 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted/50"
              >
                Start a new chat
              </button>
            </div>
          ) : (
            <div className="space-y-1">
              {items.map((item) => (
                <div
                  key={item.id}
                  onClick={() => router.push(`/chat/${item.id}`)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") router.push(`/chat/${item.id}`); }}
                  className="group flex w-full cursor-pointer items-center gap-4 rounded-lg border border-transparent px-4 py-3.5 text-left transition-colors hover:border-border/50 hover:bg-muted/50"
                >
                  <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground/50" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-foreground">
                      {item.title || "Untitled chat"}
                    </p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {timeAgo(item.updated_at)}
                    </p>
                  </div>
                  <button
                    onClick={(e) => handleDelete(e, item.id)}
                    className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted-foreground/0 transition-colors group-hover:text-muted-foreground hover:!bg-destructive/10 hover:!text-destructive"
                    aria-label="Delete conversation"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
