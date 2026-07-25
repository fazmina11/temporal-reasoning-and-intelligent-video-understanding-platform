export interface TranscriptBlock {
  id: string;
  startSec: number;
  endSec: number;
  timestamp: string;
  speakerId: string;
  speakerName: string;
  speakerAvatar: string;
  speakerTone: "indigo" | "violet" | "cyan" | "emerald";
  text: string;
  confidence: number;
  language: string;
  hasOcr: boolean;
  ocrPreview?: string;
  hasVisualObject: boolean;
  sceneTitle?: string;
  sceneGradient?: string;
  citationCount: number;
  importanceScore: number;
  topicCluster: string;
  bookmarked?: boolean;
}

export const MOCK_TRANSCRIPT_BLOCKS: TranscriptBlock[] = [
  {
    id: "tb-1",
    startSec: 15,
    endSec: 160,
    timestamp: "00:15 – 02:40",
    speakerId: "spk-1",
    speakerName: "Speaker 1 (Presenter)",
    speakerAvatar: "S1",
    speakerTone: "indigo",
    text: "Welcome everyone to this technical deep dive comparing Model Context Protocol (MCP) and traditional HTTP REST API architectures. Today we will explore why standard REST endpoints create integration bottlenecks for AI agents.",
    confidence: 99,
    language: "English (en-US)",
    hasOcr: true,
    ocrPreview: "Title Slide: Model Context Protocol vs HTTP REST Architecture",
    hasVisualObject: true,
    sceneTitle: "Scene 1: Introduction & Context Limits",
    sceneGradient: "from-indigo-950 via-slate-900 to-cyan-900",
    citationCount: 3,
    importanceScore: 0.98,
    topicCluster: "Protocol Specifications"
  },
  {
    id: "tb-2",
    startSec: 165,
    endSec: 312,
    timestamp: "02:45 – 05:12",
    speakerId: "spk-1",
    speakerName: "Speaker 1 (Presenter)",
    speakerAvatar: "S1",
    speakerTone: "indigo",
    text: "Traditional HTTP REST endpoints require transmitting full conversation histories on every request. As video transcripts grow to thousands of lines, sending uncompressed text leads to severe context window inflation.",
    confidence: 97,
    language: "English (en-US)",
    hasOcr: true,
    ocrPreview: "Diagram: HTTP Context Window Inflation (40% Token Overhead)",
    hasVisualObject: true,
    sceneTitle: "Scene 1: Introduction & Context Limits",
    sceneGradient: "from-indigo-950 via-slate-900 to-cyan-900",
    citationCount: 2,
    importanceScore: 0.94,
    topicCluster: "Context Windows"
  },
  {
    id: "tb-3",
    startSec: 315,
    endSec: 540,
    timestamp: "05:15 – 09:00",
    speakerId: "spk-1",
    speakerName: "Speaker 1 (Presenter)",
    speakerAvatar: "S1",
    speakerTone: "indigo",
    text: "Model Context Protocol solves this by introducing bidirectional JSON-RPC transport layers. The client application connects directly to specialized tool servers via stdio or Server-Sent Events (SSE).",
    confidence: 98,
    language: "English (en-US)",
    hasOcr: true,
    ocrPreview: "JSON-RPC 2.0 Spec: stdio / Server-Sent Events (SSE)",
    hasVisualObject: true,
    sceneTitle: "Scene 2: Model Context Protocol Specifications",
    sceneGradient: "from-slate-900 via-violet-950 to-indigo-900",
    citationCount: 4,
    importanceScore: 0.99,
    topicCluster: "Protocol Specifications"
  },
  {
    id: "tb-4",
    startSec: 545,
    endSec: 760,
    timestamp: "09:05 – 12:40",
    speakerId: "spk-2",
    speakerName: "Speaker 2 (Co-host)",
    speakerAvatar: "S2",
    speakerTone: "violet",
    text: "Let's examine how tool execution schemas operate. When an AI agent decides to read a file or query ChromaDB vector memory, it dispatches a structured tools/call request with exact parameter bounds.",
    confidence: 96,
    language: "English (en-US)",
    hasOcr: true,
    ocrPreview: "Schema: tools/call { name: 'query_vector_memory', arguments: { query: 'string' } }",
    hasVisualObject: true,
    sceneTitle: "Scene 2: Model Context Protocol Specifications",
    sceneGradient: "from-slate-900 via-violet-950 to-indigo-900",
    citationCount: 3,
    importanceScore: 0.95,
    topicCluster: "Tool Execution"
  },
  {
    id: "tb-5",
    startSec: 765,
    endSec: 945,
    timestamp: "12:45 – 15:45",
    speakerId: "spk-2",
    speakerName: "Speaker 2 (Co-host)",
    speakerAvatar: "S2",
    speakerTone: "violet",
    text: "Security bounds are paramount. Notice that every tool call requires an explicit user permission check. Unsanitized terminal commands or wildcard directory access are rejected automatically.",
    confidence: 95,
    language: "English (en-US)",
    hasOcr: false,
    hasVisualObject: false,
    sceneTitle: "Scene 2: Model Context Protocol Specifications",
    sceneGradient: "from-slate-900 via-violet-950 to-indigo-900",
    citationCount: 2,
    importanceScore: 0.92,
    topicCluster: "Security Bounds"
  },
  {
    id: "tb-6",
    startSec: 950,
    endSec: 1200,
    timestamp: "15:50 – 20:00",
    speakerId: "spk-1",
    speakerName: "Speaker 1 (Presenter)",
    speakerAvatar: "S1",
    speakerTone: "indigo",
    text: "Now let's transition to live demonstration in VS Code. We have configured an MCP server that parses video scene manifests and exposes ChromaDB vector nodes directly to our AI chat window.",
    confidence: 97,
    language: "English (en-US)",
    hasOcr: true,
    ocrPreview: "VS Code Editor: mcp.config.json & ChromaDB Vector Host",
    hasVisualObject: true,
    sceneTitle: "Scene 3: Bidirectional Transport & Tool Execution",
    sceneGradient: "from-cyan-950 via-slate-900 to-indigo-950",
    citationCount: 3,
    importanceScore: 0.96,
    topicCluster: "Live Demonstration"
  },
  {
    id: "tb-7",
    startSec: 1205,
    endSec: 1450,
    timestamp: "20:05 – 24:10",
    speakerId: "spk-2",
    speakerName: "Speaker 2 (Co-host)",
    speakerAvatar: "S2",
    speakerTone: "violet",
    text: "When a user asks 'When was the service contract mentioned?', the agent doesn't scan raw frames manually. It queries ChromaDB vector embeddings, matches canonical evidence spans, and jumps to timestamp 12:45.",
    confidence: 98,
    language: "English (en-US)",
    hasOcr: true,
    ocrPreview: "Vector Index: span_0412 (ChromaDB Similarity: 0.982)",
    hasVisualObject: true,
    sceneTitle: "Scene 3: Bidirectional Transport & Tool Execution",
    sceneGradient: "from-cyan-950 via-slate-900 to-indigo-950",
    citationCount: 4,
    importanceScore: 0.97,
    topicCluster: "Semantic Search"
  },
  {
    id: "tb-8",
    startSec: 1455,
    endSec: 1700,
    timestamp: "24:15 – 28:20",
    speakerId: "spk-1",
    speakerName: "Speaker 1 (Presenter)",
    speakerAvatar: "S1",
    speakerTone: "indigo",
    text: "Let's review cost benchmarks. By transmitting only verified evidence spans rather than raw 40-minute audio streams, token overhead per query is reduced by 40%, saving substantial API costs.",
    confidence: 96,
    language: "English (en-US)",
    hasOcr: true,
    ocrPreview: "Cost Benchmark Chart: -40% Token Overhead per Query",
    hasVisualObject: true,
    sceneTitle: "Scene 3: Bidirectional Transport & Tool Execution",
    sceneGradient: "from-cyan-950 via-slate-900 to-indigo-950",
    citationCount: 2,
    importanceScore: 0.93,
    topicCluster: "Cost Benchmarks"
  },
  {
    id: "tb-9",
    startSec: 1705,
    endSec: 1950,
    timestamp: "28:25 – 32:30",
    speakerId: "spk-2",
    speakerName: "Speaker 2 (Co-host)",
    speakerAvatar: "S2",
    speakerTone: "violet",
    text: "In conclusion, VideoSceneRAG turns unstructured video streams into indexed, temporal memory graphs. Developers can build agentic tools using our open source SDKs today.",
    confidence: 99,
    language: "English (en-US)",
    hasOcr: true,
    ocrPreview: "Summary Slide: Open Source SDKs Available",
    hasVisualObject: true,
    sceneTitle: "Scene 4: Evaluation Benchmark & Q&A Session",
    sceneGradient: "from-amber-950 via-slate-900 to-rose-950",
    citationCount: 3,
    importanceScore: 0.98,
    topicCluster: "Summary & SDKs"
  },
  {
    id: "tb-10",
    startSec: 1955,
    endSec: 2200,
    timestamp: "32:35 – 36:40",
    speakerId: "spk-1",
    speakerName: "Speaker 1 (Presenter)",
    speakerAvatar: "S1",
    speakerTone: "indigo",
    text: "We will now open the floor to Q&A questions from our engineering leads in the audience.",
    confidence: 94,
    language: "English (en-US)",
    hasOcr: false,
    hasVisualObject: false,
    sceneTitle: "Scene 4: Evaluation Benchmark & Q&A Session",
    sceneGradient: "from-amber-950 via-slate-900 to-rose-950",
    citationCount: 1,
    importanceScore: 0.85,
    topicCluster: "Q&A Session"
  }
];
