import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft,
  Cpu,
  HardDrive,
  FileVideo,
  Play,
  RotateCcw,
  CheckCircle2,
  Image,
  Video,
  Mic,
  Volume2,
  Database,
  Layers,
  Sparkles,
  ChevronRight,
  Terminal,
  Clock,
  AlertCircle,
  Loader2
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/global/headers";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  PipelineStage,
  ProcessingSummaryCard,
  ProcessingTimeline,
  ActivityLog,
  type StageData,
  type LogMessage,
  type Milestone
} from "@/features/processing/processing-components";
import { useProcessing, useRetryVideo, useVideo } from "@/hooks/api/use-videos";
import type { ApiProcessingStatus, LibraryVideo } from "@/types/api";

// 11 Pipeline Stage Definitions template
const STAGES_TEMPLATE: { name: string; icon: any; durationEstimate: number }[] = [
  { name: "Upload Complete", icon: HardDrive, durationEstimate: 1.2 },
  { name: "Scene Detection", icon: Video, durationEstimate: 2.1 },
  { name: "Frame Extraction", icon: Image, durationEstimate: 2.8 },
  { name: "OCR Frame Scan", icon: Layers, durationEstimate: 3.4 },
  { name: "Audio Extraction", icon: Volume2, durationEstimate: 1.5 },
  { name: "Speech Recognition", icon: Mic, durationEstimate: 4.2 },
  { name: "Speaker Detection", icon: Cpu, durationEstimate: 1.8 },
  { name: "Semantic Chunking", icon: Layers, durationEstimate: 2.0 },
  { name: "Embedding Generation", icon: Sparkles, durationEstimate: 2.5 },
  { name: "Vector Indexing", icon: Database, durationEstimate: 1.9 },
  { name: "AI Ready Status", icon: CheckCircle2, durationEstimate: 0.8 }
];

