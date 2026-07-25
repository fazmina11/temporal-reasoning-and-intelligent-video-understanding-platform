import { type ComponentType, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  Loader2,
  AlertTriangle,
  Clock,
  HardDrive,
  Cpu,
  Terminal,
  Image,
  Video,
  Mic,
  Volume2,
  Database,
  Layers,
  Sparkles,
  ArrowRight
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type StageStatus = "queued" | "processing" | "completed" | "failed";

export interface StageData {
  id: string;
  name: string;
  icon: ComponentType<any>;
  status: StageStatus;
  progress: number;
  duration: string;
}

// ----------------------------------------------------
// 1. PipelineStage Component
// ----------------------------------------------------
interface PipelineStageProps {
  stage: StageData;
}

export function PipelineStage({ stage }: PipelineStageProps) {
  const Icon = stage.icon;

  // Status mapping
  const statusConfig = {
    queued: {
      bg: "bg-slate-50 dark:bg-slate-900/20 text-slate-400 border-slate-200/50 dark:border-slate-800/50",
      statusText: "Queued",
      icon: <div className="h-4 w-4 rounded-full border-2 border-slate-300 dark:border-slate-700 border-dotted" />
    },
    processing: {
      bg: "bg-amber-500/5 dark:bg-amber-500/5 text-amber-500 border-amber-500/20 shadow-xs",
      statusText: "Processing",
      icon: <Loader2 className="h-4 w-4 animate-spin text-amber-500" />
    },
    completed: {
      bg: "bg-emerald-500/5 dark:bg-emerald-500/5 text-emerald-500 border-emerald-500/20",
      statusText: "Complete",
      icon: <CheckCircle2 className="h-4 w-4 text-emerald-500" />
    },
    failed: {
      bg: "bg-rose-500/5 dark:bg-rose-500/5 text-rose-500 border-rose-500/20",
      statusText: "Failed",
      icon: <AlertTriangle className="h-4 w-4 text-rose-500" />
    }
  };

  const current = statusConfig[stage.status];

  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 p-3.5 border rounded-xl bg-card transition-all duration-normal hover:shadow-soft",
        stage.status === "processing" ? "border-amber-500/40 ring-1 ring-amber-500/10 shadow-sm bg-amber-500/[0.01]" : "border-border/60"
      )}
    >
      <div className="flex items-center gap-3 min-w-0">
        {/* Animated icon background */}
        <div
          className={cn(
            "grid h-9 w-9 shrink-0 place-items-center rounded-lg border",
            stage.status === "processing"
              ? "bg-amber-500/10 text-amber-500 border-amber-500/30"
              : stage.status === "completed"
              ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/30"
              : "bg-slate-50 text-muted-foreground border-slate-200 dark:bg-slate-900/60 dark:border-slate-800"
          )}
        >
          <Icon className={cn("h-4.5 w-4.5", stage.status === "processing" ? "animate-pulse" : "")} />
        </div>

        <div className="min-w-0 text-left">
          <p className="text-xs font-bold leading-tight text-foreground">{stage.name}</p>
          <div className="flex items-center gap-1.5 mt-1">
            <span className="text-[10px] text-muted-foreground font-mono flex items-center gap-0.5">
              <Clock className="h-3 w-3" />
              {stage.duration}
            </span>
            {stage.status === "processing" && (
              <>
                <span className="text-[10px] text-muted-foreground font-mono">·</span>
                <span className="text-[10px] font-bold text-amber-500 font-mono">{stage.progress}%</span>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {stage.status === "processing" && stage.progress > 0 && (
          <div className="hidden sm:block w-16 h-1 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
            <div className="h-full bg-amber-500 rounded-full" style={{ width: `${stage.progress}%` }} />
          </div>
        )}
        <Badge
          variant="outline"
          className={cn("h-5.5 px-2 text-[9px] font-bold rounded-full gap-1 items-center border", current.bg)}
        >
          {current.icon}
          {current.statusText}
        </Badge>
      </div>
    </div>
  );
}

// ----------------------------------------------------
// 2. ProcessingSummaryCard Component
// ----------------------------------------------------
interface SummaryCardProps {
  title: string;
  value: number | string;
  icon: ComponentType<any>;
  colorClass?: string;
}

export function ProcessingSummaryCard({ title, value, icon: Icon, colorClass = "text-primary bg-primary/5" }: SummaryCardProps) {
  return (
    <Card className="p-4 border border-border/70 bg-card hover:shadow-soft transition-shadow">
      <div className="flex items-center justify-between gap-3">
        <div className="text-left space-y-1 min-w-0">
          <span className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground block truncate">
            {title}
          </span>
          <motion.p
            key={value}
            initial={{ scale: 0.95, opacity: 0.8 }}
            animate={{ scale: 1, opacity: 1 }}
            className="text-lg font-bold font-mono text-card-foreground"
          >
            {value}
          </motion.p>
        </div>
        <div className={cn("grid h-9 w-9 shrink-0 place-items-center rounded-lg border", colorClass)}>
          <Icon className="h-4.5 w-4.5" />
        </div>
      </div>
    </Card>
  );
}

