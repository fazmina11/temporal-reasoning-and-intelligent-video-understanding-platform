import { ArrowUpRight } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
export function FloatingActionButton() { return <Button asChild className="fixed bottom-5 right-5 z-20 rounded-full px-4 shadow-elevated sm:hidden"><Link to="/videos/new" aria-label="Upload a video"><ArrowUpRight className="h-4 w-4" />Upload</Link></Button>; }
