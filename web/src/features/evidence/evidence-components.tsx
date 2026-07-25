import { useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { toast } from "sonner";
import {
  ShieldCheck,
  Check,
  AlertTriangle,
  HelpCircle,
  XCircle,
  Video,
  FileText,
  Layers,
  Mic,
  Database,
  Sparkles,
  Network,
  ArrowRight,
  Play,
  ExternalLink,
  ZoomIn,
  ZoomOut,
  Maximize2
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  type EvidenceQuality,
  type NodeType,
  type GraphNode,
  type GraphEdge,
  type EvidenceItem,
  MOCK_GRAPH_NODES,
  MOCK_GRAPH_EDGES,
  MOCK_EVIDENCE_ITEMS
} from "./mock-evidence-data";

// Icon Map Helper
const NODE_ICON_MAP: Record<string, any> = {
  HelpCircle,
  Sparkles,
  ShieldCheck,
  Video,
  Layers,
  Mic,
  Database,
  FileText
};

// ----------------------------------------------------
// 1. EvidenceBadge Component
// ----------------------------------------------------
export function EvidenceBadge({ quality = "grounded" }: { quality?: EvidenceQuality }) {
  const configs = {
    grounded: { label: "Grounded", icon: ShieldCheck, class: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40" },
    verified: { label: "Verified", icon: Check, class: "bg-cyan-500/20 text-cyan-300 border-cyan-500/40" },
    partial: { label: "Partial", icon: AlertTriangle, class: "bg-amber-500/20 text-amber-300 border-amber-500/40" },
    weak: { label: "Weak", icon: HelpCircle, class: "bg-orange-500/20 text-orange-300 border-orange-500/40" },
    unavailable: { label: "Unavailable", icon: XCircle, class: "bg-rose-500/20 text-rose-300 border-rose-500/40" }
  };

  const cfg = configs[quality] || configs.grounded;
  const Icon = cfg.icon;

  return (
    <Badge variant="outline" className={cn("h-5 px-2 text-[10px] font-mono font-bold gap-1 border shrink-0", cfg.class)}>
      <Icon className="h-3 w-3" />
      {cfg.label}
    </Badge>
  );
}

// ----------------------------------------------------
// 2. ConfidenceIndicator Component
// ----------------------------------------------------
export function ConfidenceIndicator({ score = 98 }: { score?: number }) {
  return (
    <div className="space-y-1 text-left">
      <div className="flex justify-between items-center text-xs">
        <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400">Grounding Confidence</span>
        <span className="font-mono font-bold text-cyan-400">{score}%</span>
      </div>
      <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
        <div style={{ width: `${score}%` }} className="h-full bg-gradient-to-r from-indigo-500 via-cyan-400 to-emerald-400" />
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 3. NodeLegend Component
// ----------------------------------------------------
export function NodeLegend() {
  const items = [
    { label: "Question", color: "bg-indigo-500" },
    { label: "Answer", color: "bg-cyan-400" },
    { label: "Evidence", color: "bg-emerald-400" },
    { label: "Scene", color: "bg-violet-500" },
    { label: "OCR", color: "bg-amber-400" },
    { label: "Speaker", color: "bg-pink-400" },
    { label: "Topic", color: "bg-blue-400" }
  ];

  return (
    <div className="flex flex-wrap items-center gap-3 px-3 py-1.5 bg-slate-950/80 border-t border-slate-800 text-[10px] font-mono text-slate-400 shrink-0">
      <span className="font-bold text-slate-300 uppercase tracking-wider">Node Legend:</span>
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-1.5">
          <span className={cn("h-2 w-2 rounded-full", it.color)} />
          {it.label}
        </span>
      ))}
    </div>
  );
}

// ----------------------------------------------------
// 4. NodeCard Component
// ----------------------------------------------------
interface NodeCardProps {
  node: GraphNode;
  isSelected: boolean;
  onSelect: (node: GraphNode) => void;
}

export function NodeCard({ node, isSelected, onSelect }: NodeCardProps) {
  const Icon = NODE_ICON_MAP[node.iconName] || Sparkles;

  return (
    <motion.div
      onClick={() => onSelect(node)}
      style={{ left: `${node.x}%`, top: `${node.y}%` }}
      whileHover={{ scale: 1.08 }}
      whileTap={{ scale: 0.95 }}
      className={cn(
        "absolute z-20 -translate-x-1/2 -translate-y-1/2 flex items-center gap-2 rounded-xl border px-3 py-1.5 text-xs font-semibold shadow-elevated cursor-pointer transition-all duration-fast select-none backdrop-blur-md",
        node.color,
        isSelected ? "ring-2 ring-cyan-400 ring-offset-2 ring-offset-slate-950 scale-105 shadow-[0_0_20px_rgba(34,211,238,0.5)]" : "opacity-90 hover:opacity-100"
      )}
      title={node.details}
    >
      <Icon className="h-3.5 w-3.5 shrink-0" />
      <span className="truncate max-w-[120px]">{node.label}</span>
    </motion.div>
  );
}

// ----------------------------------------------------
// 5. RelationshipEdge Component (SVG Line)
// ----------------------------------------------------
interface RelationshipEdgeProps {
  edge: GraphEdge;
  sourceNode?: GraphNode;
  targetNode?: GraphNode;
  isSelected: boolean;
}

export function RelationshipEdge({ edge, sourceNode, targetNode, isSelected }: RelationshipEdgeProps) {
  if (!sourceNode || !targetNode) return null;

  const midX = (sourceNode.x + targetNode.x) / 2;
  const midY = (sourceNode.y + targetNode.y) / 2;

  return (
    <g>
      {/* Edge Line */}
      <line
        x1={`${sourceNode.x}%`}
        y1={`${sourceNode.y}%`}
        x2={`${targetNode.x}%`}
        y2={`${targetNode.y}%`}
        className={cn(
          "transition-all duration-normal",
          isSelected ? "stroke-cyan-400 stroke-2" : "stroke-indigo-500/40 stroke-1"
        )}
        strokeDasharray="4 4"
      />

      {/* Midpoint Label Badge */}
      <foreignObject x={`${midX}%`} y={`${midY}%`} width="80" height="24" className="-translate-x-1/2 -translate-y-1/2 overflow-visible">
        <span className={cn("px-1.5 py-0.5 rounded text-[8px] font-mono font-bold border uppercase tracking-wider block text-center shadow-2xs", isSelected ? "bg-cyan-950 text-cyan-300 border-cyan-500" : "bg-slate-900/90 text-slate-400 border-slate-800")}>
          {edge.label}
        </span>
      </foreignObject>
    </g>
  );
}

// ----------------------------------------------------
// 6. KnowledgeGraph Component
// ----------------------------------------------------
interface KnowledgeGraphProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeId: string;
  onSelectNode: (node: GraphNode) => void;
}

