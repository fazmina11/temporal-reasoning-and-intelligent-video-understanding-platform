import { ArrowRight, Clock3, MoreHorizontal, UploadCloud } from "lucide-react";
import { Link } from "react-router-dom";
import {
  mapVideosToActivity,
  mapVideosToDashboardStats,
  mapVideosToProcessingJobs
} from "@/api/adapters";
import { PageHeader, SectionHeader } from "@/components/global/headers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAnalytics, useVideos } from "@/hooks/api/use-videos";
import { cn } from "@/lib/utils";

const iconTone = {
  indigo: "bg-indigo-500/10 text-indigo-600",
  emerald: "bg-emerald-500/10 text-emerald-600",
  amber: "bg-amber-500/10 text-amber-600",
  violet: "bg-violet-500/10 text-violet-600",
  cyan: "bg-cyan-500/10 text-cyan-600"
};

function formatBytes(value: number) {
  if (value <= 0) return "0 MB";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(value) / Math.log(1024)));
  return `${(value / 1024 ** index).toFixed(index >= 3 ? 1 : 0)} ${units[index]}`;
}

export function DashboardOverview() {
  const { data: videosResponse, isLoading } = useVideos();
  const { data: analytics } = useAnalytics();
  const videos = videosResponse?.videos ?? [];
  const stats = mapVideosToDashboardStats(videos).map((stat) => {
    if (stat.label === "AI questions asked" && analytics) {
      return { ...stat, value: analytics.questions_asked, display: String(analytics.questions_asked) };
    }
    if (stat.label === "Storage used" && analytics) {
      return { ...stat, value: analytics.total_storage_bytes, display: formatBytes(analytics.total_storage_bytes) };
    }
    return stat;
  });
  const jobs = mapVideosToProcessingJobs(videos);
  const activity = mapVideosToActivity(videos);

  return (
    <div className="mx-auto max-w-[1600px] space-y-8">
      <PageHeader
        eyebrow="Video intelligence workspace"
        title="Processing and evidence overview"
        description="Live status derived from persisted manifests, processing jobs, and retrieval traces."
        actions={<Button asChild><Link to="/videos/new"><UploadCloud className="h-4 w-4" />Upload video</Link></Button>}
      />

      <section aria-label="Workspace statistics" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {stats.map((stat) => {
          const Icon = stat.icon;
          return (
            <Card key={stat.label} className="p-5">
              <span className={cn("grid h-10 w-10 place-items-center rounded-md", iconTone[stat.tone])}>
                <Icon className="h-4 w-4" />
              </span>
              <p className="mt-5 text-2xl font-semibold tabular-nums">{stat.display}</p>
              <h2 className="mt-1 text-xs font-medium text-muted-foreground">{stat.label}</h2>
              <p className="mt-3 text-[11px] text-muted-foreground">{stat.subtitle}</p>
            </Card>
          );
        })}
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <section>
          <div className="mb-4">
            <SectionHeader
              title="Recent videos"
              description="Manifest-backed sources and their current readiness."
              action={<Button variant="ghost" size="sm" asChild><Link to="/videos">View library <ArrowRight className="h-3.5 w-3.5" /></Link></Button>}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            {videos.slice(0, 4).map((video) => {
              const Icon = video.icon;
              return (
                <Link key={video.id} to={`/videos/${video.id}`} className="focus-ring rounded-xl">
                  <Card className="h-full p-4 transition hover:-translate-y-0.5 hover:shadow-elevated">
                    <div className={cn("grid aspect-video place-items-center rounded-md bg-gradient-to-br", video.gradient)}>
                      <Icon className="h-8 w-8 text-white/80" />
                    </div>
                    <div className="mt-3 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="truncate text-sm font-semibold">{video.title}</h3>
                        <p className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
                          <Clock3 className="h-3 w-3" />{video.duration}
                        </p>
                      </div>
                      <Badge variant={video.status === "Failed" ? "destructive" : video.status === "Processing" ? "warning" : "success"}>
                        {video.status}
                      </Badge>
                    </div>
                  </Card>
                </Link>
              );
            })}
            {!isLoading && videos.length === 0 && (
              <Card className="col-span-full p-8 text-center text-sm text-muted-foreground">
                No manifests are available yet.
              </Card>
            )}
          </div>
        </section>

        <section>
          <div className="mb-4">
            <SectionHeader title="Processing queue" description="Current backend phase and progress." />
          </div>
          <Card className="space-y-3 p-3">
            {jobs.map((job) => (
              <div key={job.title} className="rounded-md border p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-semibold">{job.title}</h3>
                    <p className="mt-1 text-xs text-muted-foreground">{job.stage}</p>
                  </div>
                  <Badge variant="warning">{job.status}</Badge>
                </div>
                <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${job.progress}%` }} />
                </div>
              </div>
            ))}
            {jobs.length === 0 && <p className="p-5 text-center text-sm text-muted-foreground">No active processing jobs.</p>}
          </Card>
        </section>
      </div>

      <section>
        <div className="mb-4"><SectionHeader title="Recent backend activity" description="Derived from the current manifest collection." /></div>
        <Card className="divide-y">
          {activity.map((item) => {
            const Icon = item.icon;
            return (
              <div key={item.title} className="flex items-center gap-3 p-4">
                <span className="grid h-8 w-8 place-items-center rounded-md border"><Icon className="h-3.5 w-3.5" /></span>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-semibold">{item.title}</p>
                  <p className="truncate text-xs text-muted-foreground">{item.detail}</p>
                </div>
                <MoreHorizontal className="h-4 w-4 text-muted-foreground" />
              </div>
            );
          })}
        </Card>
      </section>
    </div>
  );
}
