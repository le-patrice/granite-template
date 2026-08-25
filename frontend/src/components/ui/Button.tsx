import React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "default" | "secondary" | "destructive" | "outline" | "ghost" | "link";
  size?: "sm" | "md" | "default" | "lg" | "icon" | "icon-sm";
  isLoading?: boolean;
  loading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  className,
  variant = "primary",
  size = "md",
  isLoading = false,
  loading = false,
  disabled,
  ...props
}) => {
  const isBusy = isLoading || loading;

  const baseStyles =
    "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-all disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg:not([class*='size-'])]:size-4 shrink-0 [&_svg]:shrink-0 outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] aria-invalid:ring-destructive/20 dark:aria-invalid:ring-destructive/40 aria-invalid:border-destructive shadow-xs";

  const variants = {
    primary: "bg-primary text-primary-foreground hover:bg-primary/90 shadow-xs",
    default: "bg-primary text-primary-foreground hover:bg-primary/90 shadow-xs",
    destructive:
      "bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 dark:bg-destructive/60 shadow-xs",
    secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80 shadow-xs",
    outline:
      "border border-input bg-background shadow-xs hover:bg-accent hover:text-accent-foreground text-foreground dark:bg-input/30 dark:border-input dark:hover:bg-input/50",
    ghost: "hover:bg-accent hover:text-accent-foreground text-foreground shadow-none",
    link: "text-primary underline-offset-4 hover:underline shadow-none",
  };

  const sizes = {
    sm: "h-8 rounded-md gap-1.5 px-3 text-xs has-[>svg]:px-2.5",
    md: "h-9 px-4 py-2 text-sm gap-2 has-[>svg]:px-3",
    default: "h-9 px-4 py-2 text-sm gap-2 has-[>svg]:px-3",
    lg: "h-10 rounded-md px-6 has-[>svg]:px-4 text-base gap-2.5",
    icon: "size-9 p-0",
    "icon-sm": "size-8 p-0",
  };

  return (
    <button
      className={cn(baseStyles, variants[variant], sizes[size], className)}
      disabled={disabled || isBusy}
      {...props}
    >
      {isBusy && <Loader2 className="mr-2 h-4 w-4 animate-spin shrink-0" />}
      {children}
    </button>
  );
};

export const LoadingButton = Button;
export default Button;
