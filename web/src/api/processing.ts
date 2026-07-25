import { apiGet } from "@/api/client";
import type { ApiProcessingStatus } from "@/types/api";

export async function getProcessingStatus(videoId: string) {
  return apiGet<ApiProcessingStatus>(`/status/${videoId}`);
}

export function createProcessingEventSource(videoId: string) {
  const baseUrl = (import.meta.env.VITE_API_URL || "http://localhost:8001").replace(/\/+$/, "");
  return new EventSource(`${baseUrl}/videos/${encodeURIComponent(videoId)}/progress/stream`);
}
