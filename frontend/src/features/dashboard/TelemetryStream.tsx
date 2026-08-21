import React, { useState } from "react";
import { Radio, Zap, Check, AlertCircle } from "lucide-react";
import { Card, CardTitle, CardDescription } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { apiV1TelemetryIngestIngest } from "@/client/sdk.gen";

export const TelemetryStream: React.FC = () => {
  const [isIngesting, setIsIngesting] = useState<boolean>(false);
  const [ingestStatus, setIngestStatus] = useState<string | null>(null);
  const [isError, setIsError] = useState<boolean>(false);

  const handleSimulateBatch = async () => {
    setIsIngesting(true);
    setIngestStatus(null);
    setIsError(false);

    const now = Math.floor(Date.now() / 1000);
    const mockBatch = [
      {
        transformer_id: "TX-ALPHA-01",
        voltage_v: Number((230 + (Math.random() * 10 - 5)).toFixed(2)),
        current_a: Number((45 + (Math.random() * 8 - 4)).toFixed(2)),
        power_factor: Number((0.95 + Math.random() * 0.04).toFixed(3)),
        frequency_hz: Number((50 + (Math.random() * 0.4 - 0.2)).toFixed(2)),
        timestamp_epoch: now,
      },
      {
        transformer_id: "TX-BETA-02",
        voltage_v: Number((228 + (Math.random() * 8 - 4)).toFixed(2)),
        current_a: Number((60 + (Math.random() * 12 - 6)).toFixed(2)),
        power_factor: Number((0.92 + Math.random() * 0.05).toFixed(3)),
        frequency_hz: Number((49.9 + (Math.random() * 0.3 - 0.15)).toFixed(2)),
        timestamp_epoch: now,
      },
    ];

    try {
      const res = await apiV1TelemetryIngestIngest({
        body: mockBatch,
      });

      if (res.response?.ok) {
        setIngestStatus(`Successfully bulk-inserted ${mockBatch.length} readings into TimescaleDB hypertable.`);
      } else {
        setIsError(true);
        setIngestStatus(`Ingest failed with status ${res.response?.status ?? "unknown"}`);
      }
    } catch (err: unknown) {
      setIsError(true);
      setIngestStatus(err instanceof Error ? err.message : "Error streaming telemetry");
    } finally {
      setIsIngesting(false);
    }
  };

  return (
    <Card className="h-full flex flex-col justify-between">
      <div>
        <div className="flex items-center justify-between pb-4 border-b border-border">
          <div>
            <CardTitle>TimescaleDB Telemetry Stream</CardTitle>
            <CardDescription>High-throughput time-series sensor ingestion pipeline</CardDescription>
          </div>
          <div className="rounded-lg bg-primary/10 p-2 text-primary">
            <Radio className="h-4 w-4" />
          </div>
        </div>

        <p className="mt-4 text-xs text-muted-foreground leading-relaxed">
          Simulate a high-frequency sensor reading dispatch into the TimescaleDB hypertable with Valkey
          caching for real-time retrieval of latest readings.
        </p>

        {ingestStatus && (
          <div
            className={`mt-4 flex items-center gap-2 rounded-lg p-3 text-xs border ${
              isError
                ? "bg-destructive/10 border-destructive/20 text-destructive"
                : "bg-emerald-500/10 border-emerald-500/20 text-emerald-600 dark:text-emerald-400"
            }`}
          >
            {isError ? <AlertCircle className="h-4 w-4 shrink-0" /> : <Check className="h-4 w-4 shrink-0" />}
            <span>{ingestStatus}</span>
          </div>
        )}
      </div>

      <div className="mt-6 pt-4 border-t border-border flex items-center justify-between">
        <span className="text-[11px] text-muted-foreground font-mono">Hypertable: telemetry_readings</span>
        <Button
          size="sm"
          onClick={handleSimulateBatch}
          isLoading={isIngesting}
          className="gap-2 text-xs"
        >
          <Zap className="h-3.5 w-3.5" />
          Dispatch Ingest Batch
        </Button>
      </div>
    </Card>
  );
};
