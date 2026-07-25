import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { AppProviders } from "@/providers/app-providers";
import { AppRouter } from "@/router";
import "@/styles/index.css";
createRoot(document.getElementById("root")!).render(<AppProviders><BrowserRouter><AppRouter /></BrowserRouter></AppProviders>);