export function VideoProcessingPage() {
  const { videoId } = useParams<{ videoId: string }>();
  const navigate = useNavigate();
  const { data: backendVideo } = useVideo(videoId);
  const { data: processingStatus } = useProcessing(videoId);
  const retryMutation = useRetryVideo();

  // Load target video details from backend manifest.
  const [video, setVideo] = useState<LibraryVideo | null>(null);

  useEffect(() => {
    if (backendVideo) {
      setVideo(backendVideo);
    }
  }, [backendVideo]);

  // Ingestion Simulation States
  const [stages, setStages] = useState<StageData[]>(() =>
    STAGES_TEMPLATE.map((t, idx) => ({
      id: `stage-${idx}`,
      name: t.name,
      icon: t.icon,
      status: idx === 0 ? "processing" : "queued",
      progress: 0,
      duration: "0.0s"
    }))
  );

  const [activeStageIdx, setActiveStageIdx] = useState(0);
  const [logs, setLogs] = useState<LogMessage[]>([]);
  const [isFullyCompleted, setIsFullyCompleted] = useState(false);

  // Ingestion statistics counters
  const [stats, setStats] = useState({
    frames: 0,
    scenes: 0,
    ocrChars: 0,
    transcriptSpans: 0,
    speakers: 0,
    embeddings: 0
  });

  // Time formatter
  const getLogTime = () => {
    const now = new Date();
    return now.toTimeString().split(" ")[0] + "." + String(now.getMilliseconds()).padStart(3, "0");
  };

  // Reflect backend processing status in the stage visualization.
  useEffect(() => {
    if (!processingStatus) return;
    const data = processingStatus as ApiProcessingStatus & {
      boundary_candidate_count?: number;
      atom_count?: number;
      extracted_frame_count?: number;
      semantic_chunk_count?: number;
    };
    const progress = typeof data.progress === "number" ? data.progress : 0;
    const isDone = data.status === "completed" || progress >= 100;
    const currentStageIdx = Math.min(STAGES_TEMPLATE.length - 1, Math.floor((progress / 100) * STAGES_TEMPLATE.length));

    setActiveStageIdx(currentStageIdx);
    setIsFullyCompleted(isDone);
    setStages((prev) =>
      prev.map((stage, idx) => {
        if (idx < currentStageIdx || isDone) return { ...stage, status: "completed", progress: 100, duration: "backend" };
        if (idx === currentStageIdx) return { ...stage, status: "processing", progress: Math.max(1, Math.min(99, progress)), duration: "backend" };
        return { ...stage, status: "queued", progress: 0, duration: "0.0s" };
      })
    );
    setStats({
      frames: data.extracted_frame_count || data.frame_count || 0,
      scenes: data.boundary_candidate_count || 0,
      ocrChars: 0,
      transcriptSpans: data.atom_count || 0,
      speakers: 0,
      embeddings: data.semantic_chunk_count || 0
    });
    setLogs([{
      time: getLogTime(),
      module: "FastAPI",
      level: data.status === "failed" ? "ERROR" : isDone ? "SUCCESS" : "INFO",
      text: data.error || data.phase || data.status || "Processing status received"
    }]);
  }, [processingStatus]);

  const addLog = (module: string, level: LogMessage["level"], text: string) => {
    setLogs((prev) => [...prev, { time: getLogTime(), module, level, text }]);
  };

  // Retry processing through the backend lifecycle route.
  const handleResetSimulation = async () => {
    if (!videoId) return;
    try {
      await retryMutation.mutateAsync(videoId);
      toast.info("AI ingestion pipeline retry queued.");
    } catch {
      toast.error("Could not queue processing retry for this video.");
    }
  };

  // Compute Milestones for ProcessingTimeline component
  const getMilestones = (): Milestone[] => {
    return [
      {
        name: "Ingestion",
        label: activeStageIdx > 0 ? "Complete" : "Uploading...",
        status: activeStageIdx > 0 ? "completed" : "processing",
        stages: ["Upload Complete"]
      },
      {
        name: "Vision Parsing",
        label: activeStageIdx > 3 ? "Complete" : activeStageIdx >= 1 ? "Extracting..." : "Pending",
        status: activeStageIdx > 3 ? "completed" : activeStageIdx >= 1 ? "processing" : "queued",
        stages: ["Scene Detection", "Frame Extraction", "OCR Frame Scan"]
      },
      {
        name: "Audio Parsing",
        label: activeStageIdx > 6 ? "Complete" : activeStageIdx >= 4 ? "Recognizing..." : "Pending",
        status: activeStageIdx > 6 ? "completed" : activeStageIdx >= 4 ? "processing" : "queued",
        stages: ["Audio Extraction", "Speech Recognition", "Speaker Detection"]
      },
      {
        name: "Chroma Indexing",
        label: activeStageIdx > 9 ? "Complete" : activeStageIdx >= 7 ? "Writing vectors..." : "Pending",
        status: activeStageIdx > 9 ? "completed" : activeStageIdx >= 7 ? "processing" : "queued",
        stages: ["Semantic Chunking", "Embedding Generation", "Vector Indexing"]
      },
      {
        name: "Ready Status",
        label: isFullyCompleted ? "AI Ready" : "Preparing...",
        status: isFullyCompleted ? "completed" : activeStageIdx === 10 ? "processing" : "queued",
        stages: ["AI Ready Status"]
      }
    ];
  };

  return (
    <div className="mx-auto max-w-[1600px] space-y-7 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col gap-2">
        <Button variant="ghost" size="sm" asChild className="self-start text-muted-foreground hover:text-foreground pl-0">
          <Link to="/videos">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back to library
          </Link>
        </Button>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <PageHeader
            eyebrow="RAG ingestion pipeline"
            title="Analysis dashboard"
            description="Trace structural extractions, transcribing nodes, semantic segmentation progress, and ChromaDB vector mapping."
          />
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <Button variant="outline" size="sm" onClick={handleResetSimulation} className="h-9 gap-1.5 hover:border-border">
              <RotateCcw className="h-4 w-4" /> Reset Simulation
            </Button>
            <Button
              asChild={isFullyCompleted}
              disabled={!isFullyCompleted}
              variant="primary"
              size="sm"
              className="h-9 gap-1.5 shadow-sm"
            >
              {isFullyCompleted ? (
                <Link to={`/videos/${videoId}`}>
                  Go to workspace
                  <ChevronRight className="h-4 w-4" />
                </Link>
              ) : (
                <span>
                  Ingesting Pipeline...
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                </span>
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* Target Asset Detail Summary card */}
      <Card className="p-4 border bg-card/65 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-3.5 min-w-0">
          <div className={`grid h-12 w-20 shrink-0 place-items-center rounded-lg border bg-gradient-to-br text-white relative overflow-hidden ${video?.gradient || "from-slate-900 to-indigo-900"}`}>
            <FileVideo className="h-5 w-5 relative z-10" />
            <div className="absolute inset-0 bg-slate-950/20" />
          </div>
          <div className="min-w-0 text-left">
            <h3 className="text-sm font-bold text-card-foreground truncate leading-snug">{video?.title}</h3>
            <p className="text-xs text-muted-foreground font-mono truncate mt-0.5">{video?.filename}</p>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-xs font-semibold text-muted-foreground/80 md:border-l md:pl-6">
          <div className="flex flex-col">
            <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">File Size</span>
            <span className="text-foreground mt-0.5 font-mono">{video?.size}</span>
          </div>
          <div className="h-6 w-px bg-border/60 hidden sm:block" />
          <div className="flex flex-col">
            <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Duration</span>
            <span className="text-foreground mt-0.5 font-mono">{video?.duration}</span>
          </div>
          <div className="h-6 w-px bg-border/60 hidden sm:block" />
          <div className="flex flex-col">
            <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">Software</span>
            <span className="text-foreground mt-0.5 font-mono">{video?.pipelineVersion}</span>
          </div>
        </div>
      </Card>

      {/* Milestone Progress Bar Row */}
      <Card className="p-5 border shadow-soft bg-card">
        <h4 className="text-xs font-bold uppercase tracking-wider text-foreground mb-4 text-left">Pipeline Milestones</h4>
        <ProcessingTimeline milestones={getMilestones()} />
      </Card>

      {/* Main Grid: Pipeline stages list (left) & Summary metrics / logs terminal (right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: 11 Stages list */}
        <div className="lg:col-span-5 space-y-3">
          <div className="flex items-center justify-between border-b pb-2 mb-1">
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">Pipeline Stages</h4>
            <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-bold bg-muted/60 border border-border/80">
              {activeStageIdx + 1} / 11 running
            </Badge>
          </div>

          <div className="grid grid-cols-1 gap-2.5 max-h-[500px] overflow-y-auto pr-1">
            {stages.map((st) => (
              <PipelineStage key={st.id} stage={st} />
            ))}
          </div>
        </div>

        {/* Right Column: Statistics Summary cards grid & Terminal logs console */}
        <div className="lg:col-span-7 space-y-6">
          {/* Grid of 6 statistics cards */}
          <div>
            <h4 className="text-xs font-bold uppercase tracking-wider text-foreground border-b pb-2 mb-4 text-left">
              Ingested Structural Metrics
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <ProcessingSummaryCard
                title="Scenes Segmented"
                value={stats.scenes}
                icon={Video}
                colorClass="text-indigo-500 border-indigo-200/50 bg-indigo-50/50 dark:bg-indigo-950/20 dark:border-indigo-900/50"
              />
              <ProcessingSummaryCard
                title="Frames Extracted"
                value={stats.frames}
                icon={Image}
                colorClass="text-cyan-500 border-cyan-200/50 bg-cyan-50/50 dark:bg-cyan-950/20 dark:border-cyan-900/50"
              />
              <ProcessingSummaryCard
                title="OCR Overlays Scan"
                value={stats.ocrChars}
                icon={Layers}
                colorClass="text-amber-500 border-amber-200/50 bg-amber-50/50 dark:bg-amber-950/20 dark:border-amber-900/50"
              />
              <ProcessingSummaryCard
                title="Dialogue Spans"
                value={stats.transcriptSpans}
                icon={Mic}
                colorClass="text-emerald-500 border-emerald-200/50 bg-emerald-50/50 dark:bg-emerald-950/20 dark:border-emerald-900/50"
              />
              <ProcessingSummaryCard
                title="Speakers Identified"
                value={stats.speakers}
                icon={Cpu}
                colorClass="text-violet-500 border-violet-200/50 bg-violet-50/50 dark:bg-violet-950/20 dark:border-violet-900/50"
              />
              <ProcessingSummaryCard
                title="Embeddings Indexed"
                value={stats.embeddings}
                icon={Database}
                colorClass="text-pink-500 border-pink-200/50 bg-pink-50/50 dark:bg-pink-950/20 dark:border-pink-900/50"
              />
            </div>
          </div>

          {/* Logging Shell Console Terminal */}
          <ActivityLog logs={logs} />
        </div>
      </div>
    </div>
  );
}



