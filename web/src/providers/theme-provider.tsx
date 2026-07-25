import { createContext, useContext, useEffect, useMemo, useState, type PropsWithChildren } from "react";
import type { Theme } from "@/types";
interface ThemeContextValue { theme: Theme; setTheme: (theme: Theme) => void; toggleTheme: () => void; }
const ThemeContext = createContext<ThemeContextValue | null>(null);
export function ThemeProvider({ children }: PropsWithChildren) { const [theme, setThemeState] = useState<Theme>(() => { const saved = localStorage.getItem("videoscenerag-theme"); return saved === "dark" ? "dark" : "light"; }); const setTheme = (next: Theme) => { setThemeState(next); localStorage.setItem("videoscenerag-theme", next); }; useEffect(() => { document.documentElement.classList.toggle("dark", theme === "dark"); document.documentElement.style.colorScheme = theme; }, [theme]); const value = useMemo(() => ({ theme, setTheme, toggleTheme: () => setTheme(theme === "dark" ? "light" : "dark") }), [theme]); return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>; }
export function useTheme() { const context = useContext(ThemeContext); if (!context) throw new Error("useTheme must be used within ThemeProvider"); return context; }
