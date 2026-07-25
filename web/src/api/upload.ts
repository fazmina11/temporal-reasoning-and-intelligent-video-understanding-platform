import { apiPost } from "@/api/client";
import type { ApiUploadResponse } from "@/types/api";

export async function uploadVideo(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  return apiPost<ApiUploadResponse, FormData>("/upload", formData, {
    headers: {
      "Content-Type": "multipart/form-data"
    }
  });
}
