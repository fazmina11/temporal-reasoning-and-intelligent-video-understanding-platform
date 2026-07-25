import { cn } from "@/lib/utils";
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) { return <div className={cn("animate-pulse rounded-md bg-muted", className)} {...props} />; }
export function Spinner({ className }: { className?: string }) { return <span role="status" aria-label="Loading" className={cn("inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent", className)} />; }