// ----------------------------------------------------
// 3. ProcessingTimeline Component
// ----------------------------------------------------
export interface Milestone {
  name: string;
  stages: string[];
  status: StageStatus;
  label: string;
}

interface ProcessingTimelineProps {
  milestones: Milestone[];
}

export function ProcessingTimeline({ milestones }: ProcessingTimelineProps) {
  return (
    <div className="py-4 overflow-x-auto select-none">
      <div className="flex items-center min-w-[700px] justify-between px-6">
        {milestones.map((ms, index) => {
          const isLast = index === milestones.length - 1;
          const isActive = ms.status === "processing";
          const isDone = ms.status === "completed";

          return (
            <div key={ms.name} className="flex items-center flex-1 last:flex-initial">
              {/* Milestone Node */}
              <div className="flex flex-col items-center relative">
                {/* Node circle */}
                <div
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-full border transition-all duration-normal",
                    isDone
                      ? "bg-emerald-500 border-emerald-500 text-white shadow-md shadow-emerald-500/20"
                      : isActive
                      ? "bg-amber-500 border-amber-500 text-white shadow-md shadow-amber-500/20 animate-pulse"
                      : "bg-card border-border text-muted-foreground"
                  )}
                >
                  {isDone ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : isActive ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <span className="text-xs font-bold font-mono">{index + 1}</span>
                  )}
                </div>

                {/* Node labels */}
                <div className="absolute top-10 w-24 text-center">
                  <p className="text-[10px] font-bold text-foreground leading-tight">{ms.name}</p>
                  <p className="text-[8px] font-medium text-muted-foreground mt-0.5">{ms.label}</p>
                </div>
              </div>

              {/* Connecting Connector Line */}
              {!isLast && (
                <div className="flex-1 mx-2 relative h-1 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                  <motion.div
                    className={cn(
                      "h-full rounded-full",
                      isDone
                        ? "bg-emerald-500"
                        : isActive
                        ? "bg-gradient-to-r from-emerald-500 to-amber-500"
                        : "bg-slate-200 dark:bg-slate-700"
                    )}
                    initial={{ width: 0 }}
                    animate={{ width: isDone ? "100%" : isActive ? "60%" : "0%" }}
                    transition={{ duration: 0.4 }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
      {/* Spacer for bottom labels */}
      <div className="h-9" />
    </div>
  );
}

// ----------------------------------------------------
// 4. ActivityLog Component
// ----------------------------------------------------
export interface LogMessage {
  time: string;
  module: string;
  level: "INFO" | "WARN" | "SUCCESS" | "DEBUG";
  text: string;
}

interface ActivityLogProps {
  logs: LogMessage[];
}

export function ActivityLog({ logs }: ActivityLogProps) {
  const terminalEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom of logs
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  const levelColors = {
    INFO: "text-blue-400",
    WARN: "text-amber-400 font-semibold",
    SUCCESS: "text-emerald-400 font-bold",
    DEBUG: "text-slate-500"
  };

  return (
    <Card className="border border-slate-800 bg-slate-950 text-slate-100 shadow-elevated rounded-xl overflow-hidden flex flex-col h-64">
      {/* Console Title Header */}
      <div className="flex items-center justify-between bg-slate-900 px-4 py-2 border-b border-slate-800 shrink-0">
        <div className="flex items-center gap-2">
          <Terminal className="h-4 w-4 text-slate-400" />
          <span className="font-mono text-xs font-semibold text-slate-300">System Pipeline Log Console</span>
        </div>
        <div className="flex gap-1.5">
          <div className="h-2.5 w-2.5 rounded-full bg-rose-500/80" />
          <div className="h-2.5 w-2.5 rounded-full bg-amber-500/80" />
          <div className="h-2.5 w-2.5 rounded-full bg-emerald-500/80" />
        </div>
      </div>

      {/* Terminal Feed logs */}
      <div className="flex-1 overflow-y-auto p-4 font-mono text-[11px] leading-5 space-y-1 scrollbar-thin select-text">
        {logs.length === 0 ? (
          <p className="text-slate-500 italic">Initializing logging feed modules...</p>
        ) : (
          logs.map((log, index) => (
            <div key={index} className="flex gap-1.5 items-start">
              <span className="text-slate-500 shrink-0 select-none">[{log.time}]</span>
              <span className="text-indigo-400 shrink-0 select-none">[{log.module}]</span>
              <span className={cn("shrink-0 select-none", levelColors[log.level])}>
                {log.level}:
              </span>
              <span className="text-slate-300 break-all">{log.text}</span>
            </div>
          ))
        )}
        <div ref={terminalEndRef} />
      </div>
    </Card>
  );
}
