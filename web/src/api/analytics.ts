import { apiGet } from "@/api/client";
import type { ApiAnalyticsOverview } from "@/types/api";

export async function getAnalytics() {
  return apiGet<ApiAnalyticsOverview>("/analytics/overview");
}
