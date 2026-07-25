import { type ComponentType } from "react";
import { Film } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { VideoStatus } from "@/types/api";
import { cn } from "@/lib/utils";

// Custom premium styling for each status badge
const badgeStyles: Record<VideoStatus, { badge: string; dot: string }> = {
  Uploaded: {
    badge: "bg-slate-100 text-slate-700 border-slate-200/80 dark:bg-slate-900/60 dark:text-slate-300 dark:border-slate-800/80",
    dot: "bg-slate-400 dark:bg-slate-500"
  },
  Processing: {
    badge: "bg-amber-50 text-amber-700 border-amber-200/80 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-900/50",
    dot: "bg-amber-500 animate-pulse"
  },
  Completed: {
    badge: "bg-emerald-50 text-emerald-700 border-emerald-200/80 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-900/50",
    dot: "bg-emerald-500"
  },
  Failed: {
    badge: "bg-rose-50 text-rose-700 border-rose-200/80 dark:bg-rose-950/30 dark:text-rose-400 dark:border-rose-900/50",
    dot: "bg-rose-500"
  },
  Indexed: {
    badge: "bg-cyan-50 text-cyan-700 border-cyan-200/80 dark:bg-cyan-950/30 dark:text-cyan-400 dark:border-cyan-900/50",
    dot: "bg-cyan-500"
  }
};

interface StatusBadgeProps {
  status: VideoStatus;
  className?: string;
}

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const styles = badgeStyles[status] || badgeStyles.Uploaded;
  return (
    <Badge
      variant="outline"
      className={cn("gap-1.5 px-2 py-0.5 font-medium transition duration-fast shrink-0", styles.badge, className)}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", styles.dot)} aria-hidden="true" />
      {status}
    </Badge>
  );
}

interface ThumbnailProps {
  gradient: string;
  icon?: any;
  duration?: string;
  className?: string;
}

export function Thumbnail({ gradient, icon: iconProp, duration, className }: ThumbnailProps) {
  const Icon = (typeof iconProp === "function" || (iconProp && typeof iconProp === "object" && "$$typeof" in iconProp))
    ? iconProp
    : Film;

  return (
    <div
      className={cn(
        "relative flex items-end overflow-hidden rounded-lg bg-gradient-to-br p-3 transition-transform duration-slow ease-emphasized group-hover:scale-[1.02]",
        gradient,
        className
      )}
    >
      {/* Grid Pattern Overlay */}
      <div className="absolute inset-0 opacity-20 [background-image:linear-gradient(rgba(255,255,255,.07)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.07)_1px,transparent_1px)] [background-size:1.25rem_1.25rem]" />
      
      {/* Subtle Glow Ring */}
      <div className="absolute inset-0 bg-gradient-to-t from-slate-950/50 via-slate-950/10 to-transparent opacity-80" />

      {/* Content Container */}
      <div className="relative flex w-full items-end justify-between z-10">
        <span className="grid h-8 w-8 place-items-center rounded-lg border border-white/10 bg-white/10 text-white backdrop-blur shadow-sm transition-transform duration-normal group-hover:scale-105">
          <Icon className="h-4 w-4" aria-hidden="true" />
        </span>
        {duration && (
          <span className="rounded bg-slate-950/80 px-2 py-0.5 font-mono text-[10px] font-semibold text-slate-100 backdrop-blur shadow-sm">
            {duration}
          </span>
        )}
      </div>
    </div>
  );
}

