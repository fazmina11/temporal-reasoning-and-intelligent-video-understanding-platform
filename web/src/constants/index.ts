export const ROUTES = { root: "/", videos: "/videos", upload: "/videos/new", settings: "/settings", processing: "/videos/:videoId/processing", workspace: "/videos/:videoId", timeline: "/videos/:videoId/timeline", debug: "/videos/:videoId/debug" } as const;
export const MOTION_DURATION = { fast: 0.16, normal: 0.24, slow: 0.4 } as const;
