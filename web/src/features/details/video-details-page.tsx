import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Captions,
  Database,
  FileText,
  Film,
  Image,
  Layers,
  Mic,
  Play,
  RefreshCw,
  ScanText,
  Trash2,
  Volume2
} from "lucide-react";
import { buildWorkspaceViewModel } from "@/api/artifact-adapters";
import { PageHeader, SectionHeader } from "@/components/global/headers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  ReportCard,
  SceneCard,
  TopicChip,
  VideoHeader
} from "@/features/details/details-components";
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
  const stats = [
    ["Events", details.stats.events, "Explanation intervals", Film, "text-rose-600 bg-rose-500/10 border-rose-500/20"],
    ["Semantic chunks", details.stats.semanticChunks, "Topic segments", Layers, "text-blue-600 bg-blue-500/10 border-blue-500/20"],
    ["Transcript", details.stats.transcriptSpans, "Timestamped spans", Captions, "text-emerald-600 bg-emerald-500/10 border-emerald-500/20"],
    ["Frames", details.stats.frames, "Evidence images", Image, "text-indigo-600 bg-indigo-500/10 border-indigo-500/20"],
    ["OCR", details.stats.ocrRecords, "Visible-text records", ScanText, "text-cyan-600 bg-cyan-500/10 border-cyan-500/20"],
    ["Speakers", details.stats.speakers, "Diarized voices", Mic, "text-violet-600 bg-violet-500/10 border-violet-500/20"],
    ["Audio events", details.stats.audioEvents, "Acoustic intervals", Volume2, "text-amber-600 bg-amber-500/10 border-amber-500/20"]
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

  const handleDownload = () => {
    const report = [
      `# ${video.title}`,
      "",
      `Pipeline version: ${video.pipelineVersion}`,
      `Duration: ${video.duration}`,
      `Validation: ${details.validationPassed === null ? "not reported" : details.validationPassed ? "passed" : "failed"}`,
      "",
      "## Summary",
      details.summary,
      "",
      "## Topics",
      ...details.topics.map((topic) => `- ${topic}`),
      "",
      "## Timeline",
      ...details.scenes.map((scene) => `- ${scene.timeStart}-${scene.timeEnd}: ${scene.title}`)
    ].join("\n");
    const url = URL.createObjectURL(new Blob([report], { type: "text/markdown" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${videoId}_evidence_report.md`;
    link.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mx-auto max-w-[1500px] space-y-7">
      <PageHeader
        eyebrow="Canonical artifact overview"
        title="Video evidence profile"
        description="Every count and timeline entry below is derived from the persisted processing artifacts."
        actions={
          <>
            <Button variant="outline" onClick={handleDownload}><FileText className="h-4 w-4" />Export report</Button>
            <Button onClick={() => navigate(`/videos/${videoId}/timeline`)}><Play className="h-4 w-4" />Open workspace</Button>
          </>
        }
      />

      <VideoHeader
        video={video}
        resolution={resolutionLabel(manifest.resolution, manifest.width, manifest.height)}
      />

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7" aria-label="Artifact statistics">
        {stats.map(([title, value, label, Icon, colorClass]) => (
          <ReportCard key={title} title={title} value={value} label={label} icon={Icon} colorClass={colorClass} />
        ))}
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.35fr_.65fr]">
        <section>
          <div className="mb-4"><SectionHeader title="Explanation timeline" description="Validated events grouped from canonical semantic chunks." /></div>
          <div className="space-y-3">
            {details.scenes.map((scene) => (
              <SceneCard
                key={scene.id}
                scene={scene}
                onClick={() => navigate(`/videos/${videoId}/timeline?t=${scene.startSec}`)}
              />
            ))}
          </div>
        </section>

        <div className="space-y-5">
          <Card className="p-5">
            <SectionHeader title="Artifact summary" description="Generated from the event hierarchy." />
            <p className="mt-4 text-sm leading-6 text-muted-foreground">{details.summary}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {details.topics.map((topic) => <TopicChip key={topic} label={topic} />)}
            </div>
          </Card>

          <Card className="p-5">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-semibold"><Database className="h-4 w-4 text-cyan-600" />Readable OCR evidence</h2>
              <Badge variant="outline">{details.visibleTexts.length}</Badge>
            </div>
            <div className="mt-4 space-y-2">
              {details.visibleTexts.map((visibleText) => (
                <p key={visibleText} className="rounded-md border bg-muted/40 p-2 text-xs">{visibleText}</p>
              ))}
              {details.visibleTexts.length === 0 && <p className="text-xs text-muted-foreground">No readable OCR text is available.</p>}
            </div>
          </Card>

          <Card className="flex flex-wrap gap-2 p-4">
            <Button variant="outline" onClick={handleRetry} disabled={retryMutation.isPending}>
              <RefreshCw className="h-4 w-4" />Reprocess
            </Button>
            <Button variant="destructive" onClick={handleDelete} disabled={deleteMutation.isPending}>
              <Trash2 className="h-4 w-4" />Delete
            </Button>
          </Card>
        </div>
      </div>
    </div>
  );
}
