import { useState, useRef, type DragEvent, type ChangeEvent } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import {
  UploadCloud,
  FileVideo,
  CheckCircle2,
  AlertCircle,
  X,
  Clock,
  Play,
  Tag,
  Shield,
  Compass,
  Loader2,
  HardDrive,
  Check,
  Eye,
  Activity
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

// Max file size: 5GB in bytes
const MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024;
const ACCEPTED_VIDEO_TYPES = [
  "video/mp4",
  "video/quicktime", // .mov
  "video/x-msvideo", // .avi
  "video/x-matroska", // .mkv
  "video/webm"
];

// Zod validation schema for video metadata
export const metadataSchema = z.object({
  title: z
    .string()
    .min(3, { message: "Title must be at least 3 characters long" })
    .max(100, { message: "Title must not exceed 100 characters" }),
  description: z
    .string()
    .max(500, { message: "Description must not exceed 500 characters" })
    .optional()
    .or(z.literal("")),
  tags: z
    .string()
    .refine(
      (val) => !val || val.split(",").every((t) => t.trim().length > 0),
      { message: "Tags must be comma-separated" }
    )
    .optional()
    .or(z.literal("")),
  category: z.string().min(1, { message: "Please select a category" }),
  privacy: z.string().min(1, { message: "Please select privacy access" })
});

export type MetadataFormValues = z.infer<typeof metadataSchema>;

// Helper to format file sizes
export function formatBytes(bytes: number, decimals = 2) {
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
}

// ----------------------------------------------------
// 1. UploadDropzone Component
// ----------------------------------------------------
interface UploadDropzoneProps {
  onFileSelect: (file: File) => void;
  onError: (errMsg: string) => void;
}

export function UploadDropzone({ onFileSelect, onError }: UploadDropzoneProps) {
  const [isDragActive, setIsDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrag = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setIsDragActive(true);
    } else if (e.type === "dragleave") {
      setIsDragActive(false);
    }
  };

  const validateAndSelectFile = (file: File | null) => {
    if (!file) return;

    // Check file type
    const isVideo = ACCEPTED_VIDEO_TYPES.includes(file.type) || 
                    /\.(mp4|mov|avi|mkv|webm)$/i.test(file.name);
    
    if (!isVideo) {
      onError("Invalid file format. Please drop a video file (MP4, MOV, AVI, MKV, WebM).");
      return;
    }

    // Check file size
    if (file.size > MAX_FILE_SIZE) {
      onError("File is too large. Maximum supported upload size is 5GB.");
      return;
    }

    onFileSelect(file);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSelectFile(e.dataTransfer.files[0]);
    }
  };

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSelectFile(e.target.files[0]);
    }
  };

  const onBrowseClick = () => {
    fileInputRef.current?.click();
  };

  return (
    <div
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
      onClick={onBrowseClick}
      className={`group relative flex min-h-[340px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-8 text-center transition-all duration-normal ease-emphasized ${
        isDragActive
          ? "border-primary bg-primary/5 scale-[0.99] shadow-soft"
          : "border-border/80 bg-card hover:border-primary/40 hover:bg-slate-50/40 dark:hover:bg-slate-900/10"
      }`}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".mp4,.mov,.avi,.mkv,.webm"
        className="hidden"
        onChange={handleInputChange}
        aria-label="Upload video file"
      />

      {/* Decorative center icon */}
      <div className={`mb-5 flex h-16 w-16 items-center justify-center rounded-full border transition duration-normal ${
        isDragActive ? "bg-primary text-white border-primary" : "bg-muted text-muted-foreground group-hover:scale-105"
      }`}>
        <UploadCloud className={`h-8 w-8 ${isDragActive ? "animate-bounce" : ""}`} />
      </div>

      <div className="max-w-md space-y-2">
        <h3 className="text-base font-bold tracking-tight text-foreground">
          {isDragActive ? "Drop the file here" : "Drag and drop your video file"}
        </h3>
        <p className="text-xs text-muted-foreground max-w-xs mx-auto leading-relaxed">
          Or click to <span className="text-primary font-semibold hover:underline">browse files</span> on your computer
        </p>
      </div>

      {/* Specifications list */}
      <div className="mt-8 flex items-center justify-center gap-6 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/80 border-t border-border/50 pt-5 w-full max-w-xs">
        <div className="flex flex-col items-center">
          <span className="text-foreground/90 font-bold mb-0.5">Formats</span>
          <span>MP4, MOV, AVI, MKV</span>
        </div>
        <div className="h-6 w-px bg-border/60" />
        <div className="flex flex-col items-center">
          <span className="text-foreground/90 font-bold mb-0.5">Max Size</span>
          <span>5 Gigabytes</span>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 2. UploadProgress Component
// ----------------------------------------------------
interface UploadProgressProps {
  fileName: string;
  fileSize: number;
  progress: number;
  speed: string;
  timeRemaining: string;
  onCancel: () => void;
}

export function UploadProgress({
  fileName,
  fileSize,
  progress,
  speed,
  timeRemaining,
  onCancel
}: UploadProgressProps) {
  return (
    <Card className="p-5 border shadow-soft bg-card space-y-4">
      {/* File Detail Row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3 min-w-0">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-indigo-50 text-primary border border-indigo-100 dark:bg-indigo-950/30 dark:border-indigo-900/50">
            {progress < 100 ? (
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
            ) : (
              <CheckCircle2 className="h-5 w-5 text-emerald-500" />
            )}
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold truncate text-card-foreground" title={fileName}>
              {fileName}
            </p>
            <p className="text-xs text-muted-foreground font-mono mt-0.5">{formatBytes(fileSize)}</p>
          </div>
        </div>

        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 rounded-full text-muted-foreground hover:text-foreground"
          onClick={onCancel}
          aria-label="Cancel upload"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Progress bar */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs font-semibold">
          <span className="text-muted-foreground">Uploading...</span>
          <span className="text-primary">{progress}%</span>
        </div>
        <div className="h-2 w-full rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
          <div
            className="h-full rounded-full bg-gradient-to-r from-primary to-violet-500 transition-all duration-300"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {/* Speed & Timer stats */}
      {progress < 100 && (
        <div className="flex justify-between text-[11px] font-medium text-muted-foreground border-t border-border/50 pt-3">
          <span className="flex items-center gap-1">
            <Activity className="h-3.5 w-3.5" />
            {speed}
          </span>
          <span className="flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" />
            {timeRemaining}
          </span>
        </div>
      )}
    </Card>
  );
}

// ----------------------------------------------------
// 3. MetadataForm Component
// ----------------------------------------------------
interface MetadataFormProps {
  onSubmit: (values: MetadataFormValues) => void;
  defaultTitle?: string;
  isSubmitting?: boolean;
}

export function MetadataForm({ onSubmit, defaultTitle = "", isSubmitting = false }: MetadataFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors }
  } = useForm<MetadataFormValues>({
    resolver: zodResolver(metadataSchema),
    defaultValues: {
      title: defaultTitle.replace(/\.[^/.]+$/, ""), // Strip file extension
      description: "",
      tags: "",
      category: "Product Review",
      privacy: "Shared with Workspace"
    }
  });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {/* Title */}
      <div className="space-y-1.5">
        <label htmlFor="form-title" className="text-xs font-bold text-foreground">
          Video Title <span className="text-rose-500">*</span>
        </label>
        <Input
          id="form-title"
          type="text"
          placeholder="e.g. Q3 product showcase walkthrough"
          className={`h-10 text-sm focus-ring ${errors.title ? "border-rose-500 focus:ring-rose-500/20" : ""}`}
          {...register("title")}
          disabled={isSubmitting}
        />
        {errors.title && (
          <p className="text-[11px] font-semibold text-rose-500 flex items-center gap-1">
            <AlertCircle className="h-3 w-3" />
            {errors.title.message}
          </p>
        )}
      </div>

      {/* Description */}
      <div className="space-y-1.5">
        <label htmlFor="form-desc" className="text-xs font-bold text-foreground">
          Description
        </label>
        <textarea
          id="form-desc"
          rows={3}
          placeholder="Provide context about what is covered in this video. This helps direct the RAG search."
          className={`focus-ring w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground hover:bg-background/85 transition-colors ${
            errors.description ? "border-rose-500 focus:ring-rose-500/20" : ""
          }`}
          {...register("description")}
          disabled={isSubmitting}
        />
        {errors.description && (
          <p className="text-[11px] font-semibold text-rose-500 flex items-center gap-1">
            <AlertCircle className="h-3 w-3" />
            {errors.description.message}
          </p>
        )}
      </div>

      {/* Tags */}
      <div className="space-y-1.5">
        <label htmlFor="form-tags" className="text-xs font-bold text-foreground">
          Tags <span className="text-[10px] font-normal text-muted-foreground">(comma-separated)</span>
        </label>
        <div className="relative">
          <Tag className="absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <Input
            id="form-tags"
            type="text"
            placeholder="research, product, planning"
            className="pl-9 h-10 text-sm focus-ring"
            {...register("tags")}
            disabled={isSubmitting}
          />
        </div>
        {errors.tags && (
          <p className="text-[11px] font-semibold text-rose-500 flex items-center gap-1">
            <AlertCircle className="h-3 w-3" />
            {errors.tags.message}
          </p>
        )}
      </div>

      {/* Select Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Category */}
        <div className="space-y-1.5">
          <label htmlFor="form-cat" className="text-xs font-bold text-foreground">
            Category
          </label>
          <div className="relative">
            <Compass className="absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <select
              id="form-cat"
              className="focus-ring h-10 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm text-foreground hover:bg-background/80 transition-colors"
              {...register("category")}
              disabled={isSubmitting}
            >
              <option>Product Review</option>
              <option>Training</option>
              <option>Customer Interview</option>
              <option>Internal All-Hands</option>
              <option>Marketing</option>
              <option>Other</option>
            </select>
          </div>
        </div>

        {/* Privacy */}
        <div className="space-y-1.5">
          <label htmlFor="form-privacy" className="text-xs font-bold text-foreground">
            Privacy Access
          </label>
          <div className="relative">
            <Shield className="absolute left-3.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <select
              id="form-privacy"
              className="focus-ring h-10 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm text-foreground hover:bg-background/80 transition-colors"
              {...register("privacy")}
              disabled={isSubmitting}
            >
              <option>Private</option>
              <option>Shared with Workspace</option>
              <option>Public Link</option>
            </select>
          </div>
        </div>
      </div>

      <div className="pt-4">
        <Button type="submit" className="w-full h-10 shadow-sm" disabled={isSubmitting}>
          {isSubmitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Saving Metadata...
            </>
          ) : (
            "Complete Upload & Start Pipeline"
          )}
        </Button>
      </div>
    </form>
  );
}

