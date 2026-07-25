import { type ComponentType } from "react";
import {
  Clock,
  HardDrive,
  Cpu,
  Image,
  Video,
  Mic,
  Layers,
  Database,
  Monitor,
  Calendar,
  Sparkles,
  Volume2,
  FileText,
  Bookmark,
  BookOpen
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/features/library/library-primitives";
import type { LibraryVideo } from "@/types/api";
import { cn } from "@/lib/utils";

// ----------------------------------------------------
// 1. VideoHeader Component
// ----------------------------------------------------
interface VideoHeaderProps {
  video: LibraryVideo;
  resolution?: string;
}

export function VideoHeader({ video, resolution = "1080p (1920x1080)" }: VideoHeaderProps) {
  const iconProp = video.icon;
  const IconComponent = (typeof iconProp === "function" || (iconProp && typeof iconProp === "object" && "$$typeof" in iconProp))
    ? iconProp
    : Video;
  return (
    <Card className="overflow-hidden border border-border/80 bg-card shadow-soft">
      <div className="flex flex-col md:flex-row items-stretch">
        {/* Visual Gradient Thumbnail Area */}
        <div className={cn("md:w-72 shrink-0 h-40 md:h-auto bg-gradient-to-br relative flex items-end p-5 text-white", video.gradient)}>
          {/* Grid pattern overlay */}
          <div className="absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(255,255,255,.07)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.07)_1px,transparent_1px)] [background-size:1.25rem_1.25rem]" />
          
          <div className="absolute inset-0 bg-slate-950/20" />
          
          {/* Badge overlays */}
          <div className="relative flex w-full items-end justify-between z-10">
            <span className="grid h-10 w-10 place-items-center rounded-xl border border-white/10 bg-white/10 text-white backdrop-blur shadow-sm">
              <IconComponent className="h-5 w-5 animate-pulse" />
            </span>
            <span className="rounded-md bg-slate-950/80 px-2.5 py-0.5 font-mono text-[10px] font-bold text-slate-100 backdrop-blur shadow-sm">
              {video.duration}
            </span>
          </div>
        </div>

        {/* Text parameters area */}
        <div className="flex-1 p-5 md:p-6 flex flex-col justify-between text-left space-y-4 md:space-y-0">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={video.status} />
              <Badge variant="outline" className="text-[10px] font-mono font-bold bg-slate-50 border border-slate-200/80 dark:bg-slate-900/60 dark:border-slate-800/80">
                {video.pipelineVersion}
              </Badge>
            </div>
            <h2 className="text-xl font-bold tracking-tight text-foreground leading-snug">
              {video.title}
            </h2>
            <p className="text-xs font-mono text-muted-foreground break-all">{video.filename}</p>
          </div>

          <div className="flex flex-wrap items-center gap-x-6 gap-y-2.5 pt-4 border-t border-border/50 text-xs font-semibold text-muted-foreground/80">
            <span className="flex items-center gap-1.5">
              <HardDrive className="h-4 w-4 text-slate-400" />
              Size: <span className="text-foreground font-mono font-bold">{video.size}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <Monitor className="h-4 w-4 text-slate-400" />
              Resolution: <span className="text-foreground font-mono font-bold">{resolution}</span>
            </span>
            <span className="flex items-center gap-1.5">
              <Calendar className="h-4 w-4 text-slate-400" />
              Uploaded: <span className="text-foreground font-bold">{video.date}</span>
            </span>
          </div>
        </div>
      </div>
    </Card>
  );
}

// ----------------------------------------------------
// 2. ReportCard Component
// ----------------------------------------------------
interface ReportCardProps {
  title: string;
  value: string | number;
  label: string;
  icon: ComponentType<any>;
  colorClass: string;
}

export function ReportCard({ title, value, label, icon: Icon, colorClass }: ReportCardProps) {
  return (
    <Card className="p-4 border border-border/80 bg-card hover:shadow-soft transition-all duration-normal text-left">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1.5 min-w-0">
          <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block truncate">
            {title}
          </span>
          <p className="text-2xl font-bold font-mono text-foreground leading-none">
            {value}
          </p>
          <span className="text-[10px] text-muted-foreground/90 font-medium block">
            {label}
          </span>
        </div>
        <div className={cn("grid h-9 w-9 place-items-center rounded-lg border shrink-0 shadow-xs", colorClass)}>
          <Icon className="h-4.5 w-4.5" />
        </div>
      </div>
    </Card>
  );
}

// ----------------------------------------------------
// 3. TopicChip Component
// ----------------------------------------------------
interface TopicChipProps {
  label: string;
  active?: boolean;
}

export function TopicChip({ label, active = false }: TopicChipProps) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "px-2.5 py-1 text-xs font-semibold rounded-md border cursor-default select-none transition-colors",
        active
          ? "bg-primary/5 text-primary border-primary/30"
          : "bg-slate-50 border-slate-200/80 text-slate-700 hover:border-slate-300 hover:bg-slate-100/50 dark:bg-slate-900/50 dark:border-slate-800 dark:text-slate-300 dark:hover:border-slate-700 dark:hover:bg-slate-900"
      )}
    >
      {label}
    </Badge>
  );
}

