import { Collapsible } from "@base-ui/react/collapsible";
import { ChevronRight } from "lucide-react";
import ReactMarkdown from "react-markdown";

export interface ReasoningBlock {
  title: string;
  content: string;
}

interface ThinkingProps {
  /** Raw streaming text shown while reasoning is in progress */
  streamingText?: string;
  /** Parsed blocks shown once reasoning is complete */
  blocks?: ReasoningBlock[];
  toolStatus: string[] | null;
  expanded: boolean;
  onToggle: () => void;
}

export function Thinking({
  streamingText,
  blocks,
  toolStatus,
  expanded,
  onToggle,
}: ThinkingProps) {
  const hasBlocks = blocks && blocks.length > 0;
  const hasStreaming = streamingText && streamingText.length > 0;

  return (
    <Collapsible.Root open={expanded} onOpenChange={onToggle}>
      <Collapsible.Trigger className="group flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer">
        <ChevronRight className="h-3 w-3 transition-transform duration-200 group-data-[panel-open]:rotate-90" />
        <span>Thinking</span>
      </Collapsible.Trigger>

      <Collapsible.Panel className="h-[var(--collapsible-panel-height)] overflow-hidden transition-all duration-200 ease-out data-[ending-style]:h-0 data-[starting-style]:h-0 data-[ending-style]:opacity-0 data-[starting-style]:opacity-0">
        <div className="mt-3 pt-1 space-y-4 border-l-2 border-muted-foreground/20 pl-3">
          {hasBlocks ? (
            blocks.map((block, i) => (
              <div key={i}>
                <p className="text-xs font-medium text-muted-foreground/80">
                  {block.title}
                </p>
                <div className="text-xs text-muted-foreground/60 max-w-none [&_p]:my-1 [&_strong]:font-normal [&_b]:font-normal">
                  <ReactMarkdown>{block.content}</ReactMarkdown>
                </div>
              </div>
            ))
          ) : hasStreaming ? (
            <div className="text-xs text-muted-foreground/60 max-w-none [&_p]:my-1 [&_strong]:font-normal [&_b]:font-normal">
              <ReactMarkdown>{streamingText}</ReactMarkdown>
            </div>
          ) : null}
          {toolStatus && (
            <p className="text-xs text-muted-foreground/50 italic">
              Running: {toolStatus.join(", ")}...
            </p>
          )}
        </div>
      </Collapsible.Panel>
    </Collapsible.Root>
  );
}
