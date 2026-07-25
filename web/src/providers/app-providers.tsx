import { PropsWithChildren } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "sonner";
import { queryClient } from "./query-client";
import { ThemeProvider } from "./theme-provider";
export function AppProviders({ children }: PropsWithChildren) { return <QueryClientProvider client={queryClient}><ThemeProvider><Toaster position="bottom-right" richColors closeButton />{children}</ThemeProvider></QueryClientProvider>; }
