import { apiDelete, apiGet, apiPost } from "@/api/client";
import type { ApiQuestionHistoryResponse, ApiManifest, ApiVideoLifecycleResponse, ApiVideoSummary } from "@/types/api";

export interface VideosResponse {
  videos: ApiVideoSummary[];
}

export async function getVideos() {
  return apiGet<VideosResponse>("/videos");
}

export async function getVideoManifest(videoId: string) {
  return apiGet<ApiManifest>(`/videos/${videoId}`);
}

export const getVideo = getVideoManifest;

export async function deleteVideo(videoId: string) {
  return apiDelete<ApiVideoLifecycleResponse>(`/videos/${videoId}`);
}

export async function retryVideo(videoId: string) {
  return apiPost<ApiVideoLifecycleResponse>(`/videos/${videoId}/retry`);
}

export async function cancelVideo(videoId: string) {
  return apiPost<ApiVideoLifecycleResponse>(`/videos/${videoId}/cancel`);
}

export async function getVideoQuestions(videoId: string) {
  return apiGet<ApiQuestionHistoryResponse>(`/videos/${videoId}/questions`);
}
