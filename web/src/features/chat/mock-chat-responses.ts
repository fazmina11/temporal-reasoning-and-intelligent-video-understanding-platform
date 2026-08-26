import type { ChatMessage } from "@/types/api";

/**
 * Initial welcome message displayed when the chat panel first loads.
 * Real AI responses come from POST /ask — this file is NOT used for
 * generating answers.
 */
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