// ----------------------------------------------------
// 4. UploadQueue Component
// ----------------------------------------------------
export interface QueueItem {
  id: string;
  name: string;
  size: number;
  progress: number;
  status: "uploading" | "pending" | "completed" | "error";
  errorMsg?: string;
}

interface UploadQueueProps {
  items: QueueItem[];
  onRemove: (id: string) => void;
}

export function UploadQueue({ items, onRemove }: UploadQueueProps) {
  if (items.length === 0) return null;

  return (
    <Card className="p-4 border shadow-soft bg-card space-y-3">
      <div className="flex items-center justify-between border-b pb-2">
        <h4 className="text-xs font-bold uppercase tracking-wider text-foreground">Upload Batch Queue</h4>
        <Badge variant="outline" className="h-5 px-1.5 text-[10px] font-bold bg-muted/50 border shadow-xs">
          {items.length} {items.length === 1 ? "file" : "files"}
        </Badge>
      </div>

      <div className="space-y-2 max-h-48 overflow-y-auto divide-y divide-border/40">
        {items.map((item) => (
          <div key={item.id} className="flex items-center justify-between gap-3 pt-2 first:pt-0">
            <div className="flex items-center gap-2.5 min-w-0">
              <FileVideo className="h-4 w-4 text-muted-foreground shrink-0" />
              <div className="min-w-0 text-xs">
                <p className="font-semibold truncate text-card-foreground" title={item.name}>
                  {item.name}
                </p>
                <p className="text-[10px] text-muted-foreground font-mono mt-0.5">
                  {formatBytes(item.size)} · {item.status === "uploading" ? `${item.progress}%` : item.status}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {item.status === "uploading" && <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />}
              {item.status === "completed" && <Check className="h-3.5 w-3.5 text-emerald-500 font-bold" />}
              {item.status === "error" && <AlertCircle className="h-3.5 w-3.5 text-rose-500" />}

              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 rounded-full text-muted-foreground hover:text-foreground"
                onClick={() => onRemove(item.id)}
                aria-label={`Remove ${item.name} from queue`}
              >
                <X className="h-3 w-3" />
              </Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ----------------------------------------------------
// 5. UploadCard Component (Recent uploads)
// ----------------------------------------------------
interface RecentUploadItem {
  id: string;
  title: string;
  filename: string;
  size: number;
  date: string;
  status: "Completed" | "Processing" | "Indexed" | "Failed" | "Uploaded";
}

interface UploadCardProps {
  item: RecentUploadItem;
  onOpen: (id: string) => void;
}

export function UploadCard({ item, onOpen }: UploadCardProps) {
  // Map styles based on status
  const badgeColors: Record<RecentUploadItem["status"], string> = {
    Uploaded: "bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-900/60 dark:text-slate-300 dark:border-slate-800",
    Processing: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-900/50",
    Completed: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-900/50",
    Indexed: "bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-950/30 dark:text-cyan-400 dark:border-cyan-900/50",
    Failed: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-950/30 dark:text-rose-400 dark:border-rose-900/50"
  };

  return (
    <Card className="group relative border shadow-sm hover:shadow-soft bg-card p-4 transition-all duration-normal ease-emphasized">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-slate-50 dark:bg-slate-900 border group-hover:bg-slate-100 dark:group-hover:bg-slate-850 transition-colors">
            <FileVideo className="h-5 w-5 text-muted-foreground group-hover:text-primary transition-colors" />
          </div>
          <div className="min-w-0">
            <h4 className="text-sm font-semibold truncate text-card-foreground group-hover:text-primary transition-colors" title={item.title}>
              {item.title}
            </h4>
            <p className="text-[11px] text-muted-foreground truncate font-mono mt-0.5">{item.filename}</p>
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-border/40 pt-3">
        <span className="flex items-center gap-1 text-[10px] text-muted-foreground font-semibold">
          <HardDrive className="h-3 w-3" />
          {formatBytes(item.size)}
        </span>
        <Badge variant="outline" className={`h-5 px-1.5 text-[9px] font-bold ${badgeColors[item.status]}`}>
          {item.status}
        </Badge>
      </div>

      {/* Hover slide action */}
      <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/70 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity backdrop-blur-xs">
        <Button
          size="sm"
          variant="primary"
          onClick={() => onOpen(item.id)}
          className="h-8 rounded-full px-4 text-xs font-semibold shadow-md"
        >
          <Play className="mr-1 h-3.5 w-3.5 fill-current" /> Open Workspace
        </Button>
      </div>
    </Card>
  );
}