export function KnowledgeGraph({ nodes, edges, selectedNodeId, onSelectNode }: KnowledgeGraphProps) {
  const [zoom, setZoom] = useState(100);

  const selectedNode = useMemo(() => nodes.find((n) => n.id === selectedNodeId) || nodes[0], [nodes, selectedNodeId]);

  return (
    <div className="relative h-full w-full bg-slate-950 overflow-hidden text-left flex flex-col justify-between select-none">
      {/* Background Neural Grid Accent */}
      <div className="absolute inset-0 opacity-15 bg-[linear-gradient(to_right,#6366f1_1px,transparent_1px),linear-gradient(to_bottom,#6366f1_1px,transparent_1px)] [background-size:2.5rem_2.5rem] pointer-events-none" />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 h-96 w-96 rounded-full bg-indigo-500/10 blur-3xl pointer-events-none" />

      {/* Top Header & Zoom Controls */}
      <div className="flex items-center justify-between p-3 border-b border-slate-800 bg-slate-900/80 shrink-0 z-30">
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="h-6 px-2 text-[10px] font-mono font-bold bg-indigo-500/10 text-indigo-400 border-indigo-500/20">
            KNOWLEDGE GRAPH VISUALIZER
          </Badge>
          <span className="text-xs font-bold text-slate-200">Interactive Neural Evidence Memory</span>
        </div>

        <div className="flex items-center gap-1 bg-slate-950 border border-slate-800 rounded-lg p-1 text-xs">
          <Button variant="ghost" size="icon" onClick={() => setZoom((z) => Math.max(70, z - 15))} className="h-6 w-6 text-slate-400 hover:text-white">
            <ZoomOut className="h-3 w-3" />
          </Button>
          <span className="font-mono text-[10px] text-slate-300 min-w-[2.5rem] text-center">{zoom}%</span>
          <Button variant="ghost" size="icon" onClick={() => setZoom((z) => Math.min(150, z + 15))} className="h-6 w-6 text-slate-400 hover:text-white">
            <ZoomIn className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Main Canvas with SVG Edges and Node Cards */}
      <div className="relative flex-1 overflow-hidden" style={{ transform: `scale(${zoom / 100})`, transformOrigin: "center center" }}>
        {/* SVG Edges Canvas */}
        <svg className="absolute inset-0 h-full w-full pointer-events-none z-10">
          {edges.map((e) => {
            const sNode = nodes.find((n) => n.id === e.sourceId);
            const tNode = nodes.find((n) => n.id === e.targetId);
            const isRelated = e.sourceId === selectedNodeId || e.targetId === selectedNodeId;
            return <RelationshipEdge key={e.id} edge={e} sourceNode={sNode} targetNode={tNode} isSelected={isRelated} />;
          })}
        </svg>

        {/* Node Cards Layer */}
        {nodes.map((node) => (
          <NodeCard
            key={node.id}
            node={node}
            isSelected={node.id === selectedNodeId}
            onSelect={onSelectNode}
          />
        ))}
      </div>

      {/* Bottom Node Legend */}
      <NodeLegend />
    </div>
  );
}

