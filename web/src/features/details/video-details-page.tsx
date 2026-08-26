import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowRight,
  Captions,
  CheckCircle2,
  Clock,
  Database,
  FileText,
  Film,
  Image,
  Layers,
  Mic,
  Play,
  RefreshCw,
  ScanText,
  Search,
  Sparkles,
  Trash2,
  Volume2,
  XCircle,
  ChevronDown,
  ChevronUp
} from "lucide-react";
import { buildWorkspaceViewModel } from "@/api/artifact-adapters";
import { PageHeader, SectionHeader } from "@/components/global/headers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  useDeleteVideo,
  useRetryVideo,
  useVideo
} from "@/hooks/api/use-videos";
import { useWorkspace } from "@/hooks/api/use-workspace";

function resolutionLabel(resolution: unknown, width?: number, height?: number) {
  if (resolution && typeof resolution === "object" && "width" in resolution && "height" in resolution) {
    const value = resolution as { width?: number; height?: number };
    return `${value.width || 0} x ${value.height || 0}`;
  }
  if (typeof resolution === "string") return resolution;
  return width && height ? `${width} x ${height}` : "Unknown";
}

function formatTimestamp(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const secs = safe % 60;
  return `${minutes}:${String(secs).padStart(2, "0")}`;
}

// ── Processing Stage Definition ──────────────────────────────────
const PIPELINE_STAGES = [
  { key: "upload", label: "Upload Complete", icon: Image, phase: "upload" },
  { key: "scene", label: "Scene Detection", icon: Film, phase: "scene_detection" },
  { key: "audio", label: "Audio Extraction", icon: Volume2, phase: "audio_extraction" },
  { key: "transcript", label: "Transcription", icon: Mic, phase: "transcription" },
  { key: "chunking", label: "Canonical Chunking", icon: Layers, phase: "chunking_foundation" },
  { key: "frames", label: "Frame Extraction", icon: Image, phase: "frame_extraction" },
  { key: "evidence", label: "Evidence Foundation", icon: Database, phase: "evidence_foundation" },
  { key: "indexing", label: "Hierarchy Indexing", icon: Sparkles, phase: "hierarchy_indexing" },
  { key: "modality", label: "OCR + Speakers", icon: ScanText, phase: "modality_foundation" },
  { key: "cleanup", label: "OCR Cleanup", icon: Search, phase: "ocr_cleanup" },
  { key: "summarize", label: "Topic Summarization", icon: FileText, phase: "topic_summarization" },
  { key: "enrichment", label: "Visual Enrichment", icon: Sparkles, phase: "visual_analysis" },
  { key: "index2", label: "Vector Indexing", icon: Database, phase: "indexing" },
  { key: "ready", label: "AI Ready", icon: CheckCircle2, phase: "completed" },
];

