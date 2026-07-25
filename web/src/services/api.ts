import { apiClient, ApiError } from "@/api/client";
import { askQuestion as askQuestionRequest } from "@/api/ask";
import { getProcessingStatus } from "@/api/processing";

export { apiClient, ApiError };
export const api = apiClient;
export { getVideos, getVideoManifest } from "@/api/videos";
export { uploadVideo as uploadVideoFile } from "@/api/upload";
export const getVideoStatus = getProcessingStatus;

export async function askQuestion(videoId: string, query: string) {
  return askQuestionRequest({ video_id: videoId, query });
}

export default apiClient;
