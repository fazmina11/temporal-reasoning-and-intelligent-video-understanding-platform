export type EvidenceQuality = "grounded" | "verified" | "partial" | "weak" | "unavailable";

export type NodeType = "video" | "scene" | "speaker" | "ocr" | "transcript" | "object" | "topic" | "question" | "answer" | "evidence";

export interface GraphNode {
  id: string;
  label: string;
  type: NodeType;
  x: number; // percentage (0 to 100)
  y: number; // percentage (0 to 100)
  iconName: string;
  color: string;
  details: string;
}

export interface GraphEdge {
  id: string;
  sourceId: string;
  targetId: string;
  label: "mentions" | "contains" | "references" | "explains" | "supports" | "related";
}

export interface EvidenceItem {
  id: string;
  nodeId: string;
  timestamp: string;
  startSec: number;
  endSec: number;
  sourceType: "transcript" | "ocr" | "scene" | "visual";
  title: string;
  rank: number;
  confidence: number;
  quality: EvidenceQuality;
  transcriptQuote?: string;
  ocrText?: string;
  sceneDescription?: string;
  speaker?: string;
  explanation: string;
  frameGradient: string;
}

export const MOCK_GRAPH_NODES: GraphNode[] = [
  {
    id: "n-q1",
    label: "User Question",
    type: "question",
    x: 12,
    y: 48,
    iconName: "HelpCircle",
    color: "bg-indigo-500 text-white border-indigo-400",
    details: "When was MCP compared to HTTP REST?"
  },
  {
    id: "n-ans",
    label: "AI Answer Node",
    type: "answer",
    x: 48,
    y: 20,
    iconName: "Sparkles",
    color: "bg-cyan-500 text-slate-950 border-cyan-300 font-bold",
    details: "MCP vs HTTP compared at 05:12 (Scene 2) with 40% token savings."
  },
  {
    id: "n-ev1",
    label: "Evidence Span #1",
    type: "evidence",
    x: 48,
    y: 52,
    iconName: "ShieldCheck",
    color: "bg-emerald-500 text-white border-emerald-400 font-bold",
    details: "Rank #1 Evidence Span [05:12 – 08:32] (ChromaDB similarity 0.982)"
  },
  {
    id: "n-sc2",
    label: "Scene 2: Spec",
    type: "scene",
    x: 82,
    y: 22,
    iconName: "Video",
    color: "bg-violet-500 text-white border-violet-400",
    details: "Scene 2 Chapter: Model Context Protocol Specifications [05:12 – 15:45]"
  },
  {
    id: "n-ocr1",
    label: "OCR Slide #1",
    type: "ocr",
    x: 82,
    y: 52,
    iconName: "Layers",
    color: "bg-amber-500 text-white border-amber-400",
    details: "OCR Text: JSON-RPC 2.0 Spec: stdio / Server-Sent Events (SSE)"
  },
  {
    id: "n-spk1",
    label: "Speaker 1",
    type: "speaker",
    x: 82,
    y: 82,
    iconName: "Mic",
    color: "bg-pink-500 text-white border-pink-400",
    details: "Speaker 1 (Presenter): Delivery of protocol transport specs."
  },
  {
    id: "n-top1",
    label: "Topic: MCP Spec",
    type: "topic",
    x: 18,
    y: 82,
    iconName: "Database",
    color: "bg-blue-500 text-white border-blue-400",
    details: "Semantic Topic Cluster: Model Context Protocol Specifications"
  }
];

export const MOCK_GRAPH_EDGES: GraphEdge[] = [
  { id: "e1", sourceId: "n-q1", targetId: "n-ans", label: "explains" },
  { id: "e2", sourceId: "n-ans", targetId: "n-ev1", label: "supports" },
  { id: "e3", sourceId: "n-ev1", targetId: "n-sc2", label: "contains" },
  { id: "e4", sourceId: "n-ev1", targetId: "n-ocr1", label: "references" },
  { id: "e5", sourceId: "n-ev1", targetId: "n-spk1", label: "mentions" },
  { id: "e6", sourceId: "n-ans", targetId: "n-top1", label: "related" }
];

export const MOCK_EVIDENCE_ITEMS: EvidenceItem[] = [
  {
    id: "ev-item-1",
    nodeId: "n-ev1",
    timestamp: "05:12 – 08:32",
    startSec: 312,
    endSec: 512,
    sourceType: "transcript",
    title: "Protocol Definition & Transport Comparison",
    rank: 1,
    confidence: 98,
    quality: "grounded",
    transcriptQuote: "Model Context Protocol solves this by introducing bidirectional JSON-RPC transport layers. The client application connects directly to specialized tool servers via stdio or SSE.",
    ocrText: "JSON-RPC 2.0 Spec: stdio / Server-Sent Events (SSE)",
    sceneDescription: "Scene 2: Model Context Protocol Specifications [05:12 – 15:45]",
    speaker: "Speaker 1 (Presenter)",
    explanation: "This evidence segment provides direct audio-visual proof comparing MCP to HTTP REST APIs, verifying the AI's explanation of 40% token overhead reduction.",
    frameGradient: "from-slate-900 via-violet-950 to-indigo-900"
  },
  {
    id: "ev-item-2",
    nodeId: "n-ocr1",
    timestamp: "24:10 – 27:00",
    startSec: 1450,
    endSec: 1620,
    sourceType: "ocr",
    title: "Token Overhead Cost Benchmark Slide",
    rank: 2,
    confidence: 96,
    quality: "verified",
    transcriptQuote: "By transmitting only canonical evidence spans, API costs scale linearly with questions rather than video length.",
    ocrText: "Cost Benchmark Chart: -40% Token Overhead per Query",
    sceneDescription: "Scene 3: Bidirectional Transport & Tool Execution [15:45 – 32:30]",
    speaker: "Speaker 2 (Co-host)",
    explanation: "OCR text extraction confirms the cost savings figure displayed on the presentation slide chart.",
    frameGradient: "from-cyan-950 via-slate-900 to-indigo-950"
  },
  {
    id: "ev-item-3",
    nodeId: "n-sc2",
    timestamp: "12:45 – 15:10",
    startSec: 765,
    endSec: 910,
    sourceType: "scene",
    title: "Security Bounds & User Permission Prompts",
    rank: 3,
    confidence: 92,
    quality: "partial",
    transcriptQuote: "We enforce strict permission prompts before any tool call executes file operations or external network requests.",
    ocrText: "Security Bounds: Permission Prompts & Local Vector Indexing",
    sceneDescription: "Scene 2: Model Context Protocol Specifications [05:12 – 15:45]",
    speaker: "Speaker 2 (Co-host)",
    explanation: "Secondary evidence span verifying security boundaries and local permission controls.",
    frameGradient: "from-indigo-950 via-slate-900 to-cyan-900"
  }
];
