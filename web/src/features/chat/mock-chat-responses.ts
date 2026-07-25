export interface CitationItem {
  id: string;
  timestamp: string;
  timestampEnd: string;
  frameGradient: string;
  transcriptSnippet: string;
  ocrSnippet?: string;
  score: number;
  type: "transcript" | "ocr" | "scene";
}

export interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  text: string;
  timestamp: string;
  confidenceScore?: number;
  retrievalStatus?: string;
  citations?: CitationItem[];
  bookmarked?: boolean;
}

export const INITIAL_CHAT_MESSAGES: ChatMessage[] = [
  {
    id: "msg-welcome",
    sender: "ai",
    text: "Hello! I am VideoSceneRAG's temporal memory engine. Ask me any question about this video to locate exact timestamps, visual OCR slide text, speaker quotes, or evidence summaries.",
    timestamp: "10:20 AM",
    confidenceScore: 99,
    retrievalStatus: "System Ready",
    citations: []
  }
];

export function generateMockAiResponse(userQuery: string): ChatMessage {
  const queryLower = userQuery.toLowerCase();
  const now = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const messageId = `msg-ai-${Date.now()}`;

  if (queryLower.includes("summarize") || queryLower.includes("meeting") || queryLower.includes("overview")) {
    return {
      id: messageId,
      sender: "ai",
      text: "This video provides a technical comparison between Model Context Protocol (MCP) and traditional HTTP REST APIs. The speaker outlines why standard REST APIs create context integration bottlenecks for AI agents, demonstrates MCP's bidirectional transport layers (stdio & SSE), and reviews schema syncing across tool execution boundaries.",
      timestamp: now,
      confidenceScore: 98,
      retrievalStatus: "Verified Grounded Summary",
      citations: [
        {
          id: "cit-1",
          timestamp: "00:15",
          timestampEnd: "05:12",
          frameGradient: "from-indigo-950 via-slate-900 to-cyan-900",
          transcriptSnippet: "Welcome everyone to this technical deep dive comparing MCP and HTTP REST architecture.",
          ocrSnippet: "Title Slide: Model Context Protocol vs HTTP REST Architecture",
          score: 0.982,
          type: "scene"
        },
        {
          id: "cit-2",
          timestamp: "05:12",
          timestampEnd: "15:45",
          frameGradient: "from-slate-900 via-violet-950 to-indigo-900",
          transcriptSnippet: "Let's look at how bidirectional transport channels optimize context window usage without custom REST wrappers.",
          ocrSnippet: "Diagram: Client <-> MCP Host <-> Tool Server (stdio/SSE)",
          score: 0.954,
          type: "transcript"
        },
        {
          id: "cit-3",
          timestamp: "32:30",
          timestampEnd: "42:18",
          frameGradient: "from-amber-950 via-slate-900 to-rose-950",
          transcriptSnippet: "In summary, MCP reduces prompt token overhead while providing verifiable audit trails.",
          ocrSnippet: "Summary: 40% Token Overhead Reduction",
          score: 0.921,
          type: "ocr"
        }
      ]
    };
  }

  if (queryLower.includes("ocr") || queryLower.includes("text") || queryLower.includes("slide")) {
    return {
      id: messageId,
      sender: "ai",
      text: "I scanned the visual frames and retrieved 4,200 OCR character tokens. Key slide titles detected include 'Model Context Protocol Specifications', 'Bidirectional JSON-RPC Transport', and 'Schema Synchronization Parameters'.",
      timestamp: now,
      confidenceScore: 96,
      retrievalStatus: "OCR Visual Text Search",
      citations: [
        {
          id: "cit-ocr-1",
          timestamp: "05:12",
          timestampEnd: "08:30",
          frameGradient: "from-cyan-950 via-slate-900 to-indigo-950",
          transcriptSnippet: "As displayed on the screen, the protocol defines JSON-RPC message structures for tools and prompts.",
          ocrSnippet: "JSON-RPC 2.0 Payload: { jsonrpc: '2.0', method: 'tools/list' }",
          score: 0.975,
          type: "ocr"
        },
        {
          id: "cit-ocr-2",
          timestamp: "18:40",
          timestampEnd: "22:15",
          frameGradient: "from-indigo-950 via-slate-900 to-slate-950",
          transcriptSnippet: "Notice the parameter schema definitions on the left side of the slide diagram.",
          ocrSnippet: "Parameters: { type: 'object', properties: { query: { type: 'string' } } }",
          score: 0.941,
          type: "ocr"
        }
      ]
    };
  }

  if (queryLower.includes("contract") || queryLower.includes("legal") || queryLower.includes("agreement")) {
    return {
      id: messageId,
      sender: "ai",
      text: "The service agreement and security compliance policies were mentioned between [12:45 – 15:10]. The speaker highlights data privacy controls, tool execution permissions, and local vector indexing bounds.",
      timestamp: now,
      confidenceScore: 92,
      retrievalStatus: "Dialogue Evidence Match",
      citations: [
        {
          id: "cit-con-1",
          timestamp: "12:45",
          timestampEnd: "15:10",
          frameGradient: "from-slate-900 via-emerald-950 to-cyan-950",
          transcriptSnippet: "We enforce strict permission prompts before any tool call executes file operations or external requests.",
          ocrSnippet: "Security Bounds: Permission Prompts & Local Indexing",
          score: 0.938,
          type: "transcript"
        }
      ]
    };
  }

  if (queryLower.includes("pricing") || queryLower.includes("cost") || queryLower.includes("budget")) {
    return {
      id: messageId,
      sender: "ai",
      text: "Pricing and token efficiency were addressed at timestamp [24:18 – 27:05]. The presenter demonstrated that structured context retrieval cuts LLM API token overhead by ~40% compared to sending entire video transcripts.",
      timestamp: now,
      confidenceScore: 95,
      retrievalStatus: "Grounded Metric Match",
      citations: [
        {
          id: "cit-prc-1",
          timestamp: "24:18",
          timestampEnd: "27:05",
          frameGradient: "from-violet-950 via-slate-900 to-indigo-950",
          transcriptSnippet: "By transmitting only canonical evidence spans, API costs scale linearly with questions rather than video length.",
          ocrSnippet: "Cost Benchmark: -40% Token Overhead per Query",
          score: 0.962,
          type: "scene"
        }
      ]
    };
  }

  if (queryLower.includes("whiteboard") || queryLower.includes("diagram") || queryLower.includes("architecture")) {
    return {
      id: messageId,
      sender: "ai",
      text: "Found visual whiteboard diagrams at timestamp [08:20 – 12:15]. The diagram illustrates the host-server communication loop, ChromaDB vector embedding lookup, and temporal deduplication gates.",
      timestamp: now,
      confidenceScore: 97,
      retrievalStatus: "Visual Scene Match",
      citations: [
        {
          id: "cit-wb-1",
          timestamp: "08:20",
          timestampEnd: "12:15",
          frameGradient: "from-blue-950 via-slate-900 to-violet-950",
          transcriptSnippet: "Here on the whiteboard, you can see the 3-layer hierarchy: Video -> Manifest -> Temporal Evidence Spans.",
          ocrSnippet: "Whiteboard Notes: 1. Ingestion 2. Chunking 3. ChromaDB Vector Store",
          score: 0.971,
          type: "scene"
        }
      ]
    };
  }

  // Default intelligent response fallback
  return {
    id: messageId,
    sender: "ai",
    text: `Based on temporal memory retrieval for "${userQuery}", I identified 2 relevant evidence intervals. The discussion focuses on protocol specs, timeline anchors, and contextual verification.`,
    timestamp: now,
    confidenceScore: 89,
    retrievalStatus: "Temporal Retrieval Match",
    citations: [
      {
        id: `cit-gen-1`,
        timestamp: "04:12",
        timestampEnd: "07:30",
        frameGradient: "from-indigo-950 via-slate-900 to-cyan-950",
        transcriptSnippet: "The temporal reasoning engine resolves timestamp spans and links them directly to vector retrieval nodes.",
        ocrSnippet: "Retrieval Node: span_0412 (Confidence: 0.89)",
        score: 0.894,
        type: "transcript"
      },
      {
        id: `cit-gen-2`,
        timestamp: "16:45",
        timestampEnd: "19:20",
        frameGradient: "from-slate-900 via-violet-950 to-indigo-950",
        transcriptSnippet: "Users can jump directly to the exact frame where the visual evidence was captured.",
        ocrSnippet: "Frame Index: #412 (1080p)",
        score: 0.871,
        type: "ocr"
      }
    ]
  };
}
