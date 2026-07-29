import { useState, useMemo, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import type { ComponentType } from "react";
import {
  Search,
  Filter,
  X,
  ChevronUp,
  ChevronDown,
  Play,
  Copy,
  Bookmark,
  Share2,
  Sparkles,
  Layers,
  Video,
  ShieldCheck,
  Database,
  Mic,
  Compass,
  Network,
  FileSearch,
  Check,
  SlidersHorizontal,
  ExternalLink
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { TranscriptBlock } from "@/types/api";

// ----------------------------------------------------
// 1. SpeakerBadge Component
// ----------------------------------------------------
interface SpeakerBadgeProps {
  name: string;
  avatar: string;
  tone: "indigo" | "violet" | "cyan" | "emerald";
}

export function SpeakerBadge({ name, avatar, tone }: SpeakerBadgeProps) {
  const toneClasses = {
    indigo: "bg-indigo-500/20 text-indigo-300 border-indigo-500/30",
    violet: "bg-violet-500/20 text-violet-300 border-violet-500/30",
    cyan: "bg-cyan-500/20 text-cyan-300 border-cyan-500/30",
    emerald: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30"
  };

  return (
    <div className="flex items-center gap-2">
      <span className={cn("grid h-6 w-6 place-items-center rounded-full border text-[10px] font-bold font-mono text-white shadow-xs", toneClasses[tone])}>
        {avatar}
      </span>
      <span className="text-xs font-bold text-slate-200 truncate">{name}</span>
    </div>
  );
}

// ----------------------------------------------------
// 2. TranscriptHighlight Component
// ----------------------------------------------------
interface TranscriptHighlightProps {
  text: string;
  query: string;
}

export function TranscriptHighlight({ text, query }: TranscriptHighlightProps) {
  if (!query || !query.trim()) {
    return <span>{text}</span>;
  }

  const parts = text.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")})`, "gi"));

  return (
    <span>
      {parts.map((part, i) =>
        part.toLowerCase() === query.toLowerCase() ? (
          <mark
            key={i}
            className="bg-cyan-400/30 text-cyan-200 font-bold px-0.5 rounded shadow-[0_0_8px_rgba(34,211,238,0.4)] border border-cyan-400/40"
          >
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </span>
  );
}

// ----------------------------------------------------
// 3. SearchBar Component
// ----------------------------------------------------
interface SearchBarProps {
  query: string;
  onQueryChange: (q: string) => void;
  matchCount: number;
  activeMatchIndex: number;
  onNextMatch: () => void;
  onPrevMatch: () => void;
  onSelectSuggestion: (sug: string) => void;
}

export function SearchBar({
  query,
  onQueryChange,
  matchCount,
  activeMatchIndex,
  onNextMatch,
  onPrevMatch,
  onSelectSuggestion
}: SearchBarProps) {
  const suggestions = ["MCP", "REST", "Contract", "Pricing", "Whiteboard", "Security"];

  return (
    <div className="space-y-2">
      <div className="relative flex items-center bg-slate-900 border border-slate-800 rounded-xl px-3 py-1.5 focus-within:ring-2 focus-within:ring-primary focus-within:border-transparent shadow-xs">
        <Search className="h-4 w-4 text-slate-400 shrink-0 mr-2" />
        <Input
          type="text"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          placeholder="Semantic search transcript..."
          className="h-7 border-0 bg-transparent p-0 text-xs text-white placeholder:text-slate-500 focus-visible:ring-0 focus-visible:ring-offset-0 font-sans"
        />

        {query && (
          <div className="flex items-center gap-1 shrink-0 ml-2">
            <span className="text-[10px] font-mono text-cyan-400 bg-cyan-950/40 px-1.5 py-0.5 rounded border border-cyan-800">
              {matchCount > 0 ? `${activeMatchIndex + 1}/${matchCount}` : "0 matches"}
            </span>
            <Button
              variant="ghost"
              size="icon"
              onClick={onPrevMatch}
              disabled={matchCount === 0}
              className="h-6 w-6 text-slate-400 hover:text-white"
            >
              <ChevronUp className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={onNextMatch}
              disabled={matchCount === 0}
              className="h-6 w-6 text-slate-400 hover:text-white"
            >
              <ChevronDown className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onQueryChange("")}
              className="h-6 w-6 text-slate-400 hover:text-white"
            >
              <X className="h-3 w-3" />
            </Button>
          </div>
        )}
      </div>

      {/* Suggestion Chips */}
      <div className="flex flex-wrap gap-1 text-[10px]">
        <span className="text-slate-500 font-bold uppercase tracking-wider self-center mr-1">Suggestions:</span>
        {suggestions.map((sug) => (
          <button
            key={sug}
            onClick={() => onSelectSuggestion(sug)}
            className="px-2 py-0.5 rounded-full bg-slate-900 text-slate-300 border border-slate-800 hover:border-primary/40 hover:text-primary transition-colors"
          >
            {sug}
          </button>
        ))}
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 4. SearchFilters Component
// ----------------------------------------------------
interface SearchFiltersProps {
  selectedSpeaker: string;
  onSpeakerChange: (s: string) => void;
  hasOcrOnly: boolean;
  onOcrOnlyToggle: () => void;
  hasCitationsOnly: boolean;
  onCitationsOnlyToggle: () => void;
}

export function SearchFilters({
  selectedSpeaker,
  onSpeakerChange,
  hasOcrOnly,
  onOcrOnlyToggle,
  hasCitationsOnly,
  onCitationsOnlyToggle
}: SearchFiltersProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800/80 text-xs">
      {/* Speaker Selector */}
      <select
        value={selectedSpeaker}
        onChange={(e) => onSpeakerChange(e.target.value)}
        className="h-7 rounded-lg bg-slate-900 border border-slate-800 px-2 text-[11px] font-semibold text-slate-300 focus:outline-none focus:ring-1 focus:ring-primary"
      >
        <option value="all">All Speakers</option>
        <option value="spk-1">Speaker 1 (Presenter)</option>
        <option value="spk-2">Speaker 2 (Co-host)</option>
      </select>

      {/* Filter Toggles */}
      <Button
        variant="outline"
        size="sm"
        onClick={onOcrOnlyToggle}
        className={cn(
          "h-7 px-2 text-[10px] gap-1 font-semibold border-slate-800",
          hasOcrOnly ? "bg-amber-500/20 text-amber-300 border-amber-500/40" : "bg-slate-900 text-slate-400"
        )}
      >
        <Layers className="h-3 w-3" />
        Has OCR
      </Button>

      <Button
        variant="outline"
        size="sm"
        onClick={onCitationsOnlyToggle}
        className={cn(
          "h-7 px-2 text-[10px] gap-1 font-semibold border-slate-800",
          hasCitationsOnly ? "bg-cyan-500/20 text-cyan-300 border-cyan-500/40" : "bg-slate-900 text-slate-400"
        )}
      >
        <ShieldCheck className="h-3 w-3" />
        Contains Citations
      </Button>
    </div>
  );
}

// ----------------------------------------------------
// 5. SearchPanel Component
// ----------------------------------------------------
interface SearchPanelProps {
  query: string;
  onQueryChange: (q: string) => void;
  matchCount: number;
  activeMatchIndex: number;
  onNextMatch: () => void;
  onPrevMatch: () => void;
  selectedSpeaker: string;
  onSpeakerChange: (s: string) => void;
  hasOcrOnly: boolean;
  onOcrOnlyToggle: () => void;
  hasCitationsOnly: boolean;
  onCitationsOnlyToggle: () => void;
}

export function SearchPanel({
  query,
  onQueryChange,
  matchCount,
  activeMatchIndex,
  onNextMatch,
  onPrevMatch,
  selectedSpeaker,
  onSpeakerChange,
  hasOcrOnly,
  onOcrOnlyToggle,
  hasCitationsOnly,
  onCitationsOnlyToggle
}: SearchPanelProps) {
  return (
    <div className="p-3 bg-slate-950/80 border-b border-slate-800 space-y-2 shrink-0">
      <SearchBar
        query={query}
        onQueryChange={onQueryChange}
        matchCount={matchCount}
        activeMatchIndex={activeMatchIndex}
        onNextMatch={onNextMatch}
        onPrevMatch={onPrevMatch}
        onSelectSuggestion={onQueryChange}
      />
      <SearchFilters
        selectedSpeaker={selectedSpeaker}
        onSpeakerChange={onSpeakerChange}
        hasOcrOnly={hasOcrOnly}
        onOcrOnlyToggle={onOcrOnlyToggle}
        hasCitationsOnly={hasCitationsOnly}
        onCitationsOnlyToggle={onCitationsOnlyToggle}
      />
    </div>
  );
}

// ----------------------------------------------------
// 6. TranscriptCard Component
// ----------------------------------------------------
interface TranscriptCardProps {
  block: TranscriptBlock;
  query: string;
  isSelected: boolean;
  onSelect: (block: TranscriptBlock) => void;
  onSeekToTimestamp?: (sec: number) => void;
}

export function TranscriptCard({
  block,
  query,
  isSelected,
  onSelect,
  onSeekToTimestamp
}: TranscriptCardProps) {
  const [copied, setCopied] = useState(false);
  const [bookmarked, setBookmarked] = useState(block.bookmarked || false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(`[${block.timestamp}] ${block.speakerName}: "${block.text}"`);
    setCopied(true);
    toast.success("Transcript segment copied!");
    setTimeout(() => setCopied(false), 2000);
  };

  const handleBookmark = (e: React.MouseEvent) => {
    e.stopPropagation();
    setBookmarked(!bookmarked);
    toast.success(!bookmarked ? "Segment bookmarked." : "Bookmark removed.");
  };

  return (
    <Card
      onClick={() => onSelect(block)}
      className={cn(
        "p-4 border bg-slate-900/60 text-slate-100 shadow-soft backdrop-blur-xl transition-all duration-normal text-left cursor-pointer space-y-3",
        isSelected
          ? "border-cyan-400/80 bg-slate-900/90 shadow-[0_0_15px_rgba(34,211,238,0.2)]"
          : "border-slate-800/80 hover:border-slate-700 hover:bg-slate-900/80"
      )}
    >
      {/* Header Row */}
      <div className="flex items-center justify-between gap-2 border-b border-slate-800/60 pb-2">
        <SpeakerBadge name={block.speakerName} avatar={block.speakerAvatar} tone={block.speakerTone} />

        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-mono font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            {block.timestamp}
          </Badge>
          <Badge variant="outline" className="h-5 px-1.5 text-[10px] font-mono text-emerald-400 border-emerald-500/30 bg-emerald-950/20">
            {block.confidence}% Conf
          </Badge>
        </div>
      </div>

      {/* Transcript Text Body */}
      <p className="text-xs text-slate-200 leading-relaxed font-sans">
        <TranscriptHighlight text={block.text} query={query} />
      </p>

      {/* Attached OCR & Scene Tags */}
      {(block.ocrPreview || block.sceneTitle || block.citationCount > 0) && (
        <div className="flex flex-wrap items-center gap-1.5 pt-1 text-[10px]">
          {block.ocrPreview && (
            <span className="flex items-center gap-1 bg-amber-950/30 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded font-mono truncate max-w-xs">
              <Layers className="h-3 w-3 shrink-0" /> {block.ocrPreview}
            </span>
          )}

          {block.sceneTitle && (
            <span className="flex items-center gap-1 bg-indigo-950/30 text-indigo-300 border border-indigo-500/30 px-2 py-0.5 rounded font-mono">
              <Video className="h-3 w-3 shrink-0" /> {block.sceneTitle}
            </span>
          )}

          {block.citationCount > 0 && (
            <span className="flex items-center gap-1 bg-cyan-950/30 text-cyan-300 border border-cyan-500/30 px-2 py-0.5 rounded font-mono">
              <ShieldCheck className="h-3 w-3 shrink-0" /> {block.citationCount} Citations
            </span>
          )}
        </div>
      )}

      {/* Action Footer Bar */}
      <div className="flex items-center justify-between pt-2 border-t border-slate-800/60 text-[10px] text-slate-400">
        <span className="font-mono text-slate-400">{block.language}</span>

        <div className="flex items-center gap-1">
          {onSeekToTimestamp && (
            <Button
              variant="ghost"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onSeekToTimestamp(block.startSec);
              }}
              className="h-6 px-2 text-[10px] gap-1 text-cyan-400 hover:bg-cyan-950/40"
            >
              <Play className="h-2.5 w-2.5 fill-current" />
              Jump to Video
            </Button>
          )}

          <Button
            variant="ghost"
            size="icon"
            onClick={handleCopy}
            className="h-6 w-6 text-slate-400 hover:text-white"
            title="Copy Transcript"
          >
            {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={handleBookmark}
            className={cn("h-6 w-6 hover:text-white", bookmarked ? "text-primary" : "text-slate-400")}
            title="Bookmark"
          >
            <Bookmark className="h-3 w-3 fill-current" />
          </Button>
        </div>
      </div>
    </Card>
  );
}

// ----------------------------------------------------
// 7. SemanticCard Component
// ----------------------------------------------------
interface SemanticCardProps {
  title: string;
  description: string;
  badge?: string;
  icon: ComponentType<any>;
  gradient?: string;
}

export function SemanticCard({ title, description, badge, icon: Icon, gradient }: SemanticCardProps) {
  return (
    <Card className="p-3 border border-slate-800 bg-slate-900/80 text-left space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <Icon className="h-3.5 w-3.5 text-primary" /> {title}
        </span>
        {badge && (
          <Badge variant="outline" className="h-4 px-1 text-[9px] font-mono text-cyan-400 border-cyan-500/30">
            {badge}
          </Badge>
        )}
      </div>

      {gradient && (
        <div className={cn("h-12 w-full rounded bg-gradient-to-br flex items-center justify-center text-[9px] font-mono font-bold text-white p-1 text-center", gradient)}>
          <span>{title}</span>
        </div>
      )}

      <p className="text-xs text-slate-200 leading-normal">{description}</p>
    </Card>
  );
}

// ----------------------------------------------------
// 8. ContextPanel Component
// ----------------------------------------------------
interface ContextPanelProps {
  selectedBlock: TranscriptBlock | null;
  onClose: () => void;
}

export function ContextPanel({ selectedBlock, onClose }: ContextPanelProps) {
  if (!selectedBlock) {
    return (
      <div className="w-80 shrink-0 border-l border-slate-800 bg-slate-950 p-6 flex flex-col items-center justify-center text-center text-slate-400 space-y-3">
        <Compass className="h-10 w-10 text-slate-600 animate-pulse" />
        <div className="space-y-1">
          <p className="text-xs font-bold text-slate-300">Semantic Context Inspector</p>
          <p className="text-[11px] text-slate-500">Select any transcript segment to analyze related OCR, scene boundaries, and evidence importance scores.</p>
        </div>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      className="w-80 shrink-0 border-l border-slate-800 bg-slate-950 p-4 space-y-4 text-left overflow-y-auto"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center gap-1.5">
          <Sparkles className="h-4 w-4 text-primary" />
          <span className="text-xs font-bold text-white">Context Inspector</span>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} className="h-6 w-6 text-slate-400 hover:text-white">
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Memory Importance Score Gauge */}
      <Card className="p-3 border border-indigo-500/30 bg-indigo-950/20 space-y-1.5">
        <div className="flex justify-between items-center text-xs">
          <span className="font-semibold text-indigo-300">Memory Importance Score</span>
          <span className="font-mono font-bold text-cyan-400">{(selectedBlock.importanceScore * 100).toFixed(0)}%</span>
        </div>
        <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
          <div style={{ width: `${selectedBlock.importanceScore * 100}%` }} className="h-full bg-gradient-to-r from-indigo-500 to-cyan-400" />
        </div>
      </Card>

      {/* Topic Cluster */}
      <div className="space-y-1">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Topic Cluster</span>
        <div>
          <Badge variant="outline" className="bg-primary/10 text-primary border-primary/30 text-xs font-semibold">
            {selectedBlock.topicCluster}
          </Badge>
        </div>
      </div>

      {/* Related OCR Preview */}
      {selectedBlock.ocrPreview && (
        <SemanticCard
          title="Related OCR Slide Text"
          description={selectedBlock.ocrPreview}
          badge="OCR Token"
          icon={Layers}
        />
      )}

      {/* Related Scene Preview */}
      {selectedBlock.sceneTitle && (
        <SemanticCard
          title="Related Scene Chapter"
          description={selectedBlock.sceneTitle}
          gradient={selectedBlock.sceneGradient}
          badge={selectedBlock.timestamp}
          icon={Video}
        />
      )}

      {/* Grounded Citations count */}
      <SemanticCard
        title="Grounded AI Citations"
        description={`${selectedBlock.citationCount} vector evidence anchors linked to ChromaDB memory storage.`}
        badge={`${selectedBlock.citationCount} sources`}
        icon={ShieldCheck}
      />
    </motion.div>
  );
}

// ----------------------------------------------------
// 9. SearchStats Component
// ----------------------------------------------------
interface SearchStatsProps {
  totalFound: number;
  avgConfidence: number;
  speakerCount: number;
  timelineCoveragePct: number;
}

export function SearchStats({
  totalFound,
  avgConfidence,
  speakerCount,
  timelineCoveragePct
}: SearchStatsProps) {
  return (
    <div className="flex flex-wrap items-center justify-between border-t border-slate-800 bg-slate-950 px-4 py-2 text-[10px] text-slate-400 shrink-0 font-mono">
      <div className="flex items-center gap-4">
        <span>Results: <strong className="text-cyan-400">{totalFound}</strong> blocks</span>
        <span>Avg Conf: <strong className="text-emerald-400">{avgConfidence}%</strong></span>
        <span>Speakers: <strong className="text-violet-400">{speakerCount}</strong></span>
      </div>

      <div>
        Timeline Coverage: <strong className="text-indigo-400">{timelineCoveragePct}%</strong>
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 10. TranscriptExplorer Component (Main Orchestrator)
// ----------------------------------------------------
interface TranscriptExplorerProps {
  blocks?: TranscriptBlock[];
  onSeekToTimestamp?: (sec: number) => void;
}

export function TranscriptExplorer({ blocks = [], onSeekToTimestamp }: TranscriptExplorerProps) {
  const [query, setQuery] = useState("");
  const [selectedSpeaker, setSelectedSpeaker] = useState("all");
  const [hasOcrOnly, setHasOcrOnly] = useState(false);
  const [hasCitationsOnly, setHasCitationsOnly] = useState(false);

  const [selectedBlock, setSelectedBlock] = useState<TranscriptBlock | null>(null);
  const [activeMatchIndex, setActiveMatchIndex] = useState(0);

  // Filtered blocks logic
  const filteredBlocks = useMemo(() => {
    return blocks.filter((b) => {
      if (selectedSpeaker !== "all" && b.speakerId !== selectedSpeaker) return false;
      if (hasOcrOnly && !b.hasOcr) return false;
      if (hasCitationsOnly && b.citationCount === 0) return false;
      if (query.trim()) {
        const q = query.toLowerCase();
        const textMatch = b.text.toLowerCase().includes(q);
        const ocrMatch = b.ocrPreview?.toLowerCase().includes(q);
        const topicMatch = b.topicCluster.toLowerCase().includes(q);
        if (!textMatch && !ocrMatch && !topicMatch) return false;
      }
      return true;
    });
  }, [blocks, query, selectedSpeaker, hasOcrOnly, hasCitationsOnly]);

  const handleNextMatch = () => {
    if (filteredBlocks.length === 0) return;
    setActiveMatchIndex((prev) => (prev + 1) % filteredBlocks.length);
  };

  const handlePrevMatch = () => {
    if (filteredBlocks.length === 0) return;
    setActiveMatchIndex((prev) => (prev - 1 + filteredBlocks.length) % filteredBlocks.length);
  };

  const avgConfidence = useMemo(() => {
    if (filteredBlocks.length === 0) return 0;
    const sum = filteredBlocks.reduce((acc, b) => acc + b.confidence, 0);
    return Math.round(sum / filteredBlocks.length);
  }, [filteredBlocks]);

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-slate-950 text-slate-100 text-left select-none">
      {/* Background Glow Overlay */}
      <div className="absolute top-0 left-1/3 h-72 w-72 rounded-full bg-purple-500/5 blur-3xl pointer-events-none" />

      {/* Top Search & Filter Panel */}
      <SearchPanel
        query={query}
        onQueryChange={setQuery}
        matchCount={filteredBlocks.length}
        activeMatchIndex={activeMatchIndex}
        onNextMatch={handleNextMatch}
        onPrevMatch={handlePrevMatch}
        selectedSpeaker={selectedSpeaker}
        onSpeakerChange={setSelectedSpeaker}
        hasOcrOnly={hasOcrOnly}
        onOcrOnlyToggle={() => setHasOcrOnly(!hasOcrOnly)}
        hasCitationsOnly={hasCitationsOnly}
        onCitationsOnlyToggle={() => setHasCitationsOnly(!hasCitationsOnly)}
      />

      {/* Center Layout: Feed + Right Context Panel */}
      <div className="flex flex-1 overflow-hidden">
        {/* Transcript Cards Feed */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {filteredBlocks.length === 0 ? (
            /* Empty State */
            <div className="my-8 p-8 border border-dashed border-slate-800 rounded-2xl bg-slate-900/30 text-center space-y-3">
              <Network className="h-10 w-10 text-primary mx-auto animate-pulse" />
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-white">No transcript matches found</h4>
                <p className="text-xs text-slate-400 max-w-xs mx-auto">
                  Try clearing your search query or adjusting speaker filters to browse all video dialogue memory.
                </p>
              </div>
            </div>
          ) : (
            filteredBlocks.map((block) => (
              <TranscriptCard
                key={block.id}
                block={block}
                query={query}
                isSelected={selectedBlock?.id === block.id}
                onSelect={setSelectedBlock}
                onSeekToTimestamp={onSeekToTimestamp}
              />
            ))
          )}
        </div>

        {/* Right Context Inspector Panel */}
        <AnimatePresence>
          <ContextPanel selectedBlock={selectedBlock} onClose={() => setSelectedBlock(null)} />
        </AnimatePresence>
      </div>

      {/* Bottom Search Analytics Bar */}
      <SearchStats
        totalFound={filteredBlocks.length}
        avgConfidence={avgConfidence}
        speakerCount={new Set(blocks.map((block) => block.speakerId)).size}
        timelineCoveragePct={blocks.length > 0 ? 100 : 0}
      />
    </div>
  );
}

