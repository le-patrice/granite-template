import React from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export const LoadingSpinner: React.FC<{ className?: string; label?: string }> = ({
  className,
  label = "Loading...",
}) => {
  return (
    <div className={cn("flex flex-col items-center justify-center p-8 text-slate-400", className)}>
      <Loader2 className="h-8 w-8 animate-spin text-blue-500 mb-2" />
      <span className="text-xs">{label}</span>
    </div>
  );
};
