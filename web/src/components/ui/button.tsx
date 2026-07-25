import { forwardRef, type ButtonHTMLAttributes } from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
const buttonVariants = cva("focus-ring inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors duration-fast disabled:pointer-events-none disabled:opacity-50", { variants: { variant: { primary: "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90", secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80", outline: "border bg-background hover:bg-muted", ghost: "hover:bg-muted hover:text-foreground", destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90" }, size: { sm: "h-8 px-3", md: "h-10 px-4 py-2", lg: "h-11 px-6", icon: "h-10 w-10" } }, defaultVariants: { variant: "primary", size: "md" } });
export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> { asChild?: boolean; }
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, asChild = false, ...props }, ref) => { const Comp = asChild ? Slot : "button"; return <Comp ref={ref} className={cn(buttonVariants({ variant, size, className }))} {...props} />; });
Button.displayName = "Button";
export { buttonVariants };
