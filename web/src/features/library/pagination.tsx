import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

interface PaginationProps {
  page: number;
  totalItems: number;
  itemsPerPage: number;
  onChange: (page: number) => void;
}

export function Pagination({ page, totalItems, itemsPerPage, onChange }: PaginationProps) {
  const totalPages = Math.ceil(totalItems / itemsPerPage);

  if (totalItems === 0 || totalPages <= 1) {
    return null; // Don't show pagination if there are no items or only one page
  }

  const startItem = (page - 1) * itemsPerPage + 1;
  const endItem = Math.min(page * itemsPerPage, totalItems);

  return (
    <nav
      aria-label="Video library pagination"
      className="flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-border/60 pt-6 mt-6 transition-all duration-normal"
    >
      <p className="text-xs font-medium text-muted-foreground">
        Showing <span className="text-foreground font-semibold">{startItem}</span>–
        <span className="text-foreground font-semibold">{endItem}</span> of{" "}
        <span className="text-foreground font-semibold">{totalItems}</span> videos
      </p>

      <div className="flex items-center gap-1.5">
        {/* Previous Button */}
        <Button
          variant="outline"
          size="sm"
          onClick={() => onChange(Math.max(1, page - 1))}
          disabled={page === 1}
          aria-label="Previous page"
          className="h-9 px-3 gap-1 hover:border-border"
        >
          <ChevronLeft className="h-4 w-4" />
          <span className="hidden sm:inline text-xs font-semibold">Previous</span>
        </Button>

        {/* Page Buttons */}
        <div className="flex items-center gap-1">
          {Array.from({ length: totalPages }, (_, index) => index + 1).map((number) => {
            const isCurrent = number === page;
            return (
              <Button
                key={number}
                variant={isCurrent ? "primary" : "ghost"}
                size="icon"
                onClick={() => onChange(number)}
                aria-current={isCurrent ? "page" : undefined}
                aria-label={`Page ${number}`}
                className={`h-9 w-9 rounded-md text-xs font-semibold transition-all ${
                  isCurrent
                    ? "bg-primary text-primary-foreground shadow-sm shadow-primary/20"
                    : "hover:bg-slate-100 dark:hover:bg-slate-800/80"
                }`}
              >
                {number}
              </Button>
            );
          })}
        </div>

        {/* Next Button */}
        <Button
          variant="outline"
          size="sm"
          onClick={() => onChange(Math.min(totalPages, page + 1))}
          disabled={page === totalPages}
          aria-label="Next page"
          className="h-9 px-3 gap-1 hover:border-border"
        >
          <span className="hidden sm:inline text-xs font-semibold">Next</span>
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </nav>
  );
}
