import { Routes, Route, Navigate } from "react-router-dom";
import { DashboardLayout, PublicLayout } from "@/layouts/layouts";
import { RoutePlaceholder } from "@/pages/route-placeholder";
import { LandingPage } from "@/pages/landing-page";
import { DashboardOverview } from "@/features/dashboard/dashboard-overview";
import { VideoLibraryPage } from "@/features/library/video-library-page";
import { VideoUploadPage } from "@/features/upload/video-upload-page";
import { VideoProcessingPage } from "@/features/processing/video-processing-page";
import { VideoDetailsPage } from "@/features/details/video-details-page";
import { WorkspacePage } from "@/features/workspace/workspace-page";
import { NotFoundPage } from "@/pages/not-found-page";
export function AppRouter() { return <Routes><Route element={<PublicLayout />}><Route path="/" element={<LandingPage />} /><Route path="/login" element={<RoutePlaceholder name="Login" />} /></Route><Route element={<DashboardLayout />}><Route path="/dashboard" element={<DashboardOverview />} /><Route path="/videos" element={<VideoLibraryPage />} /><Route path="/videos/new" element={<VideoUploadPage />} /><Route path="/processing" element={<RoutePlaceholder name="Processing queue" />} /><Route path="/workspace" element={<WorkspacePage />} /><Route path="/analytics" element={<RoutePlaceholder name="Analytics" />} /><Route path="/settings" element={<RoutePlaceholder name="Settings" />} /><Route path="/videos/:videoId" element={<VideoDetailsPage />} /><Route path="/videos/:videoId/processing" element={<VideoProcessingPage />} /><Route path="/videos/:videoId/timeline" element={<WorkspacePage />} /><Route path="/videos/:videoId/debug" element={<RoutePlaceholder name="Debug" />} /></Route><Route path="*" element={<NotFoundPage />} /></Routes>; }


