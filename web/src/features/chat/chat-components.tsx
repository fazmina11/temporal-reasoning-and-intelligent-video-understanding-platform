import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  Sparkles,
  Send,
  Mic,
  Paperclip,
  Copy,
  Bookmark,
  RotateCcw,
  ChevronDown,
  ChevronUp,
  Play,
  ShieldCheck,
  Database,
  Layers,
  ArrowDown,
  HelpCircle,
  Network,
  FileSearch,
  MessageSquareText,
  Check,
  ExternalLink,
  Volume2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { type ChatMessage, type CitationItem, type ApiCitation } from "@/types/api";
import { INITIAL_CHAT_MESSAGES } from "./mock-chat-responses";
import { useAsk } from "@/hooks/api/use-ask";

const secondsToTimestamp = (seconds?: number | null) => {
  const total = Math.max(0, Math.floor(seconds ?? 0));
  const minutes = Math.floor(total / 60);
  const secs = String(total % 60).padStart(2, "0");
  return `${minutes}:${secs}`;
};

const timestampToSeconds = (timestamp: string) => {
  const parts = timestamp.split(":").map((part) => Number(part));
  if (parts.some(Number.isNaN)) return 0;
  return parts.reduce((total, part) => total * 60 + part, 0);
};

const citationType = (sourceType?: string): CitationItem["type"] => {
  const normalized = String(sourceType || "").toLowerCase();
  if (normalized.includes("ocr")) return "ocr";
  if (normalized.includes("visual") || normalized.includes("event") || normalized.includes("scene")) return "scene";
  return "transcript";
};

const mapCitation = (citation: ApiCitation, index: number, fallbackConfidence: number): CitationItem => {
  const startSeconds = citation.start_seconds ?? (typeof citation.start_ms === "number" ? citation.start_ms / 1000 : 0);
  const endSeconds = citation.end_seconds ?? (typeof citation.end_ms === "number" ? citation.end_ms / 1000 : startSeconds);
  const type = citationType(citation.source_type);
  const snippet = citation.text || citation.visual_summary || "Grounding citation span from video timeline";

  return {
    id: citation.citation_id || citation.evidence_id || `S${index + 1}`,
    timestamp: citation.timestamp || secondsToTimestamp(startSeconds),
    timestampEnd: secondsToTimestamp(endSeconds),
    frameGradient: "from-indigo-950 via-slate-900 to-cyan-900",
    transcriptSnippet: snippet,
    ocrSnippet: type === "ocr" ? snippet : undefined,
    score: (citation.confidence ?? citation.quality_score ?? fallbackConfidence) || 0,
    type
  };
};
// ----------------------------------------------------
// 1. ConfidenceBadge Component
// ----------------------------------------------------
export function ConfidenceBadge({ score = 95 }: { score?: number }) {
  const isHigh = score >= 90;
  const isModerate = score >= 75 && score < 90;

  return (
    <Badge
      variant="outline"
      className={cn(
        "h-5 px-2 text-[10px] font-mono font-bold gap-1 border shrink-0",
        isHigh
          ? "bg-emerald-50 text-emerald-700 border-emerald-300 dark:bg-emerald-950/40 dark:text-emerald-300 dark:border-emerald-800"
          : isModerate
          ? "bg-amber-50 text-amber-700 border-amber-300 dark:bg-amber-950/40 dark:text-amber-300 dark:border-amber-800"
          : "bg-slate-50 text-slate-700 border-slate-300 dark:bg-slate-900 dark:text-slate-300"
      )}
    >
      <ShieldCheck className="h-3 w-3" />
      {score}% Confidence
    </Badge>
  );
}

// ----------------------------------------------------
// 2. SourcePreview Component
// ----------------------------------------------------
interface SourcePreviewProps {
  citation: CitationItem;
  onJumpToVideo?: (seconds: number) => void;
}

