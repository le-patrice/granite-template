import React, { useEffect, useState } from "react";
import { CheckCircle2, AlertCircle, RefreshCw } from "lucide-react";
import { Card, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { healthGetHealth, healthReadyGetReadiness, healthStartupGetStartup } from "@/client/sdk.gen";

interface SubsystemHealth {
  name: string;
  status: "healthy" | "unhealthy" | "loading";
  latencyMs?: number;
  details?: string;
}

export const SystemHealthCard: React.FC = () => {
  const [healths, setHealths] = useState<SubsystemHealth[]>([
    { name: "Litestar ASGI API", status: "loading" },
    { name: "PostgreSQL & TimescaleDB", status: "loading" },
    { name: "Valkey In-Memory Cache", status: "loading" },
    { name: "Alembic Migrations", status: "loading" },
  ]);
  const [isChecking, setIsChecking] = useState<boolean>(false);

  const checkHealth = async () => {
    setIsChecking(true);
    const updated: SubsystemHealth[] = [];

    // 1. Basic Health
    const start1 = performance.now();
    try {
      const res = await healthGetHealth();
      const lat = Math.round(performance.now() - start1);
      const isOk = !!res.response?.ok;
      updated.push({
        name: "Litestar ASGI API",
        status: isOk ? "healthy" : "unhealthy",
        latencyMs: lat,
        details: isOk ? "HTTP 200 OK (Basic)" : "Status Degraded",
      });
    } catch {
      updated.push({ name: "Litestar ASGI API", status: "unhealthy", details: "Unreachable" });
    }

    // 2. Readiness Probe (DB & Valkey)
    const start2 = performance.now();
    try {
      const res = await healthReadyGetReadiness();
      const lat = Math.round(performance.now() - start2);
      const isOk = !!res.response?.ok;
      updated.push({
        name: "PostgreSQL & TimescaleDB",
        status: isOk ? "healthy" : "unhealthy",
        latencyMs: lat,
        details: isOk ? "Connection Verified" : "DB Failed",
      });
      updated.push({
        name: "Valkey In-Memory Cache",
        status: isOk ? "healthy" : "unhealthy",
        latencyMs: lat,
        details: isOk ? "Ping 6379 OK" : "Cache Failed",
      });
    } catch {
      updated.push({ name: "PostgreSQL & TimescaleDB", status: "unhealthy", details: "Failed" });
      updated.push({ name: "Valkey In-Memory Cache", status: "unhealthy", details: "Failed" });
    }

    // 3. Startup Migrations Check
    try {
      const res = await healthStartupGetStartup();
      const isOk = !!res.response?.ok;
      updated.push({
        name: "Alembic Migrations",
        status: isOk ? "healthy" : "unhealthy",
        details: isOk ? "Schema Head Verified" : "Pending Migrations",
      });
    } catch {
      updated.push({ name: "Alembic Migrations", status: "unhealthy", details: "Check Failed" });
    }

    setHealths(updated);
    setIsChecking(false);
  };

  useEffect(() => {
    checkHealth();
  }, []);

  return (
    <Card className="h-full flex flex-col justify-between">
      <div>
        <div className="flex items-center justify-between pb-4 border-b border-border">
          <div>
            <CardTitle>System & Subsystem Health</CardTitle>
            <CardDescription>Live Kubernetes probes & dependency status</CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={checkHealth}
            disabled={isChecking}
            className="gap-1.5 text-xs"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isChecking ? "animate-spin text-primary" : ""}`} />
            Run Probe
          </Button>
        </div>

        <div className="mt-4 space-y-3">
          {healths.map((sub, idx) => (
            <div
              key={idx}
              className="flex items-center justify-between rounded-lg bg-accent/40 p-3 border border-border"
            >
              <div className="flex items-center gap-3">
                {sub.status === "healthy" ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
                ) : sub.status === "loading" ? (
                  <RefreshCw className="h-4 w-4 text-muted-foreground animate-spin shrink-0" />
                ) : (
                  <AlertCircle className="h-4 w-4 text-destructive shrink-0" />
                )}
                <div>
                  <div className="text-xs font-medium text-foreground">{sub.name}</div>
                  <div className="text-[10px] text-muted-foreground">{sub.details || "Operational"}</div>
                </div>
              </div>

              {sub.latencyMs !== undefined && (
                <span className="text-[11px] font-mono text-muted-foreground">{sub.latencyMs} ms</span>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="mt-6 rounded-lg bg-primary/10 border border-primary/20 p-3 text-[11px] text-primary">
        All probes adhere to Kubernetes Standard Spec (`/health/live`, `/health/ready`, `/health/startup`).
      </div>
    </Card>
  );
};