// ----------------------------------------------------
// 7. EvidenceCard Component
// ----------------------------------------------------
interface EvidenceCardProps {
  item: EvidenceItem;
  isSelected: boolean;
  onSelect: (item: EvidenceItem) => void;
}

export function EvidenceCard({ item, isSelected, onSelect }: EvidenceCardProps) {
  return (
    <Card
      onClick={() => onSelect(item)}
      className={cn(
        "p-3 border bg-slate-900/60 text-slate-100 shadow-soft transition-all duration-normal text-left cursor-pointer space-y-2",
        isSelected
          ? "border-cyan-400 bg-slate-900/90 shadow-[0_0_12px_rgba(34,211,238,0.25)]"
          : "border-slate-800 hover:border-slate-700 hover:bg-slate-900/80"
      )}
    >
      <div className="flex items-center justify-between gap-2 border-b border-slate-800/60 pb-1.5">
        <div className="flex items-center gap-1.5">
          <Badge variant="outline" className="h-5 px-1.5 text-[10px] font-mono font-bold bg-indigo-500/20 text-indigo-300 border-indigo-500/30">
            Rank #{item.rank}
          </Badge>
          <span className="text-[10px] font-mono text-slate-400">{item.timestamp}</span>
        </div>
        <EvidenceBadge quality={item.quality} />
      </div>

      <p className="text-xs font-bold text-slate-200 leading-tight truncate">{item.title}</p>
      
      {item.transcriptQuote && (
        <p className="text-[11px] text-slate-400 italic line-clamp-2">
          "{item.transcriptQuote}"
        </p>
      )}
    </Card>
  );
}

// ----------------------------------------------------
// 8. EvidencePanel Component
// ----------------------------------------------------
interface EvidencePanelProps {
  item: EvidenceItem;
  onSeekToTimestamp?: (sec: number) => void;
}

export function EvidencePanel({ item, onSeekToTimestamp }: EvidencePanelProps) {
  return (
    <div className="h-full w-full overflow-y-auto p-4 space-y-4 bg-slate-950 text-left border-l border-slate-800">
      {/* AI Grounding Header */}
      <Card className="p-4 border border-indigo-500/30 bg-indigo-950/20 space-y-3">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-bold uppercase tracking-wider text-indigo-300 flex items-center gap-1.5">
            <Sparkles className="h-4 w-4 text-cyan-400" />
            This AI Answer is Supported By:
          </span>
          <EvidenceBadge quality={item.quality} />
        </div>

        <ConfidenceIndicator score={item.confidence} />

        <p className="text-xs text-slate-300 leading-relaxed bg-slate-900/60 p-2.5 rounded border border-slate-800">
          {item.explanation}
        </p>
      </Card>

      {/* Frame gradient preview */}
      <div className={cn("h-24 w-full rounded-xl bg-gradient-to-br flex items-center justify-center text-xs font-mono font-bold text-white shadow-soft p-3 text-center border border-white/10", item.frameGradient)}>
        <span>{item.title}</span>
      </div>

      {/* Transcript Quote */}
      {item.transcriptQuote && (
        <div className="space-y-1">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
            <FileText className="h-3 w-3 text-emerald-400" /> Dialogue Transcript Quote
          </span>
          <div className="p-3 border rounded-lg bg-slate-900/80 text-xs text-slate-200 italic leading-relaxed">
            "{item.transcriptQuote}"
          </div>
        </div>
      )}

      {/* OCR Text */}
      {item.ocrText && (
        <div className="space-y-1">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
            <Layers className="h-3 w-3 text-amber-400" /> Slide OCR Text Extraction
          </span>
          <div className="p-2.5 border rounded-lg bg-slate-900/80 text-xs font-mono text-amber-300">
            {item.ocrText}
          </div>
        </div>
      )}

      {/* Scene Context */}
      <div className="space-y-1">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1">
          <Video className="h-3 w-3 text-violet-400" /> Scene Context
        </span>
        <p className="text-xs text-slate-300 font-semibold">{item.sceneDescription}</p>
      </div>

      {/* Action Button */}
      {onSeekToTimestamp && (
        <Button
          variant="primary"
          size="sm"
          onClick={() => onSeekToTimestamp(item.startSec)}
          className="w-full h-9 gap-1.5 shadow-sm"
        >
          <Play className="h-3.5 w-3.5 fill-current" />
          Jump to Timeline ({item.timestamp})
        </Button>
      )}
    </div>
  );
}