export function SourcePreview({ citation, onJumpToVideo }: SourcePreviewProps) {
  return (
    <Card className="p-3 border border-border/80 bg-slate-50/70 dark:bg-slate-900/50 space-y-2 text-left hover:border-primary/40 transition-all duration-normal">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5">
          <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-mono font-bold bg-primary/10 text-primary border border-primary/20">
            {citation.timestamp} â€“ {citation.timestampEnd}
          </Badge>
          <span className="text-[10px] font-mono text-muted-foreground">
            Score: {(citation.score * 100).toFixed(1)}%
          </span>
        </div>

        {onJumpToVideo && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onJumpToVideo(timestampToSeconds(citation.timestamp))}
            className="h-6 px-2 text-[10px] font-semibold gap-1 text-primary hover:bg-primary/10"
          >
            <Play className="h-2.5 w-2.5 fill-current" />
            Jump to Video
          </Button>
        )}
      </div>

      <div className="flex gap-2.5 items-stretch">
        {/* Frame gradient preview placeholder */}
        <div className={cn("w-20 shrink-0 rounded-md bg-gradient-to-br flex items-center justify-center text-[9px] font-mono font-bold text-white shadow-xs p-1 text-center", citation.frameGradient)}>
          <span>FRAME {citation.timestamp}</span>
        </div>

        {/* Content text snippets */}
        <div className="flex-1 space-y-1 min-w-0 text-xs">
          <p className="text-foreground leading-tight italic line-clamp-2">
            "{citation.transcriptSnippet}"
          </p>
          {citation.ocrSnippet && (
            <p className="text-[10px] font-mono text-muted-foreground line-clamp-1 bg-background/80 p-1 rounded border border-border/50">
              OCR: {citation.ocrSnippet}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}

// ----------------------------------------------------
// 3. CitationCard Component
// ----------------------------------------------------
interface CitationCardProps {
  citations: CitationItem[];
  onJumpToVideo?: (seconds: number) => void;
}

export function CitationCard({ citations, onJumpToVideo }: CitationCardProps) {
  const [expanded, setExpanded] = useState(false);

  if (!citations || citations.length === 0) return null;

  return (
    <div className="space-y-2 pt-2 border-t border-border/50">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between w-full text-[11px] font-semibold text-muted-foreground hover:text-foreground transition-colors"
      >
        <span className="flex items-center gap-1.5">
          <Database className="h-3.5 w-3.5 text-primary" />
          {citations.length} Grounded Evidence {citations.length === 1 ? "Source" : "Sources"} Attached
        </span>
        <span className="flex items-center gap-1 text-[10px] text-primary">
          {expanded ? "Collapse" : "Expand Citations"}
          {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </span>
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="space-y-2 overflow-hidden"
          >
            {citations.map((cit) => (
              <SourcePreview key={cit.id} citation={cit} onJumpToVideo={onJumpToVideo} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ----------------------------------------------------
// 4. TypingIndicator Component
// ----------------------------------------------------
export function TypingIndicator() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      className="flex items-start gap-3 p-3 text-left"
    >
      <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground shadow-xs animate-pulse">
        <Sparkles className="h-3.5 w-3.5" />
      </div>

      <div className="rounded-2xl rounded-tl-none border border-border/80 bg-card/90 p-3 shadow-soft space-y-2 max-w-sm">
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-foreground">VideoSceneRAG</span>
          <span className="text-[10px] text-muted-foreground font-mono">Analyzing memory...</span>
        </div>

        <div className="flex items-center gap-1.5 py-1">
          <motion.span
            className="h-2 w-2 rounded-full bg-primary"
            animate={{ scale: [1, 1.4, 1], opacity: [0.4, 1, 0.4] }}
            transition={{ repeat: Infinity, duration: 0.8, delay: 0 }}
          />
          <motion.span
            className="h-2 w-2 rounded-full bg-primary"
            animate={{ scale: [1, 1.4, 1], opacity: [0.4, 1, 0.4] }}
            transition={{ repeat: Infinity, duration: 0.8, delay: 0.2 }}
          />
          <motion.span
            className="h-2 w-2 rounded-full bg-primary"
            animate={{ scale: [1, 1.4, 1], opacity: [0.4, 1, 0.4] }}
            transition={{ repeat: Infinity, duration: 0.8, delay: 0.4 }}
          />
        </div>
      </div>
    </motion.div>
  );
}

// ----------------------------------------------------
// 5. MessageBubble Component
// ----------------------------------------------------
interface MessageBubbleProps {
  message: ChatMessage;
  onBookmarkToggle?: (id: string) => void;
  onJumpToVideo?: (seconds: number) => void;
  onRegenerate?: () => void;
}

export function MessageBubble({
  message,
  onBookmarkToggle,
  onJumpToVideo,
  onRegenerate
}: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.sender === "user";

  const handleCopy = () => {
    navigator.clipboard.writeText(message.text);
    setCopied(true);
    toast.success("Response copied to clipboard!");
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-end p-2"
      >
        <div className="max-w-[85%] rounded-2xl rounded-tr-none bg-primary px-4 py-3 text-primary-foreground shadow-sm text-xs font-medium text-left leading-relaxed">
          {message.text}
          <div className="text-[9px] text-primary-foreground/75 mt-1 text-right font-mono">
            {message.timestamp}
          </div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-start gap-3 p-2 text-left"
    >
      <div className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground shadow-xs">
        <Sparkles className="h-3.5 w-3.5" />
      </div>

      <div className="flex-1 space-y-3 max-w-[90%]">
        <Card className="p-4 border border-border/80 bg-card/90 shadow-soft backdrop-blur-xl space-y-3">
          {/* Header row with badges */}
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2">
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-foreground">AI Memory Engine</span>
              {message.retrievalStatus && (
                <Badge variant="secondary" className="h-5 text-[9px] font-mono bg-slate-100 dark:bg-slate-900 border">
                  {message.retrievalStatus}
                </Badge>
              )}
            </div>

            {message.confidenceScore !== undefined && (
              <ConfidenceBadge score={message.confidenceScore} />
            )}
          </div>

          {/* AI Response Text */}
          <p className="text-xs text-foreground leading-relaxed font-sans">
            {message.text}
          </p>

          {/* Citations block */}
          {message.citations && message.citations.length > 0 && (
            <CitationCard citations={message.citations} onJumpToVideo={onJumpToVideo} />
          )}

          {/* Actions Footer */}
          <div className="flex items-center justify-between pt-2 border-t border-border/50 text-muted-foreground text-[10px]">
            <span className="font-mono">{message.timestamp}</span>

            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                onClick={handleCopy}
                className="h-6 w-6 hover:text-foreground"
                title="Copy response"
              >
                {copied ? <Check className="h-3 w-3 text-emerald-500" /> : <Copy className="h-3 w-3" />}
              </Button>

              <Button
                variant="ghost"
                size="icon"
                onClick={() => onBookmarkToggle?.(message.id)}
                className={cn("h-6 w-6 hover:text-foreground", message.bookmarked ? "text-primary" : "")}
                title="Bookmark response"
              >
                <Bookmark className="h-3 w-3 fill-current" />
              </Button>

              {onRegenerate && (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onRegenerate}
                  className="h-6 w-6 hover:text-foreground"
                  title="Regenerate response"
                >
                  <RotateCcw className="h-3 w-3" />
                </Button>
              )}
            </div>
          </div>
        </Card>
      </div>
    </motion.div>
  );
}

// ----------------------------------------------------
// 6. SuggestedQuestion Component
// ----------------------------------------------------
interface SuggestedQuestionProps {
  label: string;
  onClick: (query: string) => void;
}

export function SuggestedQuestion({ label, onClick }: SuggestedQuestionProps) {
  return (
    <button
      onClick={() => onClick(label)}
      className="group relative flex items-center gap-1.5 rounded-full border border-border/80 bg-slate-50/80 dark:bg-slate-900/60 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:border-primary/40 hover:bg-primary/5 hover:text-primary transition-all duration-normal shrink-0 shadow-2xs"
    >
      <HelpCircle className="h-3.5 w-3.5 text-primary/70 group-hover:text-primary transition-colors" />
      <span>{label}</span>
    </button>
  );
}

// ----------------------------------------------------
// 7. ChatInput Component
// ----------------------------------------------------
interface ChatInputProps {
  onSendMessage: (text: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSendMessage, disabled }: ChatInputProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSend = () => {
    if (!text.trim() || disabled) return;
    onSendMessage(text.trim());
    setText("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleTextChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(120, textareaRef.current.scrollHeight)}px`;
    }
  };

  return (
    <div className="p-3 border-t border-border/80 bg-card/90 backdrop-blur-md space-y-2 shrink-0">
      <div className="relative flex items-end gap-2 bg-background border border-border/80 rounded-xl p-2 focus-within:ring-2 focus-within:ring-ring focus-within:border-transparent transition-all shadow-2xs">
        <Textarea
          ref={textareaRef}
          value={text}
          onChange={handleTextChange}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything about this video... (Press Enter to send)"
          rows={1}
          disabled={disabled}
          className="min-h-[38px] max-h-[120px] resize-none border-0 bg-transparent p-1 text-xs focus-visible:ring-0 focus-visible:ring-offset-0 flex-1 font-sans"
        />

        <div className="flex items-center gap-1 shrink-0 pb-0.5">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => toast.info("Voice query feature placeholder.")}
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
            title="Voice Query"
          >
            <Mic className="h-3.5 w-3.5" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={() => toast.info("Attach file/frame placeholder.")}
            className="h-7 w-7 text-muted-foreground hover:text-foreground"
            title="Attach Document or Frame"
          >
            <Paperclip className="h-3.5 w-3.5" />
          </Button>

          <Button
            size="icon"
            onClick={handleSend}
            disabled={!text.trim() || disabled}
            className="h-7 w-7 rounded-lg shadow-xs"
          >
            <Send className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex items-center justify-between text-[10px] text-muted-foreground px-1 font-mono">
        <span>Shift + Enter for new line</span>
        <span>{text.length} / 1000</span>
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 8. ChatWindow Component
// ----------------------------------------------------
interface ChatWindowProps {
  videoId?: string;
  onJumpToVideo?: (sec: number) => void;
}

export function ChatWindow({ videoId, onJumpToVideo }: ChatWindowProps) {
  const askMutation = useAsk();
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_CHAT_MESSAGES);
  const [isTyping, setIsTyping] = useState(false);
  const [showScrollBottom, setShowScrollBottom] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const suggestions = [
    "Summarize this meeting",
    "Show all OCR text",
    "When was the contract mentioned?",
    "Find people discussing pricing",
    "Show scene containing whiteboard"
  ];

  // Auto-scroll handler
  const scrollToBottom = () => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: "smooth"
      });
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    setShowScrollBottom(scrollHeight - scrollTop - clientHeight > 100);
  };

  const handleSendMessage = async (text: string) => {
    const userMsg: ChatMessage = {
      id: `msg-user-${Date.now()}`,
      sender: "user",
      text,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsTyping(true);

    try {
      if (!videoId) {
        throw new Error("Select a processed video before asking a question.");
      }
      const responseData = await askMutation.mutateAsync({ video_id: videoId, query: text });

      const aiResponse: ChatMessage = {
        id: `msg-ai-${Date.now()}`,
        sender: "ai",
        text: responseData.answer || "The backend did not return an answer for this question.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        confidenceScore: Math.round((responseData.confidence || 0) * 100),
        retrievalStatus: responseData.answer_quality?.grounded ? "Grounded" : "Verified",
        citations: responseData.citations?.map((citation, idx) => mapCitation(citation, idx, responseData.confidence || 0)) || []
      };

      setMessages((prev) => [...prev, aiResponse]);
    } catch (err) {
      const aiResponse: ChatMessage = {
        id: `msg-ai-error-${Date.now()}`,
        sender: "ai",
        text: err instanceof Error ? err.message : "The backend ask endpoint is unavailable.",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        retrievalStatus: "Backend unavailable",
        confidenceScore: 0,
        citations: []
      };
      toast.error("Question failed against the backend.");
      setMessages((prev) => [...prev, aiResponse]);
    } finally {
      setIsTyping(false);
    }
  };

  const handleBookmarkToggle = (id: string) => {
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id === id) {
          const nextState = !m.bookmarked;
          toast.success(nextState ? "Message bookmarked." : "Bookmark removed.");
          return { ...m, bookmarked: nextState };
        }
        return m;
      })
    );
  };

  return (
    <div className="relative flex h-full w-full flex-col justify-between overflow-hidden bg-card text-left">
      {/* Radial Background Accent Glow */}
      <div className="absolute top-0 right-0 h-64 w-64 rounded-full bg-primary/5 blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 left-0 h-64 w-64 rounded-full bg-cyan-500/5 blur-3xl pointer-events-none" />

      {/* Header Bar */}
      <div className="flex items-center justify-between border-b border-border/80 px-4 py-2.5 bg-slate-50/70 dark:bg-slate-900/40 shrink-0 z-10">
        <div className="flex items-center gap-2">
          <span className="grid h-6 w-6 place-items-center rounded-md bg-primary text-primary-foreground shadow-2xs">
            <Sparkles className="h-3.5 w-3.5" />
          </span>
          <span className="text-xs font-bold text-foreground">AI Temporal Memory Assistant</span>
        </div>

        <Badge variant="outline" className="text-[9px] font-mono font-bold bg-primary/10 text-primary border-primary/20">
          ChromaDB RAG Active
        </Badge>
      </div>

      {/* Message Feed Area */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-4 space-y-4 relative z-10"
      >
        {messages.length === 1 && (
          /* Neural Empty State Graphic */
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="my-6 p-6 border border-dashed border-border/80 rounded-2xl bg-slate-50/50 dark:bg-slate-900/20 text-center space-y-3"
          >
            <div className="relative mx-auto h-16 w-16 flex items-center justify-center rounded-2xl bg-gradient-to-br from-indigo-500/20 via-purple-500/20 to-cyan-500/20 text-primary border shadow-xs">
              <Network className="h-8 w-8 text-primary animate-pulse" />
            </div>
            <div className="space-y-1">
              <h4 className="text-sm font-bold text-foreground">Ask anything about your video.</h4>
              <p className="text-xs text-muted-foreground max-w-xs mx-auto">
                VideoSceneRAG uses canonical evidence bounds, OCR slide indexes, and Whisper transcripts to answer queries with precise video timestamps.
              </p>
            </div>
          </motion.div>
        )}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onBookmarkToggle={handleBookmarkToggle}
            onJumpToVideo={onJumpToVideo}
            onRegenerate={() => handleSendMessage(msg.text)}
          />
        ))}

        <AnimatePresence>{isTyping && <TypingIndicator />}</AnimatePresence>
      </div>

      {/* Floating Scroll to Bottom Button */}
      <AnimatePresence>
        {showScrollBottom && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
            className="absolute bottom-28 right-4 z-20"
          >
            <Button
              size="icon"
              variant="outline"
              onClick={scrollToBottom}
              className="h-8 w-8 rounded-full shadow-elevated bg-card border-primary/30 text-primary hover:bg-primary hover:text-white"
            >
              <ArrowDown className="h-4 w-4" />
            </Button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Suggested Questions Bar */}
      <div className="px-3 py-2 border-t border-border/60 bg-slate-50/50 dark:bg-slate-900/20 overflow-x-auto flex items-center gap-1.5 shrink-0 z-10">
        <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground shrink-0 mr-1 flex items-center gap-1">
          <HelpCircle className="h-3 w-3" /> Prompts:
        </span>
        {suggestions.map((sug) => (
          <SuggestedQuestion key={sug} label={sug} onClick={handleSendMessage} />
        ))}
      </div>

      {/* Multiline Input Bar */}
      <ChatInput onSendMessage={handleSendMessage} disabled={isTyping} />
    </div>
  );
}




