import { Link } from "react-router-dom";
import { ArrowLeft, Home, Video, Compass, FileQuestion } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

export function NotFoundPage() {
  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4 animate-fade-in">
      <Card className="max-w-lg w-full p-8 text-center border shadow-elevated bg-card relative overflow-hidden space-y-6">
        {/* Background ambient glow */}
        <div className="absolute -top-12 -right-12 h-40 w-40 rounded-full bg-primary/10 blur-3xl pointer-events-none" />
        <div className="absolute -bottom-12 -left-12 h-40 w-40 rounded-full bg-cyan-500/10 blur-3xl pointer-events-none" />

        <div className="relative mx-auto flex h-20 w-20 items-center justify-center rounded-2xl bg-slate-100 text-primary border shadow-xs dark:bg-slate-900">
          <FileQuestion className="h-10 w-10 text-primary" />
          <span className="absolute -bottom-1 -right-1 font-mono text-[10px] font-bold bg-primary text-primary-foreground px-1.5 py-0.5 rounded-full">
            404
          </span>
        </div>

        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Page Not Found</h1>
          <p className="text-sm text-muted-foreground leading-relaxed max-w-sm mx-auto">
            The page or workspace view you are looking for does not exist or has been moved.
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
          <Button asChild variant="primary" className="w-full sm:w-auto h-10 shadow-sm gap-2">
            <Link to="/dashboard">
              <Home className="h-4 w-4" />
              Go to Dashboard
            </Link>
          </Button>

          <Button asChild variant="outline" className="w-full sm:w-auto h-10 gap-2">
            <Link to="/videos">
              <Video className="h-4 w-4" />
              Browse Video Library
            </Link>
          </Button>
        </div>

        <div className="border-t pt-4 text-[11px] text-muted-foreground flex items-center justify-center gap-1">
          <Compass className="h-3.5 w-3.5" />
          <span>Need help? Check your URL or return to the main workspace.</span>
        </div>
      </Card>
    </div>
  );
}