// ----------------------------------------------------
// 9. EvidenceTimeline Component
// ----------------------------------------------------
interface EvidenceTimelineProps {
  items: EvidenceItem[];
  selectedId: string;
  onSelect: (item: EvidenceItem) => void;
}

export function EvidenceTimeline({ items, selectedId, onSelect }: EvidenceTimelineProps) {
  return (
    <div className="h-12 border-t border-slate-800 bg-slate-950 px-4 py-2 flex items-center gap-3 shrink-0 text-xs text-left overflow-x-auto">
      <span className="text-[10px] font-bold font-mono text-slate-400 uppercase tracking-wider shrink-0">
        Evidence Timeline:
      </span>
      <div className="flex-1 relative h-6 bg-slate-900 border border-slate-800 rounded-md flex items-center px-2">
        {items.map((it) => {
          const isSelected = it.id === selectedId;
          const leftPct = (it.startSec / 2538) * 100;
          return (
            <button
              key={it.id}
              onClick={() => onSelect(it)}
              style={{ left: `${leftPct}%` }}
              className={cn(
                "absolute h-4 px-2 rounded-full text-[9px] font-mono font-bold transition-all duration-fast flex items-center gap-1 shadow-xs",
                isSelected
                  ? "bg-cyan-400 text-slate-950 border border-white z-10 scale-105"
                  : "bg-indigo-600/80 text-white border border-indigo-400/40 hover:bg-indigo-500"
              )}
              title={`${it.title} (${it.timestamp})`}
            >
              <ShieldCheck className="h-2.5 w-2.5" />
              Rank #{it.rank}
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 10. EvidenceInspector Component (Main Orchestrator)
// ----------------------------------------------------
interface EvidenceInspectorProps {
  onSeekToTimestamp?: (sec: number) => void;
}

export function EvidenceInspector({ onSeekToTimestamp }: EvidenceInspectorProps) {
  const [evidenceItems] = useState<EvidenceItem[]>(MOCK_EVIDENCE_ITEMS);
  const [selectedItem, setSelectedItem] = useState<EvidenceItem>(MOCK_EVIDENCE_ITEMS[0]);
  const [selectedNodeId, setSelectedNodeId] = useState<string>(MOCK_EVIDENCE_ITEMS[0].nodeId);

  const handleSelectEvidence = (item: EvidenceItem) => {
    setSelectedItem(item);
    setSelectedNodeId(item.nodeId);
  };

  const handleSelectNode = (node: GraphNode) => {
    setSelectedNodeId(node.id);
    const match = evidenceItems.find((e) => e.nodeId === node.id);
    if (match) setSelectedItem(match);
  };

  return (
    <div className="relative flex h-full w-full flex-col overflow-hidden bg-slate-950 text-slate-100 select-none">
      {/* Main 3-Column Center Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Column: Evidence Sources List */}
        <div className="w-72 shrink-0 border-r border-slate-800 bg-slate-950 p-3 space-y-3 overflow-y-auto text-left">
          <div className="flex items-center justify-between border-b border-slate-800 pb-2">
            <span className="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center gap-1.5">
              <ShieldCheck className="h-4 w-4 text-emerald-400" /> Grounded Evidence
            </span>
            <Badge variant="outline" className="text-[10px] font-mono text-cyan-400 border-cyan-500/30">
              3 Anchors
            </Badge>
          </div>

          <div className="space-y-2">
            {evidenceItems.map((item) => (
              <EvidenceCard
                key={item.id}
                item={item}
                isSelected={selectedItem.id === item.id}
                onSelect={handleSelectEvidence}
              />
            ))}
          </div>
        </div>

        {/* Center Column: Interactive Knowledge Graph */}
        <div className="flex-1 relative overflow-hidden">
          <KnowledgeGraph
            nodes={MOCK_GRAPH_NODES}
            edges={MOCK_GRAPH_EDGES}
            selectedNodeId={selectedNodeId}
            onSelectNode={handleSelectNode}
          />
        </div>

        {/* Right Column: Evidence Details Inspector Panel */}
        <div className="w-80 shrink-0 overflow-hidden">
          <EvidencePanel item={selectedItem} onSeekToTimestamp={onSeekToTimestamp} />
        </div>
      </div>

      {/* Bottom Column: Timeline Evidence Bar */}
      <EvidenceTimeline
        items={evidenceItems}
        selectedId={selectedItem.id}
        onSelect={handleSelectEvidence}
      />
    </div>
  );
}
