import { useState, useEffect } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  Database,
  Globe,
  HardDrive,
  Layers,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
  XCircle,
  Zap
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/global/headers";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  getHealthLive,
  getHealthReady,
  getProviderStatus,
  type HealthResponse,
  type ProviderStatus
} from "@/api/health";
import { useVideos } from "@/hooks/api/use-videos";

const StatusDot = ({ ok }: { ok: boolean }) => (
  <span className={`inline-block h-2.5 w-2.5 rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`} />
);

export function SettingsPage() {
  const [healthLive, setHealthLive] = useState<HealthResponse | null>(null);
  const [healthReady, setHealthReady] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const { data: videosResponse } = useVideos();
  const videos = videosResponse?.videos ?? [];

  const fetchHealth = async () => {
    try {
      const [live, ready] = await Promise.allSettled([
        getHealthLive(),
        getHealthReady()
      ]);
      setHealthLive(live.status === "fulfilled" ? live.value : null);
      setHealthReady(ready.status === "fulfilled" ? ready.value : null);
      setHealthError(
        live.status === "rejected"
          ? "Cannot connect to backend server"
          : ready.status === "rejected"
            ? "Backend is running but not ready"
            : null
      );
    } catch {
      setHealthError("Cannot connect to backend server");
    }
  };

  const fetchProviders = async () => {
    try {
      const status = await getProviderStatus();
      setProviderStatus(status);
    } catch {
      // Provider status endpoint may not exist yet
    }
  };

  const refresh = async () => {
    setRefreshing(true);
    await Promise.all([fetchHealth(), fetchProviders()]);
    setRefreshing(false);
    toast.success("System status refreshed.");
  };

  useEffect(() => {
    Promise.all([fetchHealth(), fetchProviders()]).finally(() => setLoading(false));
  }, []);

  const backendOk = healthLive?.status === "ok";
  const dataReady = healthReady?.status === "ok";

  return (
    <div className="mx-auto max-w-[1400px] space-y-8 animate-fade-in pb-12">
      <div className="flex items-start justify-between gap-4">
        <PageHeader
          eyebrow="System Configuration"
          title="Platform Settings & System Health"
          description="Backend health status, AI provider availability, video processing queue, and system configuration."
        />
        <Button variant="outline" size="sm" onClick={refresh} disabled={refreshing} className="gap-2 mt-2">
          <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {/* ── Backend Health Cards ─────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-5 border bg-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">API Server</p>
              <p className="text-2xl font-bold mt-1 flex items-center gap-2">
                {loading ? "..." : backendOk ? "Online" : "Offline"}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                {healthLive?.service || "FastAPI backend"}
              </p>
            </div>
            <div className="h-10 w-10 rounded-xl bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 flex items-center justify-center">
              <Server className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs">
            <StatusDot ok={backendOk} />
            <span className="text-muted-foreground">
              {loading ? "Checking..." : healthError || "Healthy and responding"}
            </span>
          </div>
        </Card>

        <Card className="p-5 border bg-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Data Readiness</p>
              <p className="text-2xl font-bold mt-1 flex items-center gap-2">
                {loading ? "..." : dataReady ? "Ready" : "Degraded"}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                {healthReady?.details?.processing_jobs ?? 0} active jobs
              </p>
            </div>
            <div className="h-10 w-10 rounded-xl bg-indigo-50 dark:bg-indigo-950/50 text-indigo-600 flex items-center justify-center">
              <Database className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs">
            <StatusDot ok={dataReady} />
            <span className="text-muted-foreground">
              {loading ? "Checking..." : dataReady ? "All directories accessible" : "Missing data directories"}
            </span>
          </div>
        </Card>

        <Card className="p-5 border bg-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Total Videos</p>
              <p className="text-2xl font-bold mt-1">{videos.length}</p>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                {videos.filter(v => v.status === "Completed" || v.status === "Indexed").length} ready for queries
              </p>
            </div>
            <div className="h-10 w-10 rounded-xl bg-violet-50 dark:bg-violet-950/50 text-violet-600 flex items-center justify-center">
              <Activity className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            <Zap className="h-3 w-3" />
            {videos.filter(v => v.status === "Processing").length} currently processing
          </div>
        </Card>

        <Card className="p-5 border bg-card">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Uptime</p>
              <p className="text-2xl font-bold mt-1">
                {healthLive?.timestamp ? new Date(healthLive.timestamp).toLocaleTimeString() : "--:--"}
              </p>
              <p className="text-[11px] text-muted-foreground mt-0.5">Last health check</p>
            </div>
            <div className="h-10 w-10 rounded-xl bg-cyan-50 dark:bg-cyan-950/50 text-cyan-600 flex items-center justify-center">
              <HardDrive className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
            <Globe className="h-3 w-3" />
            http://localhost:8001
          </div>
        </Card>
      </div>

      {/* ── AI Provider Status ─────────────────────────────────── */}
      <Card className="p-6 border bg-card space-y-5">
        <div className="flex items-center justify-between border-b pb-3">
          <h3 className="font-bold text-sm text-foreground flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-indigo-500" />
            AI Provider Status
          </h3>
          <Badge variant="outline">Multi-Key Rotation</Badge>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Groq Section */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-lg bg-orange-50 dark:bg-orange-950/50 text-orange-600 flex items-center justify-center">
                  <Zap className="h-4 w-4" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-foreground">Groq API</h4>
                  <p className="text-[11px] text-muted-foreground">qwen/qwen3.6-27b</p>
                </div>
              </div>
              <Badge variant={providerStatus?.groq.available_keys ? "success" : "destructive"}>
                {providerStatus?.groq.available_keys ?? "?"}/{providerStatus?.groq.total_keys ?? 3} keys
              </Badge>
            </div>

            {providerStatus?.groq.keys ? (
              <div className="space-y-2">
                {providerStatus.groq.keys.map((key) => (
                  <div key={key.key_index} className="flex items-center justify-between p-3 rounded-xl border bg-secondary/30 text-xs">
                    <div className="flex items-center gap-2">
                      <StatusDot ok={key.available} />
                      <span className="font-mono text-foreground">Key {key.key_index} (...{key.key_suffix})</span>
                    </div>
                    <div className="flex items-center gap-3 text-muted-foreground">
                      <span>{key.requests_today} requests</span>
                      {key.quota_exhausted && (
                        <span className="text-red-500 font-semibold">Rate limited</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="p-3 rounded-xl border bg-secondary/30 text-xs text-muted-foreground text-center">
                {loading ? "Loading provider status..." : "Provider status unavailable"}
              </div>
            )}

            <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/50 text-xs text-emerald-700 dark:text-emerald-300">
              <p className="font-semibold">Rate limit: 14,400 requests/day per key</p>
              <p className="mt-0.5 text-emerald-600/80 dark:text-emerald-400/80">
                With 3 keys = 43,200 total daily capacity
              </p>
            </div>
          </div>

          {/* Gemini Section */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-lg bg-blue-50 dark:bg-blue-950/50 text-blue-600 flex items-center justify-center">
                  <Sparkles className="h-4 w-4" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-foreground">Google Gemini</h4>
                  <p className="text-[11px] text-muted-foreground">gemini-2.5-flash (VLM + Text fallback)</p>
                </div>
              </div>
              <Badge variant={providerStatus?.gemini.quota_exhausted ? "destructive" : "success"}>
                {providerStatus?.gemini.quota_exhausted ? "Exhausted" : "Available"}
              </Badge>
            </div>

            <div className="p-3 rounded-xl border bg-secondary/30 text-xs space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Requests today</span>
                <span className="font-mono font-bold text-foreground">{providerStatus?.gemini.requests_today ?? 0}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Daily limit</span>
                <span className="font-mono font-bold text-foreground">1,500</span>
              </div>
              {providerStatus?.gemini.last_error && (
                <div className="pt-2 border-t border-border/50">
                  <p className="text-red-500 text-[11px] truncate">{providerStatus.gemini.last_error}</p>
                </div>
              )}
            </div>

            <div className="p-3 rounded-xl bg-blue-50 dark:bg-blue-950/20 border border-blue-200 dark:border-blue-900/50 text-xs text-blue-700 dark:text-blue-300">
              <p className="font-semibold">Fallback provider for VLM enrichment</p>
              <p className="mt-0.5 text-blue-600/80 dark:text-blue-400/80">
                Used when Groq keys are rate-limited
              </p>
            </div>
          </div>
        </div>
      </Card>

      {/* ── Video Processing Queue ─────────────────────────────── */}
      <Card className="p-6 border bg-card space-y-4">
        <div className="flex items-center justify-between border-b pb-3">
          <h3 className="font-bold text-sm text-foreground flex items-center gap-2">
            <Activity className="h-4 w-4 text-violet-500" />
            Video Processing Queue
          </h3>
          <Badge variant="outline">{videos.length} total</Badge>
        </div>

        {videos.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            No videos uploaded yet. Upload a video to start processing.
          </div>
        ) : (
          <div className="space-y-3">
            {videos.map((video) => (
              <div key={video.id} className="flex items-center justify-between p-4 rounded-xl border bg-secondary/20 hover:bg-secondary/40 transition-colors">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="h-10 w-16 rounded-lg bg-gradient-to-br from-slate-900 to-indigo-900 flex items-center justify-center">
                    <Activity className="h-4 w-4 text-white/70" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-foreground truncate">{video.title}</p>
                    <p className="text-[11px] text-muted-foreground font-mono">{video.filename}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4 text-xs">
                  <span className="text-muted-foreground font-mono">{video.duration}</span>
                  <Badge variant={
                    video.status === "Completed" || video.status === "Indexed"
                      ? "success"
                      : video.status === "Processing"
                        ? "warning"
                        : video.status === "Failed"
                          ? "destructive"
                          : "default"
                  }>
                    {video.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* ── System Configuration ──────────────────────────────── */}
      <Card className="p-6 border bg-card space-y-5">
        <div className="flex items-center justify-between border-b pb-3">
          <h3 className="font-bold text-sm text-foreground flex items-center gap-2">
            <Cpu className="h-4 w-4 text-emerald-500" />
            Pipeline Configuration
          </h3>
          <Badge variant="outline">Read-only</Badge>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 text-xs">
          <div className="p-3 rounded-xl border bg-secondary/30 space-y-1">
            <p className="text-muted-foreground font-semibold uppercase text-[10px]">Backend URL</p>
            <p className="font-mono text-foreground">http://localhost:8001</p>
          </div>
          <div className="p-3 rounded-xl border bg-secondary/30 space-y-1">
            <p className="text-muted-foreground font-semibold uppercase text-[10px]">Embedding Model</p>
            <p className="font-mono text-foreground">BAAI/bge-base-en-v1.5</p>
          </div>
          <div className="p-3 rounded-xl border bg-secondary/30 space-y-1">
            <p className="text-muted-foreground font-semibold uppercase text-[10px]">Whisper ASR</p>
            <p className="font-mono text-foreground">Auto (small)</p>
          </div>
          <div className="p-3 rounded-xl border bg-secondary/30 space-y-1">
            <p className="text-muted-foreground font-semibold uppercase text-[10px]">OCR Engine</p>
            <p className="font-mono text-foreground">Tesseract + Groq LLM Cleanup</p>
          </div>
          <div className="p-3 rounded-xl border bg-secondary/30 space-y-1">
            <p className="text-muted-foreground font-semibold uppercase text-[10px]">VLM Captioning</p>
            <p className="font-mono text-foreground">Groq (qwen3.6-27b) + Gemini 2.5 Flash</p>
          </div>
          <div className="p-3 rounded-xl border bg-secondary/30 space-y-1">
            <p className="text-muted-foreground font-semibold uppercase text-[10px]">Vector Store</p>
            <p className="font-mono text-foreground">ChromaDB (4 collections)</p>
          </div>
          <div className="p-3 rounded-xl border bg-secondary/30 space-y-1">
            <p className="text-muted-foreground font-semibold uppercase text-[10px]">Pipeline Version</p>
            <p className="font-mono text-foreground">base-v1</p>
          </div>
          <div className="p-3 rounded-xl border bg-secondary/30 space-y-1">
            <p className="text-muted-foreground font-semibold uppercase text-[10px]">Frame Extraction</p>
            <p className="font-mono text-foreground">atom_coverage (2s interval)</p>
          </div>
          <div className="p-3 rounded-xl border bg-secondary/30 space-y-1">
            <p className="text-muted-foreground font-semibold uppercase text-[10px]">Answer Mode</p>
            <p className="font-mono text-foreground">strict_video (grounded citations)</p>
          </div>
        </div>
      </Card>
    </div>
  );
}
