import React, { useEffect, useState } from "react";
import { Menu, RefreshCw, Activity, Database, CheckCircle2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { healthGetHealth } from "@/client/sdk.gen";

interface TopNavbarProps {
  onToggleSidebar: () => void;
  onRefreshAll?: () => void;
  isRefreshing?: boolean;
}

export const TopNavbar: React.FC<TopNavbarProps> = ({
  onToggleSidebar,
  onRefreshAll,
  isRefreshing = false,
}) => {
  const [isHealthy, setIsHealthy] = useState<boolean | null>(null);

  const checkHealth = async () => {
    try {
      const res = await healthGetHealth();
      setIsHealthy(!!res.response?.ok);
    } catch {
      setIsHealthy(false);
    }
  };

  useEffect(() => {
    checkHealth();
    const interval = setInterval(checkHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-border bg-background/95 px-6 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={onToggleSidebar}
          className="h-9 w-9 p-0 text-muted-foreground hover:text-foreground"
          title="Toggle Sidebar"
        >
          <Menu className="h-5 w-5" />
        </Button>
      </div>

      <div className="flex items-center gap-4">
        {/* Cluster Health Indicator */}
        <div className="hidden sm:flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-xs">
          {isHealthy === true ? (
            <>
              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-muted-foreground font-medium">Cluster Healthy</span>
            </>
          ) : isHealthy === false ? (
            <>
              <span className="h-2 w-2 rounded-full bg-destructive" />
              <span className="text-destructive font-medium">Service Degraded</span>
            </>
          ) : (
            <>
              <span className="h-2 w-2 rounded-full bg-muted-foreground" />
              <span className="text-muted-foreground">Checking Probes...</span>
            </>
          )}
        </div>

        {onRefreshAll && (
          <Button
            variant="outline"
            size="sm"
            onClick={onRefreshAll}
            disabled={isRefreshing}
            className="gap-2 text-xs h-9"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isRefreshing ? "animate-spin text-primary" : ""}`} />
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        )}
      </div>
    </header>
  );
};