function ProcessingStagesTimeline({ status, progress }: { status?: string; progress?: number }) {
  const isComplete = status === "completed";
  const isFailed = status === "failed";
  const currentPhase = (status || "").toLowerCase();

  return (
    <Card className="p-6 border bg-card space-y-4">
      <div className="flex items-center justify-between border-b pb-3">
        <h3 className="font-bold text-sm text-foreground flex items-center gap-2">
          <Clock className="h-4 w-4 text-indigo-500" />
          Processing Pipeline Stages
        </h3>
        <div className="flex items-center gap-2">
          {isComplete && <Badge variant="success">Complete</Badge>}
          {isFailed && <Badge variant="destructive">Failed</Badge>}
          {!isComplete && !isFailed && (
            <Badge variant="warning">{Math.round(progress || 0)}%</Badge>
          )}
        </div>
      </div>

      <div className="relative">
        {/* Progress bar */}
        <div className="absolute top-5 left-0 right-0 h-0.5 bg-secondary">
          <div
            className="h-full bg-primary transition-all duration-500"
            style={{ width: `${isComplete ? 100 : progress || 0}%` }}
          />
        </div>

        {/* Stage nodes */}
        <div className="relative flex justify-between">
          {PIPELINE_STAGES.map((stage, index) => {
            const stageProgress = (index / (PIPELINE_STAGES.length - 1)) * 100;
            const isStageComplete = isComplete || (progress || 0) > stageProgress;
            const isCurrent = !isComplete && !isFailed && Math.abs((progress || 0) - stageProgress) < (100 / PIPELINE_STAGES.length);
            const Icon = stage.icon;

            return (
              <div key={stage.key} className="flex flex-col items-center gap-1.5" style={{ width: `${100 / PIPELINE_STAGES.length}%` }}>
                <div className={cn(
                  "h-10 w-10 rounded-full flex items-center justify-center border-2 transition-all z-10 bg-background",
                  isStageComplete ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/50" : "",
                  isCurrent ? "border-primary bg-primary/10 animate-pulse" : "",
                  !isStageComplete && !isCurrent ? "border-border" : ""
                )}>
                  {isStageComplete ? (
                    <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                  ) : isCurrent ? (
                    <Icon className="h-4 w-4 text-primary animate-spin" />
                  ) : (
                    <Icon className="h-4 w-4 text-muted-foreground" />
                  )}
                </div>
                <span className="text-[9px] font-semibold text-muted-foreground text-center leading-tight hidden lg:block">
                  {stage.label}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

// ── Timeline Frame Extraction Database ───────────────────────────
interface TimelineFrame {
  atomId: string;
  startTime: number;
  endTime: number;
  transcript: string;
  speaker: string;
  visualSummary: string;
  ocrText: string;
  concepts: string[];
  diagramType: string;
}

function TimelineFrameDatabase({ viewModel, videoId, onJumpToTimeline }: { viewModel: ReturnType<typeof buildWorkspaceViewModel>; videoId: string; onJumpToTimeline: (sec: number) => void }) {
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [filterText, setFilterText] = useState("");

  // Build timeline frames from transcript blocks + OCR + visual artifacts
  const frames: TimelineFrame[] = useMemo(() => {
    const blocks = viewModel.transcriptBlocks || [];
    const ocr = viewModel.ocrEvidence || [];

    return blocks.map((block) => {
      const nearbyOcr = ocr.find(o => o.startSec < block.endSec && o.endSec > block.startSec);
      return {
        atomId: block.id,
        startTime: block.startSec,
        endTime: block.endSec,
        transcript: block.text,
        speaker: block.speakerName,
        visualSummary: block.topicCluster || "",
        ocrText: nearbyOcr?.text || "",
        concepts: block.sceneTitle ? [block.sceneTitle] : [],
        diagramType: block.hasVisualObject ? "visual" : "speech"
      };
    });
  }, [viewModel]);

  const filteredFrames = useMemo(() => {
    if (!filterText) return frames;
    const lower = filterText.toLowerCase();
    return frames.filter(f =>
      f.transcript.toLowerCase().includes(lower) ||
      f.speaker.toLowerCase().includes(lower) ||
      f.ocrText.toLowerCase().includes(lower) ||
      f.visualSummary.toLowerCase().includes(lower)
    );
  }, [frames, filterText]);

  return (
    <Card className="p-6 border bg-card space-y-4">
      <div className="flex items-center justify-between border-b pb-3">
        <h3 className="font-bold text-sm text-foreground flex items-center gap-2">
          <Database className="h-4 w-4 text-cyan-500" />
          Per-Timeline Extraction Database
        </h3>
        <Badge variant="outline">{filteredFrames.length} records</Badge>
      </div>

      {/* Search filter */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <input
          value={filterText}
          onChange={(e) => setFilterText(e.target.value)}
          placeholder="Search transcript, OCR, speaker..."
          className="w-full h-9 rounded-md border bg-background pl-9 pr-3 text-xs text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        />
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b text-left">
              <th className="pb-2 font-semibold text-muted-foreground">Time</th>
              <th className="pb-2 font-semibold text-muted-foreground">Speaker</th>
              <th className="pb-2 font-semibold text-muted-foreground">Transcript</th>
              <th className="pb-2 font-semibold text-muted-foreground">OCR Text</th>
              <th className="pb-2 font-semibold text-muted-foreground">Type</th>
              <th className="pb-2 font-semibold text-muted-foreground"></th>
            </tr>
          </thead>
          <tbody>
            {filteredFrames.map((frame) => (
              <>
                <tr
                  key={frame.atomId}
                  className="border-b border-border/50 hover:bg-secondary/30 cursor-pointer"
                  onClick={() => setExpandedRow(expandedRow === frame.atomId ? null : frame.atomId)}
                >
                  <td className="py-2.5 font-mono text-muted-foreground whitespace-nowrap">
                    {formatTimestamp(frame.startTime)} - {formatTimestamp(frame.endTime)}
                  </td>
                  <td className="py-2.5">
                    <Badge variant="secondary" className="text-[10px] font-mono">
                      {frame.speaker}
                    </Badge>
                  </td>
                  <td className="py-2.5 text-foreground max-w-xs truncate">{frame.transcript || "---"}</td>
                  <td className="py-2.5 text-muted-foreground max-w-[200px] truncate font-mono">{frame.ocrText || "---"}</td>
                  <td className="py-2.5">
                    <Badge variant={frame.diagramType === "visual" ? "default" : "outline"} className="text-[10px]">
                      {frame.diagramType}
                    </Badge>
                  </td>
                  <td className="py-2.5">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0"
                      onClick={(e) => {
                        e.stopPropagation();
                        onJumpToTimeline(frame.startTime);
                      }}
                    >
                      <ArrowRight className="h-3 w-3" />
                    </Button>
                  </td>
                </tr>
                {expandedRow === frame.atomId && (
                  <tr key={`${frame.atomId}-expanded`}>
                    <td colSpan={6} className="py-3 px-4 bg-secondary/20">
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
                        <div className="space-y-1">
                          <p className="text-[10px] font-bold uppercase text-muted-foreground">Full Transcript</p>
                          <p className="text-foreground leading-relaxed">{frame.transcript || "No transcript available"}</p>
                        </div>
                        <div className="space-y-1">
                          <p className="text-[10px] font-bold uppercase text-muted-foreground">Visual Summary</p>
                          <p className="text-foreground leading-relaxed">{frame.visualSummary || "No visual summary available"}</p>
                        </div>
                        <div className="space-y-1">
                          <p className="text-[10px] font-bold uppercase text-muted-foreground">OCR Extracted Text</p>
                          <p className="text-foreground leading-relaxed font-mono">{frame.ocrText || "No OCR text in this segment"}</p>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>

      {filteredFrames.length === 0 && (
        <div className="p-8 text-center text-sm text-muted-foreground">
          {filterText ? "No records match your search." : "No extraction data available."}
        </div>
      )}
    </Card>
  );
}

// ── Main Video Details Page ──────────────────────────────────────
export function VideoDetailsPage() {
  const { videoId } = useParams<{ videoId: string }>();
  const navigate = useNavigate();
  const { data: video, isLoading: videoLoading } = useVideo(videoId);
  const { data: artifacts, isLoading: artifactsLoading } = useWorkspace(videoId);
  const deleteMutation = useDeleteVideo();
  const retryMutation = useRetryVideo();
  const viewModel = useMemo(
    () => artifacts ? buildWorkspaceViewModel(artifacts) : null,
    [artifacts]
  );

  if (!videoId || videoLoading || artifactsLoading || !video || !artifacts || !viewModel) {
    return (
      <div className="grid min-h-[60vh] place-items-center text-sm text-muted-foreground">
        {!videoId ? "No video was selected." : "Loading manifest and evidence artifacts..."}
      </div>
    );
  }

  const details = viewModel.details;
  const manifest = artifacts.manifest;
  const processing = manifest.processing;
  const status = processing?.status || "unknown";
  const progress = processing?.progress || 0;

  const stats = [
    ["Events", details.stats.events, "Explanation intervals", Film, "text-rose-600 bg-rose-500/10 border-rose-500/20"],
    ["Chunks", details.stats.semanticChunks, "Topic segments", Layers, "text-blue-600 bg-blue-500/10 border-blue-500/20"],
    ["Transcript", details.stats.transcriptSpans, "Timestamped spans", Captions, "text-emerald-600 bg-emerald-500/10 border-emerald-500/20"],
    ["Frames", details.stats.frames, "Evidence images", Image, "text-indigo-600 bg-indigo-500/10 border-indigo-500/20"],
    ["OCR", details.stats.ocrRecords, "Visible-text records", ScanText, "text-cyan-600 bg-cyan-500/10 border-cyan-500/20"],
    ["Speakers", details.stats.speakers, "Diarized voices", Mic, "text-violet-600 bg-violet-500/10 border-violet-500/20"],
    ["Audio", details.stats.audioEvents, "Acoustic intervals", Volume2, "text-amber-600 bg-amber-500/10 border-amber-500/20"]
  ] as const;

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${video.title}" and its managed artifacts?`)) return;
    try {
      await deleteMutation.mutateAsync(videoId);
      toast.success("Video deleted.");
      navigate("/videos");
    } catch {
      toast.error("The backend could not delete this video.");
    }
  };

  const handleRetry = async () => {
    try {
      await retryMutation.mutateAsync(videoId);
      toast.success("Processing retry queued.");
      navigate(`/videos/${videoId}/processing`);
    } catch {
      toast.error("The source video is unavailable for retry.");
    }
  };

  return (
    <div className="mx-auto max-w-[1500px] space-y-7 animate-fade-in">
      <PageHeader
        eyebrow="Video evidence profile"
        title={video.title}
        description={`Duration: ${video.duration} | Resolution: ${resolutionLabel(manifest.resolution, manifest.width, manifest.height)} | Codec: ${manifest.video_codec || "unknown"} | FPS: ${manifest.fps || "?"}`}
        actions={
          <div className="flex gap-2">
            <Button variant="outline" onClick={handleRetry} disabled={retryMutation.isPending}>
              <RefreshCw className="h-4 w-4" />Reprocess
            </Button>
            <Button onClick={() => navigate(`/videos/${videoId}/timeline`)}>
              <Play className="h-4 w-4" />Open Workspace
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleteMutation.isPending}>
              <Trash2 className="h-4 w-4" />Delete
            </Button>
          </div>
        }
      />

      {/* Processing Stages Timeline */}
      <ProcessingStagesTimeline status={status} progress={progress} />

      {/* Artifact Statistics Grid */}
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7" aria-label="Artifact statistics">
        {stats.map(([title, value, label, Icon, colorClass]) => (
          <Card key={title} className={cn("p-4 border", colorClass)}>
            <div className="flex items-center gap-2 mb-2">
              <Icon className="h-4 w-4" />
              <span className="text-xs font-bold uppercase tracking-wider">{title}</span>
            </div>
            <p className="text-2xl font-bold">{value}</p>
            <p className="text-[11px] text-muted-foreground mt-0.5">{label}</p>
          </Card>
        ))}
      </section>

      {/* Per-Timeline Extraction Database */}
      <TimelineFrameDatabase viewModel={viewModel} videoId={videoId} onJumpToTimeline={(sec) => navigate(`/videos/${videoId}/timeline?t=${sec}`)} />

      {/* Explanation Timeline + Summary */}
      <div className="grid gap-6 xl:grid-cols-[1.35fr_.65fr]">
        <section>
          <div className="mb-4">
            <SectionHeader title="Explanation timeline" description="Validated events grouped from canonical semantic chunks." />
          </div>
          <div className="space-y-3">
            {details.scenes.map((scene) => (
              <Card key={scene.id} className="p-4 border bg-card hover:bg-secondary/30 transition-colors cursor-pointer" onClick={() => navigate(`/videos/${videoId}/timeline?t=${scene.startSec}`)}>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className={cn("h-10 w-10 rounded-lg bg-gradient-to-br flex items-center justify-center text-white text-xs font-bold", scene.gradient)}>
                      {scene.index}
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-foreground">{scene.title}</h4>
                      <p className="text-[11px] text-muted-foreground font-mono">{scene.timeStart} - {scene.timeEnd}</p>
                    </div>
                  </div>
                  <ArrowRight className="h-4 w-4 text-muted-foreground" />
                </div>
                {scene.description && (
                  <p className="mt-2 text-xs text-muted-foreground line-clamp-2">{scene.description}</p>
                )}
              </Card>
            ))}
          </div>
        </section>

        <div className="space-y-5">
          <Card className="p-5">
            <SectionHeader title="Summary" description="Generated from the event hierarchy." />
            <p className="mt-4 text-sm leading-6 text-muted-foreground">{details.summary}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {details.topics.map((topic) => (
                <Badge key={topic} variant="secondary" className="text-[10px]">{topic}</Badge>
              ))}
            </div>
          </Card>

          <Card className="p-5">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <Database className="h-4 w-4 text-cyan-600" />Readable OCR Evidence
              </h2>
              <Badge variant="outline">{details.visibleTexts.length}</Badge>
            </div>
            <div className="mt-4 space-y-2 max-h-64 overflow-y-auto">
              {details.visibleTexts.map((text) => (
                <p key={text} className="rounded-md border bg-muted/40 p-2 text-xs font-mono">{text}</p>
              ))}
              {details.visibleTexts.length === 0 && (
                <p className="text-xs text-muted-foreground">No readable OCR text is available.</p>
              )}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
