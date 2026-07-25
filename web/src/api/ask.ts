import { apiGet, apiPost } from "@/api/client";
import type { ApiAskDebugResponse, ApiAskRequest, ApiAskResponse } from "@/types/api";

export async function askQuestion(payload: ApiAskRequest) {
  return apiPost<ApiAskResponse, ApiAskRequest>("/ask", payload);
}

export async function askQuestionDebug(payload: ApiAskRequest) {
  return apiPost<ApiAskDebugResponse, ApiAskRequest>("/ask-debug", payload);
}
