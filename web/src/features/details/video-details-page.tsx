import { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft,
  Play,
  RotateCcw,
  Download,
  Trash2,
  Video,
  Image,
  Mic,
  Cpu,
  Layers,
  Database,
  Clock,
  Sparkles,
  ExternalLink
} from "lucide-react";

import { PageHeader } from "@/components/global/headers";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription
} from "@/components/ui/dialog";

import {
  VideoHeader,
  ReportCard,
  TopicChip,
  SceneCard,
  SummaryPanel,
  type SceneItem
} from "@/features/details/details-components";
import { libraryVideos as initialLibraryVideos, type LibraryVideo } from "@/features/library/mock-data";

// Detailed interface for populated report metrics
interface ExtendedDetailData {
  summary: string;
  topics: string[];
  objects: string[];
  scenes: SceneItem[];
  stats: {
    scenes: number;
    frames: number;
    ocrChars: number;
    transcriptSpans: number;
    speakers: number;
    duration: string;
  };
}

export function VideoDetailsPage() {
  const { videoId } = useParams<{ videoId: string }>();
  const navigate = useNavigate();

  // Video and Details states
  const [video, setVideo] = useState<LibraryVideo | null>(null);
  const [details, setDetails] = useState<ExtendedDetailData | null>(null);
  
  // Dialog confirmation state
  const [deleteOpen, setDeleteOpen] = useState(false);

  // Load video details
  useEffect(() => {
    const saved = localStorage.getItem("video-library-data");
    const library: LibraryVideo[] = saved ? JSON.parse(saved) : initialLibraryVideos;
    const match = library.find((v) => v.id === videoId);

    if (match) {
      setVideo(match);
      setDetails(populateVideoDetails(match));
    } else {
      // Direct user back to library if video is not found
      toast.error("Video asset not found.");
      navigate("/videos");
    }
  }, [videoId, navigate]);

  // Helper to generate mock reports dynamically
  const populateVideoDetails = (v: LibraryVideo): ExtendedDetailData => {
    // 1. Details for "MCP vs HTTP comparison"
    if (v.id === "mcp-vs-http") {
      return {
        summary: "This technical deep dive explores the Model Context Protocol (MCP) in contrast to standard HTTP REST APIs. The video reviews transport layers, bidirectional tool calls, context window optimizations, and real-time JSON payload mappings. It outlines how AI agents can leverage MCP to connect external files, prompt files, and database tools directly without custom wrappers.",
        topics: ["MCP Specification", "HTTP REST Comparison", "Bidirectional Transport", "Context Windows", "AI Agents", "Schema Syncing", "API Design Architecture"],
        objects: ["Architecture Block Diagram", "Opening Slide Title", "JSON Schema Payload code", "Vite Comparison Grid", "VS Code Editor Interface", "Speaker Camera Feed"],
        stats: { scenes: 16, frames: 1240, ocrChars: 5420, transcriptSpans: 248, speakers: 2, duration: "18.4s" },
        scenes: [
          { id: "s1", index: 1, timeStart: "00:00", timeEnd: "05:12", title: "Introduction & Context Limits", description: "Overview of current RAG limitations and the need for standard context schemas. The presenter explains why traditional HTTP REST creates integration bottlenecks for agent tools.", gradient: "from-indigo-950 via-slate-900 to-cyan-900" },
          { id: "s2", index: 2, timeStart: "05:12", timeEnd: "15:45", title: "Model Context Protocol Specifications", description: "Deep dive into the MCP stack. Reviews client-server architectures, transport adapters (SSE and stdio), and message serialization protocols.", gradient: "from-slate-900 via-violet-950 to-indigo-900" },
          { id: "s3", index: 3, timeStart: "15:45", timeEnd: "32:30", title: "Bidirectional Tool Calls & Prompt Registries", description: "Walkthrough of tool execution loops. Live demonstration of schemas, parameters passing, schema syncing, and security permission grants.", gradient: "from-cyan-950 via-slate-900 to-indigo-950" },
          { id: "s4", index: 4, timeStart: "32:30", timeEnd: "42:18", title: "RAG Evaluation Gates & Summary QA", description: "Comparison results across the N10 evaluation suite. Audience questions regarding latency, WebSocket integrations, and future WebSocket roadmaps.", gradient: "from-amber-950 via-slate-900 to-rose-950" }
        ]
      };
    }

    // 2. Details for "Product architecture review"
    if (v.id === "architecture-review") {
      return {
        summary: "A thorough product architecture review session focusing on microservices restructuring, load balancing, caching layers, and database sharding. It reviews latency bottlenecks, database write locks, Redis caching strategies, and Q3 deployment action points.",
        topics: ["Microservices", "Load Balancing", "Redis Caching", "DB Sharding", "Scalability", "Latencies", "API Gateways"],
        objects: ["System Architecture diagram", "Kubernetes cluster terminal", "Grafana metrics charts", "Whiteboard scribbles"],
        stats: { scenes: 22, frames: 1840, ocrChars: 2100, transcriptSpans: 320, speakers: 3, duration: "24.2s" },
        scenes: [
          { id: "ar-s1", index: 1, timeStart: "00:00", timeEnd: "10:15", title: "Welcome & Current Architecture", description: "Reviewing the current legacy monolithic pipeline structure and outlining the scale limits faced in microservice integrations.", gradient: "from-slate-900 via-violet-950 to-indigo-900" },
          { id: "ar-s2", index: 2, timeStart: "10:15", timeEnd: "28:40", title: "Latency Bottlenecks & Write Locks", description: "Diagnosing write lock spikes in PostgreSQL transactions. Presenter isolates issues to concurrent connections and unindexed foreign keys.", gradient: "from-cyan-950 via-slate-900 to-indigo-950" },
          { id: "ar-s3", index: 3, timeStart: "28:40", timeEnd: "48:22", title: "Caching Strategies & Message Queues", description: "Proposing a new Redis caching layer and RabbitMQ message queues to decouple visual chunk processing pipelines asynchronously.", gradient: "from-amber-950 via-slate-900 to-rose-950" },
          { id: "ar-s4", index: 4, timeStart: "48:22", timeEnd: "58:42", title: "Q3 Release Milestones & Resourcing", description: "Agreeing on engineering sprints allocation, testing procedures, budget approvals, and timeline action steps.", gradient: "from-blue-950 via-slate-900 to-violet-950" }
        ]
      };
    }

    // 3. Fallback default generator for user-uploaded videos
    const cleanTags = v.tags.map((t) => t.charAt(0).toUpperCase() + t.slice(1));
    return {
      summary: `An ingested video asset titled "${v.title}", registered under filename "${v.filename}" and analyzed using pipeline software ${v.pipelineVersion}. The pipeline has parsed its frame changes, recognized speech dialogue, clustered speaker turn markers, and generated searchable vector nodes in ChromaDB.`,
      topics: [...cleanTags, "Video Analysis", "Automatic Ingest", "RAG Processing"],
      objects: ["Presenter slide deck", "Code text listing", "Speaker webcam view", "Title slide logo"],
      stats: {
        scenes: v.status === "Processing" ? 0 : 8,
        frames: v.status === "Processing" ? 0 : 450,
        ocrChars: v.status === "Processing" ? 0 : 890,
        transcriptSpans: v.status === "Processing" ? 0 : 92,
        speakers: v.status === "Processing" ? 0 : 1,
        duration: v.status === "Processing" ? "Processing..." : "12.5s"
      },
      scenes: [
        {
          id: `${v.id}-s1`,
          index: 1,
          timeStart: "00:00",
          timeEnd: "05:00",
          title: "Introduction & Context Overview",
          description: "Visual boundaries highlight the presenter introducing the main topics, slides title overlays, and agenda points.",
          gradient: v.gradient
        },
        {
          id: `${v.id}-s2`,
          index: 2,
          timeStart: "05:00",
          timeEnd: v.duration,
          title: "Core Extraction Discussion",
          description: "Technical segments mapping text overlays, speaker dialogue turns, and general summary questions of the presentation.",
          gradient: "from-slate-900 via-zinc-900 to-slate-950"
        }
      ]
    };
  };

  // Action: Reprocess Video
  const handleReprocess = () => {
    if (!video) return;
    toast.info("Restarting AI parsing pipeline...");
    // Reset video status in local storage to simulate ingestion
    const saved = localStorage.getItem("video-library-data");
    const library: LibraryVideo[] = saved ? JSON.parse(saved) : initialLibraryVideos;
    const resetLibrary = library.map((v) =>
      v.id === video.id ? { ...v, status: "Processing" as const, progress: 0 } : v
    );
    localStorage.setItem("video-library-data", JSON.stringify(resetLibrary));

    // Redirect to processing dashboard
    navigate(`/videos/${video.id}/processing`);
  };

  // Action: Download Audit Report
  const handleDownloadReport = () => {
    if (!video || !details) return;

    const reportMarkdown = `# Pipeline Analysis Report â€” ${video.title}
Generated: ${new Date().toLocaleString()}
Filename: ${video.filename}
File Size: ${video.size}
Duration: ${video.duration}
Resolution: 1080p (1920x1080)
Pipeline Version: ${video.pipelineVersion}
Processing Duration: ${details.stats.duration}

## Ingestion Metrics Summary
- Total Scenes Segmented: ${details.stats.scenes}
- Total Frames Analyzed: ${details.stats.frames}
- OCR Overlay Detections: ${details.stats.ocrChars} character tokens
- Dialog Spans Generated: ${details.stats.transcriptSpans} boundaries
- Speakers Identified: ${details.stats.speakers} unique voice signatures
- Embeddings Generated: ${details.stats.ocrChars > 0 ? 840 : 0} nodes

## AI Content Summary
${details.summary}

## Topics Cataloged
${details.topics.map((t) => `- ${t}`).join("\n")}

## Detected Visual Artifacts
${details.objects.map((o) => `- ${o}`).join("\n")}

## Chronological Scene Breakdown
${details.scenes
  .map(
    (s) =>
      `### Scene ${s.index} [${s.timeStart} â€“ ${s.timeEnd}]: ${s.title}\n${s.description}`
  )
  .join("\n\n")}

