import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, UploadCloud, Film, Settings, Cpu, HardDrive, CheckCircle2, RotateCcw, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/global/headers";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  UploadDropzone,
  UploadProgress,
  MetadataForm,
  UploadQueue,
  UploadCard,
  type MetadataFormValues,
  type QueueItem
} from "@/features/upload/upload-components";
import { useUpload } from "@/hooks/api/use-upload";

interface RecentUploadItem {
  id: string;
  title: string;
  filename: string;
  size: number;
  date: string;
  status: "Completed" | "Processing" | "Indexed" | "Failed" | "Uploaded";
}

const formatBytes = (bytes: number) => {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, index);
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
};

export function VideoUploadPage() {
  const navigate = useNavigate();
  const uploadMutation = useUpload();
  
  // File & Upload States
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [durationStr, setDurationStr] = useState("0:00");
  
  // Progress Simulation States
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadSpeed, setUploadSpeed] = useState("0.0 MB/s");
  const [timeRemaining, setTimeRemaining] = useState("Calculating...");
  const [isUploading, setIsUploading] = useState(false);
  const [isUploadComplete, setIsUploadComplete] = useState(false);

  // Queue state (to showcase multi-file capabilities)
  const [queue, setQueue] = useState<QueueItem[]>([]);

  // Recent Uploads log state for this browser session.
  const [recentUploads, setRecentUploads] = useState<RecentUploadItem[]>([]);

  // Clean up Object URL on unmount or file reset
  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  // Upload Simulation Loop
  useEffect(() => {
    if (!isUploading || !selectedFile) return;

    // Speeds around 4.5 MB/s to 7 MB/s
    const speedBytes = (4.5 + Math.random() * 2.5) * 1024 * 1024;
    setUploadSpeed(`${(speedBytes / (1024 * 1024)).toFixed(1)} MB/s`);

    const interval = setInterval(() => {
      setUploadProgress((prev) => {
        const remaining = 100 - prev;
        // Step size decays slightly as it nears completion
        const step = Math.max(1, Math.min(12, Math.floor(Math.random() * 8) + 2));
        const next = prev + step;

        if (next >= 100) {
          clearInterval(interval);
          setIsUploading(false);
          setIsUploadComplete(true);
          setUploadProgress(100);
          
          // Update queue status
          setQueue((prevQ) =>
            prevQ.map((item) =>
              item.name === selectedFile.name ? { ...item, progress: 100, status: "completed" } : item
            )
          );

          toast.success("File upload finished successfully!");
          return 100;
        }

        // Update queue item progress
        setQueue((prevQ) =>
          prevQ.map((item) =>
            item.name === selectedFile.name ? { ...item, progress: next, status: "uploading" } : item
          )
        );

        // Estimate time remaining
        const remainingSize = ((100 - next) / 100) * selectedFile.size;
        const seconds = Math.ceil(remainingSize / speedBytes);
        if (seconds < 60) {
          setTimeRemaining(`${seconds} sec remaining`);
        } else {
          const mins = Math.floor(seconds / 60);
          const secs = seconds % 60;
          setTimeRemaining(`${mins} min ${secs} sec remaining`);
        }

        return next;
      });
    }, 400);

    return () => clearInterval(interval);
  }, [isUploading, selectedFile]);

  // File selection handler
  const handleFileSelect = (file: File) => {
    setSelectedFile(file);
    setUploadProgress(0);
    setIsUploadComplete(false);
    setIsUploading(true);

    const objUrl = URL.createObjectURL(file);
    setPreviewUrl(objUrl);

    // Add to mock queue
    const queueItem: QueueItem = {
      id: `queue-${Date.now()}`,
      name: file.name,
      size: file.size,
      progress: 0,
      status: "uploading"
    };
    setQueue([queueItem]);
  };

  const handleFileError = (errMsg: string) => {
    toast.error(errMsg, { duration: 4000 });
  };

  const handleCancelUpload = () => {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    setSelectedFile(null);
    setUploadProgress(0);
    setIsUploading(false);
    setIsUploadComplete(false);
    setQueue([]);
    toast.info("Upload cancelled.");
  };

  const handleRemoveQueueItem = (id: string) => {
    setQueue((prev) => prev.filter((item) => item.id !== id));
    if (selectedFile) {
      setSelectedFile(null);
      setUploadProgress(0);
      setIsUploading(false);
      setIsUploadComplete(false);
    }
  };

  // Video duration reader
  const handleLoadedMetadata = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    const duration = e.currentTarget.duration;
    if (isNaN(duration)) return;
    const minutes = Math.floor(duration / 60);
    const seconds = Math.floor(duration % 60);
    setDurationStr(`${minutes}:${seconds.toString().padStart(2, "0")}`);
  };

  // Form submission handler connected to FastAPI backend
  const handleMetadataSubmit = async (values: MetadataFormValues) => {
    if (!selectedFile) return;

    if (!isUploadComplete) {
      toast.warning("Please wait for the file transfer to complete before submitting.");
      return;
    }

    setIsUploading(true);

    try {
      const response = await uploadMutation.mutateAsync(selectedFile);
      const videoId = response.video_id;

      setRecentUploads((prev) => [
        {
          id: videoId,
          title: values.title,
          filename: selectedFile.name,
          size: selectedFile.size,
          date: "Just now",
          status: "Processing"
        },
        ...prev
      ]);

      toast.success(`"${values.title}" uploaded. Starting AI processing pipeline...`);
      navigate(`/videos/${videoId}/processing`);
    } catch (err) {
      console.error("Upload Error:", err);
      toast.error("Upload failed. Please confirm the FastAPI backend is running and try again.");
    } finally {
      setIsUploading(false);
    }
  };

  const handleOpenRecentWorkspace = (id: string) => {
    navigate(`/videos/${id}`);
  };

  const clearRecentLogs = () => {
    setRecentUploads([]);
    toast.success("Recent uploads history cleared.");
  };

  return (
    <div className="mx-auto max-w-[1600px] space-y-7 animate-fade-in">
      {/* Header with back navigation */}
      <div className="flex flex-col gap-2">
        <Button variant="ghost" size="sm" asChild className="self-start text-muted-foreground hover:text-foreground pl-0">
          <Link to="/videos">
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back to library
          </Link>
        </Button>
        <PageHeader
          eyebrow="Upload video"
          title="Import raw footage"
          description="Drag video assets into the workspace to automatically start indexing transcription, scene segmentation, and retrieval tags."
        />
      </div>

      {/* Main Layout Grid */}
      {!selectedFile ? (
        /* PHASE A: Upload Zone & Recent Uploads list */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          <div className="lg:col-span-7">
            <UploadDropzone onFileSelect={handleFileSelect} onError={handleFileError} />
          </div>

          <div className="lg:col-span-5 space-y-5">
            {/* Guide Info Box */}
            <Card className="p-5 border bg-slate-50/50 dark:bg-slate-900/10 space-y-3">
              <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-1.5">
                <Cpu className="h-4 w-4 text-primary" />
                Pipeline Analysis Ingest
              </h4>
              <p className="text-xs text-muted-foreground leading-relaxed">
                Upon completing the upload, your video will run through the RAG segmentation pipeline:
              </p>
              <div className="grid grid-cols-2 gap-3 text-[11px] font-semibold text-foreground/80 pt-1">
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                  <span>Whisper Transcript</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                  <span>OCR Text Frame</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                  <span>Speaker Turns</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                  <span>ChromaDB Vectors</span>
                </div>
              </div>
            </Card>

            {/* Recent Uploads panel */}
            <Card className="p-5 border bg-card space-y-4">
              <div className="flex items-center justify-between border-b pb-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">Recent Uploads Log</h4>
                {recentUploads.length > 0 && (
                  <Button variant="ghost" size="sm" onClick={clearRecentLogs} className="h-6 text-[10px] text-muted-foreground hover:text-foreground gap-1.5">
                    <RotateCcw className="h-3 w-3" /> Clear History
                  </Button>
                )}
              </div>

              {recentUploads.length > 0 ? (
                <div className="grid grid-cols-1 gap-3">
                  {recentUploads.map((item) => (
                    <UploadCard key={item.id} item={item} onOpen={handleOpenRecentWorkspace} />
                  ))}
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center p-6 text-center">
                  <p className="text-xs text-muted-foreground font-medium">No recent uploads recorded.</p>
                </div>
              )}
            </Card>
          </div>
        </div>
      ) : (
        /* PHASE B: Preview, Progress & Metadata Form editing layout */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
          {/* Left Column: Preview + Progress bar */}
          <div className="lg:col-span-5 space-y-6">
            {/* HTML5 Video Player preview */}
            <Card className="overflow-hidden border bg-black shadow-soft relative rounded-xl aspect-video flex items-center justify-center">
              {previewUrl && (
                <video
                  src={previewUrl}
                  controls
                  onLoadedMetadata={handleLoadedMetadata}
                  className="w-full h-full object-contain"
                  poster="/assets/video-poster.jpg"
                />
              )}
              {/* Overlay badges */}
              <div className="absolute top-3 left-3 bg-slate-900/80 text-white text-[10px] px-2 py-0.5 rounded backdrop-blur font-semibold flex items-center gap-1">
                <Film className="h-3 w-3 text-indigo-400" /> Local Preview
              </div>
              <div className="absolute top-3 right-3 bg-slate-900/80 text-white text-[10px] px-2 py-0.5 rounded backdrop-blur font-mono">
                {durationStr}
              </div>
            </Card>

            {/* Progress component */}
            <UploadProgress
              fileName={selectedFile.name}
              fileSize={selectedFile.size}
              progress={uploadProgress}
              speed={uploadSpeed}
              timeRemaining={timeRemaining}
              onCancel={handleCancelUpload}
            />

            {/* Queue items list */}
            <UploadQueue items={queue} onRemove={handleRemoveQueueItem} />
          </div>

          {/* Right Column: Metadata form */}
          <div className="lg:col-span-7">
            <Card className="p-6 border shadow-soft bg-card space-y-5">
              <div>
                <h3 className="text-base font-bold tracking-tight text-foreground flex items-center gap-2">
                  <Settings className="h-4.5 w-4.5 text-primary" />
                  Asset Metadata Configuration
                </h3>
                <p className="mt-1 text-xs text-muted-foreground">
                  Provide metadata details. These parameters are parsed to index search nodes.
                </p>
              </div>

              <hr className="border-border/60" />

              <MetadataForm
                onSubmit={handleMetadataSubmit}
                defaultTitle={selectedFile.name}
                isSubmitting={isUploading}
              />
              
              {!isUploadComplete && (
                <p className="text-[10px] font-semibold text-amber-600 dark:text-amber-500 bg-amber-50 dark:bg-amber-950/20 border border-amber-200/50 p-2.5 rounded-lg text-center flex items-center justify-center gap-1.5">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Transferring data... You can fill in the metadata details while the file uploads.
                </p>
              )}
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}





