export interface TimelineMarkerData {
  id: string;
  trackId: "scenes" | "transcript" | "ocr" | "speakers" | "citations" | "topics" | "events";
  startSec: number;
  endSec: number;
  timeLabel: string;
  title: string;
  summary: string;
  transcriptQuote?: string;
  ocrText?: string;
  color: string;
  gradient?: string;
  speaker?: string;
  badge?: string;
}

export interface TimelineTrackData {
  id: "scenes" | "transcript" | "ocr" | "speakers" | "citations" | "topics" | "events";
  label: string;
  iconName: string;
  color: string;
  badge: string;
  visible: boolean;
  expanded: boolean;
  markers: TimelineMarkerData[];
}

export interface OverviewChapter {
  id: string;
  title: string;
  startSec: number;
  endSec: number;
  gradient: string;
}

export const TOTAL_DURATION_SEC = 2538; // 42:18

export const OVERVIEW_CHAPTERS: OverviewChapter[] = [
  { id: "ch1", title: "1. Ingestion & Limits", startSec: 0, endSec: 312, gradient: "from-indigo-600 to-cyan-500" },
  { id: "ch2", title: "2. MCP Specifications", startSec: 312, endSec: 945, gradient: "from-violet-600 to-indigo-600" },
  { id: "ch3", title: "3. Transport & Tool Execution", startSec: 945, endSec: 1950, gradient: "from-cyan-600 to-blue-600" },
  { id: "ch4", title: "4. Summary & RAG Evaluation", startSec: 1950, endSec: 2538, gradient: "from-amber-600 to-rose-600" }
];