// ----------------------------------------------------
// 4. SceneCard Component
// ----------------------------------------------------
export interface SceneItem {
  id: string;
  index: number;
  timeStart: string;
  timeEnd: string;
  title: string;
  description: string;
  gradient: string;
}

interface SceneCardProps {
  scene: SceneItem;
  onClick?: () => void;
}

export function SceneCard({ scene, onClick }: SceneCardProps) {
  return (
    <Card
      onClick={onClick}
      className={cn(
        "flex flex-col sm:flex-row items-stretch overflow-hidden border border-border/75 bg-card hover:border-primary/30 transition-all duration-normal text-left",
        onClick ? "cursor-pointer hover:shadow-soft" : ""
      )}
    >
      {/* Miniature Visual Slide Indicator */}
      <div className={cn("sm:w-36 shrink-0 h-24 sm:h-auto bg-gradient-to-br relative flex items-center justify-center p-3 text-white", scene.gradient)}>
        <div className="absolute inset-0 opacity-10 [background-image:linear-gradient(rgba(255,255,255,.07)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.07)_1px,transparent_1px)] [background-size:1rem_1rem]" />
        
        <Bookmark className="h-5 w-5 text-white/55 relative z-10 animate-pulse duration-slow" />
        <span className="absolute bottom-2 left-2 text-[9px] font-bold font-mono tracking-wider bg-slate-950/60 backdrop-blur-xs px-1.5 py-0.5 rounded border border-white/5">
          SCENE {scene.index}
        </span>
      </div>

      {/* Details Box */}
      <div className="flex-1 p-4 flex flex-col justify-between space-y-2">
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-3">
            <h4 className="text-xs font-bold text-foreground leading-tight truncate">
              {scene.title}
            </h4>
            <Badge variant="secondary" className="h-5 px-2 text-[10px] font-mono font-bold bg-slate-100 text-slate-700 dark:bg-slate-900 dark:text-slate-300 shrink-0 border border-slate-200 dark:border-slate-800">
              {scene.timeStart} â€“ {scene.timeEnd}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground leading-normal line-clamp-2">
            {scene.description}
          </p>
        </div>
      </div>
    </Card>
  );
}

// ----------------------------------------------------
// 5. SummaryPanel Component
// ----------------------------------------------------
interface SummaryPanelProps {
  summaryText: string;
  objects: string[];
  language?: string;
  accent?: string;
  ocrChars?: number;
}

export function SummaryPanel({
  summaryText,
  objects,
  language = "English (en-US)",
  accent = "General American",
  ocrChars = 4200
}: SummaryPanelProps) {
  return (
    <div className="space-y-6">
      {/* AI Content Summary Paragraph */}
      <Card className="p-5 border border-border/80 bg-card text-left space-y-3">
        <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-1.5">
          <BookOpen className="h-4 w-4 text-primary" />
          AI Context Summary
        </h4>
        <p className="text-xs text-muted-foreground leading-relaxed">
          {summaryText}
        </p>
      </Card>

      {/* Screen Object list */}
      <Card className="p-5 border border-border/80 bg-card text-left space-y-3">
        <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-1.5">
          <Monitor className="h-4.5 w-4.5 text-primary" />
          Detected Visual Screen Objects
        </h4>
        <div className="flex flex-wrap gap-1.5 pt-1">
          {objects.map((obj) => (
            <Badge
              key={obj}
              variant="secondary"
              className="text-[10px] bg-slate-100 text-slate-700 border border-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:border-slate-800"
            >
              {obj}
            </Badge>
          ))}
        </div>
      </Card>

      {/* Language parameters */}
      <Card className="p-5 border border-border/80 bg-card text-left space-y-3">
        <h4 className="text-xs font-bold uppercase tracking-wider text-foreground flex items-center gap-1.5">
          <Volume2 className="h-4.5 w-4.5 text-primary" />
          Diarization & Language Ingestion
        </h4>
        <div className="grid grid-cols-2 gap-3 text-xs pt-1">
          <div className="space-y-0.5">
            <span className="text-[10px] text-muted-foreground font-semibold">Speech Language</span>
            <p className="font-bold text-foreground">{language}</p>
          </div>
          <div className="space-y-0.5">
            <span className="text-[10px] text-muted-foreground font-semibold">Vocal Accent</span>
            <p className="font-bold text-foreground">{accent}</p>
          </div>
          <div className="space-y-0.5 col-span-2 border-t pt-2 mt-1">
            <span className="text-[10px] text-muted-foreground font-semibold">Optical Characters (OCR)</span>
            <p className="font-bold text-foreground font-mono">{ocrChars.toLocaleString()} index tokens</p>
          </div>
        </div>
      </Card>
    </div>
  );
}

