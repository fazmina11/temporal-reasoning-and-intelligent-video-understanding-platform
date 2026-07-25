import { Activity, BrainCircuit, Clock3, Database, FileCheck2, HardDrive, MessageSquareText, Play, ScanText, UploadCloud, Video, Zap } from "lucide-react";
export const dashboardStats = [
  { label: "Total videos", value: 48, display: "48", subtitle: "Across your workspace", trend: "+12%", trendText: "vs. last month", icon: Video, tone: "indigo" },
  { label: "Processed videos", value: 41, display: "41", subtitle: "Ready for questions", trend: "+8%", trendText: "vs. last month", icon: FileCheck2, tone: "emerald" },
  { label: "Processing jobs", value: 3, display: "03", subtitle: "2 active right now", trend: "2 active", trendText: "pipeline status", icon: Activity, tone: "amber" },
  { label: "AI questions asked", value: 1264, display: "1,264", subtitle: "Grounded conversations", trend: "+24%", trendText: "vs. last month", icon: MessageSquareText, tone: "violet" },
  { label: "Storage used", value: 68.4, display: "68.4 GB", subtitle: "of 250 GB workspace", trend: "27%", trendText: "capacity used", icon: HardDrive, tone: "cyan" },
] as const;
export const recentVideos = [
  { title: "MCP vs HTTP — technical deep dive", duration: "42:18", date: "Today, 10:24 AM", status: "Ready", statusVariant: "success" as const, gradient: "from-indigo-950 via-slate-900 to-cyan-900", icon: BrainCircuit },
  { title: "Product architecture review", duration: "58:42", date: "Yesterday, 4:12 PM", status: "Processing", statusVariant: "warning" as const, gradient: "from-slate-900 via-violet-950 to-indigo-900", icon: Database },
  { title: "Design systems workshop", duration: "1:12:06", date: "Jul 21, 2026", status: "Ready", statusVariant: "success" as const, gradient: "from-cyan-950 via-slate-900 to-indigo-950", icon: Zap },
  { title: "Q2 customer research interviews", duration: "36:27", date: "Jul 19, 2026", status: "Ready", statusVariant: "success" as const, gradient: "from-amber-950 via-slate-900 to-rose-950", icon: MessageSquareText },
];
export const processingJobs = [
  { title: "Product architecture review", stage: "Building semantic chunks", progress: 72, progressClass: "w-[72%]", eta: "About 4 minutes left", status: "Active" },
  { title: "Quarterly planning session", stage: "Transcribing speech", progress: 34, progressClass: "w-[34%]", eta: "About 11 minutes left", status: "Active" },
  { title: "Field interview — north site", stage: "Queued for processing", progress: 8, progressClass: "w-[8%]", eta: "Starts in about 2 minutes", status: "Queued" },
];
export const recentActivity = [
  { title: "AI question answered", detail: "“Where did the speaker compare MCP with HTTP?”", time: "12 minutes ago", icon: MessageSquareText, tone: "violet" },
  { title: "OCR completed", detail: "MCP vs HTTP — technical deep dive", time: "28 minutes ago", icon: ScanText, tone: "cyan" },
  { title: "Transcript generated", detail: "Product architecture review", time: "Yesterday at 4:34 PM", icon: FileCheck2, tone: "emerald" },
  { title: "Processing started", detail: "Quarterly planning session", time: "Yesterday at 2:18 PM", icon: Play, tone: "amber" },
  { title: "Upload completed", detail: "Field interview — north site", time: "Yesterday at 2:16 PM", icon: UploadCloud, tone: "indigo" },
];

