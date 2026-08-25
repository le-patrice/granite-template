import React from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from "lucide-react";
import { cn } from "@/lib/utils";

export interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "destructive" | "warning" | "success";
  icon?: React.ReactNode;
}

export const Alert: React.FC<AlertProps> = ({
  className,
  variant = "default",
  icon,
  children,
  ...props
}) => {
  const defaultIcons = {
    default: <Info className="h-4 w-4 shrink-0" />,
    destructive: <AlertCircle className="h-4 w-4 shrink-0" />,
    warning: <AlertTriangle className="h-4 w-4 shrink-0" />,
    success: <CheckCircle2 className="h-4 w-4 shrink-0" />,
  };

  const variants = {
    default: "bg-card text-card-foreground border-border",
    destructive:
      "border-destructive/30 bg-destructive/10 text-destructive dark:border-destructive/40 dark:bg-destructive/20 [&_svg]:text-destructive",
    warning:
      "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 dark:border-amber-500/40 dark:bg-amber-500/20 [&_svg]:text-amber-500",
    success:
      "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 dark:border-emerald-500/40 dark:bg-emerald-500/20 [&_svg]:text-emerald-500",
  };

  const renderedIcon = icon !== undefined ? icon : defaultIcons[variant];

  return (
    <div
      role="alert"
      className={cn(
        "relative w-full rounded-lg border p-3.5 text-xs transition-all flex items-start gap-3",
        variants[variant],
        className
      )}
      {...props}
    >
      {renderedIcon}
      <div className="flex-1 min-w-0">{children}</div>
    </div>
  );
};

export const AlertTitle: React.FC<React.HTMLAttributes<HTMLHeadingElement>> = ({
  className,
  children,
  ...props
}) => {
  return (
    <h5
      className={cn("font-semibold leading-tight tracking-tight mb-1 text-inherit", className)}
      {...props}
    >
      {children}
    </h5>
  );
};

export const AlertDescription: React.FC<React.HTMLAttributes<HTMLParagraphElement>> = ({
  className,
  children,
  ...props
}) => {
  return (
    <div className={cn("text-xs leading-relaxed opacity-90", className)} {...props}>
      {children}
    </div>
  );
};

export default Alert;
