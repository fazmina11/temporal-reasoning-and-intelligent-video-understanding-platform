import { PropsWithChildren } from "react";
import { Outlet } from "react-router-dom";
import { DashboardShell } from "@/components/shell/dashboard-shell";
export function PublicLayout({ children }: PropsWithChildren) { return <div className="min-h-screen">{children || <Outlet />}</div>; }
export function DashboardLayout() { return <DashboardShell />; }
export function WorkspaceLayout() { return <DashboardShell />; }
