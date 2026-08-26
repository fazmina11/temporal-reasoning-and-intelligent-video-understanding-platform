import { apiGet } from "@/api/client";

export interface HealthResponse {
  status: "ok" | "degraded";
  service: string;
  timestamp: string;
  details?: {
    processing_jobs?: number;
  };
}

export interface ProviderKeyStatus {
  key_index: number;
  key_suffix: string;
  available: boolean;
  quota_exhausted: boolean;
  requests_today: number;
  last_error: string;
}

export interface ProviderStatus {
  groq: {
    quota_exhausted: boolean;
    total_keys: number;
    available_keys: number;
    keys: ProviderKeyStatus[];
  };
  gemini: {
    quota_exhausted: boolean;
    requests_today: number;
    last_error: string;
  };
}

export async function getHealthLive() {
  return apiGet<HealthResponse>("/health/live");
}

export async function getHealthReady() {
  return apiGet<HealthResponse>("/health/ready");
}

export async function getProviderStatus() {
  return apiGet<ProviderStatus>("/provider-status");
}