export const INITIAL_TIMELINE_TRACKS: TimelineTrackData[] = [
  {
    id: "scenes",
    label: "Scenes",
    iconName: "Video",
    color: "text-indigo-400 border-indigo-500/30 bg-indigo-500/10",
    badge: "16 Scenes",
    visible: true,
    expanded: true,
    markers: [
      {
        id: "sc-1",
        trackId: "scenes",
        startSec: 0,
        endSec: 312,
        timeLabel: "00:00 – 05:12",
        title: "Scene 1: Introduction & Context Limits",
        summary: "Overview of current RAG limitations and the need for standard context schemas. Reviews why traditional REST creates integration bottlenecks.",
        transcriptQuote: "Welcome everyone to this technical deep dive comparing MCP and HTTP REST architecture.",
        color: "bg-indigo-500",
        gradient: "from-indigo-950 via-slate-900 to-cyan-900"
      },
      {
        id: "sc-2",
        trackId: "scenes",
        startSec: 312,
        endSec: 945,
        timeLabel: "05:12 – 15:45",
        title: "Scene 2: Model Context Protocol Specifications",
        summary: "Deep dive into the MCP stack. Reviews client-server architectures, transport adapters (stdio & SSE), and message serialization.",
        transcriptQuote: "Let's look at how bidirectional transport channels optimize context window usage.",
        ocrText: "Diagram: Client <-> MCP Host <-> Tool Server",
        color: "bg-violet-500",
        gradient: "from-slate-900 via-violet-950 to-indigo-900"
      },
      {
        id: "sc-3",
        trackId: "scenes",
        startSec: 945,
        endSec: 1950,
        timeLabel: "15:45 – 32:30",
        title: "Scene 3: Bidirectional Transport & Tool Execution",
        summary: "Walkthrough of tool execution loops. Live demonstration of schemas, parameter passing, and security permission grants.",
        transcriptQuote: "We enforce strict permission prompts before any tool call executes file operations.",
        ocrText: "JSON-RPC 2.0 Payload: { method: 'tools/call' }",
        color: "bg-cyan-500",
        gradient: "from-cyan-950 via-slate-900 to-indigo-950"
      },
      {
        id: "sc-4",
        trackId: "scenes",
        startSec: 1950,
        endSec: 2538,
        timeLabel: "32:30 – 42:18",
        title: "Scene 4: Evaluation Benchmark & Q&A Session",
        summary: "Comparison results across N10 evaluation suite. Audience questions regarding latency, WebSocket integrations, and future roadmaps.",
        transcriptQuote: "In summary, MCP reduces prompt token overhead while providing verifiable audit trails.",
        color: "bg-amber-500",
        gradient: "from-amber-950 via-slate-900 to-rose-950"
      }
    ]
  },
  {
    id: "transcript",
    label: "Transcript Spans",
    iconName: "FileText",
    color: "text-emerald-400 border-emerald-500/30 bg-emerald-500/10",
    badge: "248 Spans",
    visible: true,
    expanded: true,
    markers: [
      {
        id: "tr-1",
        trackId: "transcript",
        startSec: 15,
        endSec: 240,
        timeLabel: "00:15 – 04:00",
        title: "Introductory Remarks",
        summary: "Speaker introduces the problem statement regarding token limits in RAG pipelines.",
        transcriptQuote: "Traditional HTTP endpoints require sending long conversation histories on every request.",
        speaker: "Speaker 1",
        color: "bg-emerald-500"
      },
      {
        id: "tr-2",
        trackId: "transcript",
        startSec: 320,
        endSec: 680,
        timeLabel: "05:20 – 11:20",
        title: "MCP Architecture Breakdown",
        summary: "Detailed explanation of host application roles and tool server connections.",
        transcriptQuote: "MCP decouples prompt engineering from external data ingestion through standardized RPC messages.",
        speaker: "Speaker 1",
        color: "bg-emerald-500"
      },
      {
        id: "tr-3",
        trackId: "transcript",
        startSec: 1020,
        endSec: 1480,
        timeLabel: "17:00 – 24:40",
        title: "Tool Execution Security",
        summary: "Discussion on sandbox boundaries, user confirmation dialogs, and security policies.",
        transcriptQuote: "Security bounds ensure AI agents cannot read unauthorized paths.",
        speaker: "Speaker 2",
        color: "bg-emerald-400"
      },
      {
        id: "tr-4",
        trackId: "transcript",
        startSec: 1980,
        endSec: 2400,
        timeLabel: "33:00 – 40:00",
        title: "Live Q&A Discussion",
        summary: "Answering questions from engineering leads regarding SDK availability.",
        transcriptQuote: "TypeScript and Python SDKs are available today in open source.",
        speaker: "Speaker 2",
        color: "bg-emerald-400"
      }
    ]
  },
  {
    id: "ocr",
    label: "OCR Detections",
    iconName: "Layers",
    color: "text-amber-400 border-amber-500/30 bg-amber-500/10",
    badge: "12 Key Slides",
    visible: true,
    expanded: false,
    markers: [
      {
        id: "ocr-1",
        trackId: "ocr",
        startSec: 30,
        endSec: 300,
        timeLabel: "00:30 – 05:00",
        title: "Title Slide OCR",
        summary: "Detected title slide text overlay",
        ocrText: "Model Context Protocol vs HTTP REST Architecture",
        color: "bg-amber-500"
      },
      {
        id: "ocr-2",
        trackId: "ocr",
        startSec: 330,
        endSec: 900,
        timeLabel: "05:30 – 15:00",
        title: "Architecture Diagram OCR",
        summary: "Detected diagram slide labels and RPC transport definitions",
        ocrText: "JSON-RPC 2.0: stdio / Server-Sent Events (SSE)",
        color: "bg-amber-500"
      },
      {
        id: "ocr-3",
        trackId: "ocr",
        startSec: 1450,
        endSec: 1900,
        timeLabel: "24:10 – 31:40",
        title: "Benchmark Chart OCR",
        summary: "Detected performance metric labels and token reduction stats",
        ocrText: "Token Overhead: -40% | Latency: 140ms",
        color: "bg-amber-500"
      }
    ]
  },
  {
    id: "speakers",
    label: "Speakers Diarization",
    iconName: "Mic",
    color: "text-violet-400 border-violet-500/30 bg-violet-500/10",
    badge: "2 Speakers",
    visible: true,
    expanded: false,
    markers: [
      {
        id: "spk-1",
        trackId: "speakers",
        startSec: 0,
        endSec: 980,
        timeLabel: "00:00 – 16:20",
        title: "Speaker 1 (Presenter)",
        summary: "Primary presenter delivering technical slides and protocol specs.",
        speaker: "Speaker 1 (General American)",
        color: "bg-indigo-500"
      },
      {
        id: "spk-2",
        trackId: "speakers",
        startSec: 980,
        endSec: 2538,
        timeLabel: "16:20 – 42:18",
        title: "Speaker 2 (Co-host)",
        summary: "Co-host demonstrating live tool execution and answering Q&A.",
        speaker: "Speaker 2 (British Accent)",
        color: "bg-violet-500"
      }
    ]
  },
  {
    id: "citations",
    label: "AI Evidence Citations",
    iconName: "ShieldCheck",
    color: "text-cyan-400 border-cyan-500/30 bg-cyan-500/10",
    badge: "6 Anchors",
    visible: true,
    expanded: true,
    markers: [
      {
        id: "cit-m-1",
        trackId: "citations",
        startSec: 312,
        endSec: 512,
        timeLabel: "05:12 – 08:32",
        title: "Canonical Evidence: Protocol Definition",
        summary: "ChromaDB vector score 0.982. Grounded evidence for MCP spec query.",
        transcriptQuote: "MCP decouples prompt engineering from external data ingestion.",
        badge: "Score: 0.982",
        color: "bg-cyan-400"
      },
      {
        id: "cit-m-2",
        trackId: "citations",
        startSec: 1450,
        endSec: 1620,
        timeLabel: "24:10 – 27:00",
        title: "Canonical Evidence: Token Reduction",
        summary: "ChromaDB vector score 0.962. Grounded evidence for token pricing query.",
        transcriptQuote: "API costs scale linearly with questions rather than video length.",
        badge: "Score: 0.962",
        color: "bg-cyan-400"
      }
    ]
  },
  {
    id: "topics",
    label: "Key Topics",
    iconName: "Database",
    color: "text-pink-400 border-pink-500/30 bg-pink-500/10",
    badge: "7 Clusters",
    visible: true,
    expanded: false,
    markers: [
      {
        id: "top-1",
        trackId: "topics",
        startSec: 0,
        endSec: 312,
        timeLabel: "00:00 – 05:12",
        title: "Topic: Context Windows & Limits",
        summary: "Semantic topic cluster mapping RAG context window limits.",
        color: "bg-pink-500"
      },
      {
        id: "top-2",
        trackId: "topics",
        startSec: 312,
        endSec: 1200,
        timeLabel: "05:12 – 20:00",
        title: "Topic: MCP Specification & Transport",
        summary: "Semantic topic cluster mapping stdio and SSE transport protocols.",
        color: "bg-pink-500"
      },
      {
        id: "top-3",
        trackId: "topics",
        startSec: 1200,
        endSec: 2538,
        timeLabel: "20:00 – 42:18",
        title: "Topic: Tool Execution & Evaluation",
        summary: "Semantic topic cluster mapping permission prompts and benchmark scores.",
        color: "bg-pink-500"
      }
    ]
  },
  {
    id: "events",
    label: "Milestone Events",
    iconName: "Sparkles",
    color: "text-blue-400 border-blue-500/30 bg-blue-500/10",
    badge: "4 Milestones",
    visible: true,
    expanded: false,
    markers: [
      {
        id: "ev-1",
        trackId: "events",
        startSec: 0,
        endSec: 30,
        timeLabel: "00:00",
        title: "Event: Video Start & Title Slide",
        summary: "Video stream initialized. Ingestion manifest verified.",
        color: "bg-blue-400"
      },
      {
        id: "ev-2",
        trackId: "events",
        startSec: 945,
        endSec: 975,
        timeLabel: "15:45",
        title: "Event: Demo Transition",
        summary: "Presenter switches screen sharing to live VS Code tool demonstration.",
        color: "bg-blue-400"
      },
      {
        id: "ev-3",
        trackId: "events",
        startSec: 1950,
        endSec: 1980,
        timeLabel: "32:30",
        title: "Event: Q&A Session Start",
        summary: "Transition from presentation slides to live audience question answering.",
        color: "bg-blue-400"
      }
    ]
  }
];