---
VideoSceneRAG Retrieval Engine Audit Log. File generated locally.
`;

    const blob = new Blob([reportMarkdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${video.id}_pipeline_report.md`;
    link.click();
    URL.revokeObjectURL(url);

    toast.success("Pipeline Markdown audit report downloaded successfully.");
  };

  // Action: Delete Video Asset
  const handleDeleteConfirm = () => {
    if (!video) return;

    // Delete from library state
    const saved = localStorage.getItem("video-library-data");
    const library: LibraryVideo[] = saved ? JSON.parse(saved) : initialLibraryVideos;
    const remaining = library.filter((v) => v.id !== video.id);
    localStorage.setItem("video-library-data", JSON.stringify(remaining));

    // Clear uploads history matching this ID if any
    const savedRecent = localStorage.getItem("video-recent-uploads");
    if (savedRecent) {
      const recent = JSON.parse(savedRecent);
      const filteredRecent = recent.filter((r: any) => r.id !== video.id);
      localStorage.setItem("video-recent-uploads", JSON.stringify(filteredRecent));
    }

    toast.success(`"${video.title}" has been permanently deleted.`);
    setDeleteOpen(false);
    navigate("/videos");
  };

  if (!video || !details) {
    return (
      <div className="flex h-96 items-center justify-center">
        <div className="text-center space-y-2">
          <Clock className="h-8 w-8 animate-spin text-primary mx-auto" />
          <p className="text-sm text-muted-foreground">Loading video details...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1600px] space-y-7 animate-fade-in">
      {/* Header back navigation */}
      <div className="flex flex-col gap-2">
        <Button variant="ghost" size="sm" asChild className="self-start text-muted-foreground hover:text-foreground pl-0">
          <Link to="/videos">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back to library
          </Link>
        </Button>
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <PageHeader
            eyebrow="Asset summary"
            title="Video details"
            description="Overview of the ingested text metadata, visual segments, and structural extraction properties."
          />

          {/* Quick Actions Panel */}
          <div className="flex flex-wrap items-center gap-2 self-start sm:self-auto">
            {video.status === "Processing" ? (
              <Button asChild variant="primary" size="sm" className="h-9 gap-1.5 shadow-sm">
                <Link to={`/videos/${video.id}/processing`}>
                  View Processing Progress
                  <Sparkles className="h-4 w-4 animate-spin text-white" />
                </Link>
              </Button>
            ) : (
              <Button asChild variant="primary" size="sm" className="h-9 gap-1.5 shadow-sm">
                <Link to={`/videos/${video.id}/timeline`}>
                  <Play className="h-4 w-4 fill-current" />
                  Open Workspace
                </Link>
              </Button>
            )}
            
            <Button variant="outline" size="sm" onClick={handleReprocess} className="h-9 gap-1.5 hover:border-border">
              <RotateCcw className="h-4 w-4 text-muted-foreground" />
              Reprocess
            </Button>
            <Button variant="outline" size="sm" onClick={handleDownloadReport} className="h-9 gap-1.5 hover:border-border">
              <Download className="h-4 w-4 text-muted-foreground" />
              Download Report
            </Button>
            <Button variant="destructive" size="sm" onClick={() => setDeleteOpen(true)} className="h-9 gap-1.5 shadow-xs">
              <Trash2 className="h-4 w-4" />
              Delete
            </Button>
          </div>
        </div>
      </div>

      {/* Reusable VideoHeader summary row */}
      <VideoHeader video={video} />

      {/* Processing report statistics grid (animated stats cards) */}
      <div>
        <h3 className="text-xs font-bold uppercase tracking-wider text-foreground mb-4 text-left">
          Ingestion Processing Report
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-4">
          <ReportCard
            title="Total Scenes"
            value={details.stats.scenes}
            label="Visual splits"
            icon={Video}
            colorClass="text-indigo-500 border-indigo-200/50 bg-indigo-50/50 dark:bg-indigo-950/20 dark:border-indigo-900/50"
          />
          <ReportCard
            title="Total Frames"
            value={details.stats.frames}
            label="Sampled outputs"
            icon={Image}
            colorClass="text-cyan-500 border-cyan-200/50 bg-cyan-50/50 dark:bg-cyan-950/20 dark:border-cyan-900/50"
          />
          <ReportCard
            title="OCR Detections"
            value={details.stats.ocrChars}
            label="Recognized words"
            icon={Layers}
            colorClass="text-amber-500 border-amber-200/50 bg-amber-50/50 dark:bg-amber-950/20 dark:border-amber-900/50"
          />
          <ReportCard
            title="Dialogue Spans"
            value={details.stats.transcriptSpans}
            label="Whisper segments"
            icon={Mic}
            colorClass="text-emerald-500 border-emerald-200/50 bg-emerald-50/50 dark:bg-emerald-950/20 dark:border-emerald-900/50"
          />
          <ReportCard
            title="Speakers"
            value={details.stats.speakers}
            label="Diarized voices"
            icon={Cpu}
            colorClass="text-violet-500 border-violet-200/50 bg-violet-50/50 dark:bg-violet-950/20 dark:border-violet-900/50"
          />
          <ReportCard
            title="Process Time"
            value={details.stats.duration}
            label="Pipeline duration"
            icon={Clock}
            colorClass="text-pink-500 border-pink-200/50 bg-pink-50/50 dark:bg-pink-950/20 dark:border-pink-900/50"
          />
        </div>
      </div>

      {/* Main Grid: Content summary (Left) & Scene boundary list (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column: AI Summary, objects list, language information */}
        <div className="lg:col-span-4">
          <SummaryPanel
            summaryText={details.summary}
            objects={details.objects}
            ocrChars={details.stats.ocrChars}
          />
        </div>

        {/* Right Column: Key topics list & Ingested Scene boundaries card stack */}
        <div className="lg:col-span-8 space-y-6">
          {/* Key Topics List chips */}
          <Card className="p-5 border border-border/80 bg-card text-left space-y-4">
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-1.5">
                <Database className="h-4.5 w-4.5 text-primary" />
                Indexed Key Topics
              </h4>
              <p className="text-[11px] text-muted-foreground mt-0.5">
                Core query topics mapped to ChromaDB retrieval nodes for semantic scene search.
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5 pt-1">
              {details.topics.map((topic, idx) => (
                <TopicChip key={topic} label={topic} active={idx === 0} />
              ))}
            </div>
          </Card>

          {/* Segmented Scene Breakdown list */}
          <div className="space-y-4">
            <div className="flex items-center justify-between border-b pb-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-1.5">
                <Video className="h-4.5 w-4.5 text-primary" />
                Chronological Scene Breakdown
              </h4>
              <Badge variant="secondary" className="h-5 px-1.5 text-[10px] font-bold bg-muted/60 border">
                {details.scenes.length} scene splits
              </Badge>
            </div>

            <div className="grid grid-cols-1 gap-3.5">
              {details.scenes.map((scene) => (
                <SceneCard
                  key={scene.id}
                  scene={scene}
                  onClick={
                    video.status !== "Processing"
                      ? () => navigate(`/videos/${video.id}/timeline`)
                      : undefined
                  }
                />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Deletion confirmation dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base font-bold flex items-center gap-2 text-rose-600">
              <Trash2 className="h-5 w-5" />
              Delete video asset
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              This action cannot be undone and will erase all metadata.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <p className="text-sm text-foreground">
              Are you sure you want to delete <span className="font-semibold text-foreground">"{video.title}"</span>? This will permanently wipe all extracted video timelines, OCR, transcript indexes, and speaker clusters.
            </p>
          </div>
          <div className="flex justify-end gap-2 border-t pt-4">
            <Button variant="ghost" size="sm" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button variant="destructive" size="sm" onClick={handleDeleteConfirm}>
              Confirm Delete
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

