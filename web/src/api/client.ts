import axios, { type AxiosError, type AxiosInstance, type AxiosRequestConfig } from "axios";
import { toast } from "sonner";

export interface ApiErrorPayload {
  detail?: string | Array<{ msg?: string; message?: string }>;
  error?: { message?: string };
}

export class ApiError extends Error {
  status?: number;
  payload?: unknown;

  constructor(message: string, status?: number, payload?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload;
  }
}

const baseURL = (import.meta.env.VITE_API_URL || "http://localhost:8001").replace(/\/+$/, "");

export const apiClient: AxiosInstance = axios.create({
  baseURL,
  timeout: 30_000,
  headers: {
    Accept: "application/json"
  }
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorPayload>) => {
    const status = error.response?.status;
    const detail = error.response?.data?.detail;
    let message = error.message || "An unexpected backend error occurred.";

    if (typeof detail === "string") {
      message = detail;
    } else if (Array.isArray(detail)) {
      message = detail.map((entry) => entry?.msg || entry?.message || "Unknown error").join(", ");
    } else if (error.code === "ECONNABORTED") {
      message = "Request timed out. The backend did not respond in time.";
    } else if (!error.response) {
      message = "Cannot connect to the backend server.";
    }

    if (status && status >= 400 && status !== 404) {
      toast.error(message);
    }

    return Promise.reject(new ApiError(message, status, error.response?.data));
  }
);

export async function apiGet<T>(url: string, config?: AxiosRequestConfig) {
  const response = await apiClient.get<T>(url, config);
  return response.data;
}

export async function apiPost<T, TBody = unknown>(url: string, body?: TBody, config?: AxiosRequestConfig) {
  const response = await apiClient.post<T>(url, body, config);
  return response.data;
}

export async function apiDelete<T>(url: string, config?: AxiosRequestConfig) {
  const response = await apiClient.delete<T>(url, config);
  return response.data;
}

export async function apiPatch<T, TBody = unknown>(url: string, body?: TBody, config?: AxiosRequestConfig) {
  const response = await apiClient.patch<T>(url, body, config);
  return response.data;
}
