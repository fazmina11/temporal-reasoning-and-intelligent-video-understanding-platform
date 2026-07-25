import { BarChart3, Cog, LayoutDashboard, ListChecks, UploadCloud, Video, Workflow, type LucideIcon } from "lucide-react";
export interface NavigationItem { label: string; href: string; icon: LucideIcon; exact?: boolean; }
export const dashboardNavigation: NavigationItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard, exact: true },
  { label: "Video Library", href: "/videos", icon: Video },
  { label: "Upload", href: "/videos/new", icon: UploadCloud },
  { label: "Processing Queue", href: "/processing", icon: ListChecks },
  { label: "Workspace", href: "/workspace", icon: Workflow },
  { label: "Analytics", href: "/analytics", icon: BarChart3 },
  { label: "Settings", href: "/settings", icon: Cog },
];
export const navigationLabels: Record<string, string> = Object.fromEntries(dashboardNavigation.map((item) => [item.href, item.label]));
