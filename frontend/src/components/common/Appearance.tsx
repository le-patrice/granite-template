import React, { useState, useRef, useEffect } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "@/hooks/useTheme";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

interface AppearanceProps {
  className?: string;
  side?: "bottom" | "top" | "right" | "left";
  align?: "start" | "end" | "center";
}

export const Appearance: React.FC<AppearanceProps> = ({
  className,
  side = "bottom",
  align = "end",
}) => {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [open]);

  // Positioning classes based on side
  const positionClasses = {
    bottom: "top-full mt-2 right-0",
    top: "bottom-full mb-2 right-0",
    right: "left-full bottom-0 ml-2",
    left: "right-full bottom-0 mr-2",
  };

  return (
    <div className={cn("relative inline-block", className)} ref={dropdownRef}>
      <Button
        variant="outline"
        size="sm"
        onClick={() => setOpen((prev) => !prev)}
        className="h-9 w-9 p-0"
        title="Toggle theme"
        aria-label="Toggle theme"
      >
        <Sun className="h-4 w-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0 text-amber-500" />
        <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100 text-blue-400" />
        <span className="sr-only">Toggle theme</span>
      </Button>

      {open && (
        <div
          className={cn(
            "absolute z-50 min-w-36 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-xl backdrop-blur-sm animate-in fade-in-0 zoom-in-95 duration-100",
            positionClasses[side]
          )}
        >
          <button
            type="button"
            onClick={() => {
              setTheme("light");
              setOpen(false);
            }}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-md px-3 py-1.5 text-xs transition-colors text-left",
              theme === "light"
                ? "bg-accent text-accent-foreground font-medium"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            <Sun className="h-3.5 w-3.5 text-amber-500" />
            Light
          </button>

          <button
            type="button"
            onClick={() => {
              setTheme("dark");
              setOpen(false);
            }}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-md px-3 py-1.5 text-xs transition-colors text-left",
              theme === "dark"
                ? "bg-accent text-accent-foreground font-medium"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            <Moon className="h-3.5 w-3.5 text-blue-400" />
            Dark
          </button>
        </div>
      )}
    </div>
  );
};

export const SidebarAppearance: React.FC<{ isOpen?: boolean }> = ({ isOpen = true }) => {
  const { theme, setTheme } = useTheme();
  const [open, setOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [open]);

  return (
    <div className="relative w-full" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className={cn(
          "flex w-full items-center gap-3 rounded-lg p-2 text-sm font-medium text-sidebar-foreground transition-colors hover:bg-sidebar-accent",
          !isOpen && "justify-center px-0"
        )}
        title="Appearance"
        aria-label="Appearance settings"
      >
        {theme === "dark" ? (
          <Moon className="h-4 w-4 text-blue-400 shrink-0" />
        ) : (
          <Sun className="h-4 w-4 text-amber-500 shrink-0" />
        )}
        {isOpen && <span className="text-xs">Appearance</span>}
      </button>

      {open && (
        <div
          className={cn(
            "absolute z-50 min-w-44 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-xl backdrop-blur-sm animate-in fade-in-0 zoom-in-95 duration-100",
            isOpen ? "bottom-full left-0 mb-2 w-full" : "left-full bottom-0 ml-2"
          )}
        >
          <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground border-b border-border mb-1">
            Theme
          </div>

          <button
            type="button"
            onClick={() => {
              setTheme("light");
              setOpen(false);
            }}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-md px-3 py-1.5 text-xs transition-colors text-left",
              theme === "light"
                ? "bg-accent text-accent-foreground font-medium"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            <Sun className="h-3.5 w-3.5 text-amber-500" />
            Light
          </button>

          <button
            type="button"
            onClick={() => {
              setTheme("dark");
              setOpen(false);
            }}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-md px-3 py-1.5 text-xs transition-colors text-left",
              theme === "dark"
                ? "bg-accent text-accent-foreground font-medium"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            )}
          >
            <Moon className="h-3.5 w-3.5 text-blue-400" />
            Dark
          </button>
        </div>
      )}
    </div>
  );
};

export default Appearance;
