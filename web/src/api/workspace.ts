import { apiGet } from "@/api/client";
import type { ApiArtifactDocument, ApiManifest, ApiTimelineDocument, ApiTranscriptDocument } from "@/types/api";

export async function getWorkspace(videoId: string) {
  return apiGet<ApiManifest>(`/videos/${videoId}`);
}

export async function getTranscript(videoId: string) {
  return apiGet<ApiTranscriptDocument>(`/videos/${videoId}/transcript`);
}

export async function getTimeline(videoId: string) {
  return apiGet<ApiTimelineDocument>(`/videos/${videoId}/timeline`);
}

export async function getOCR(videoId: string) {
  return apiGet<ApiArtifactDocument>(`/visual-artifacts/${videoId}`);
}

export async function getScenes(videoId: string) {
  return apiGet<ApiArtifactDocument>(`/semantic-chunks/${videoId}`);
}

export async function getBoundaries(videoId: string) {
  return apiGet<ApiArtifactDocument>(`/boundaries/${videoId}`);
}

export async function getFrames(videoId: string) {
  return apiGet<ApiArtifactDocument>(`/frames/${videoId}`);
}

export async function getChunkValidation(videoId: string) {
  return apiGet<ApiArtifactDocument>(`/chunk-validation/${videoId}`);
}
