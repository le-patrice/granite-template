import React from "react";
import { Activity, Users, Zap, Database } from "lucide-react";
import { Card } from "@/components/ui/Card";

interface MetricsProps {
  userCount?: number;
  apiStatus?: string;
  isReady?: boolean;
}

export const MetricsOverviewCards: React.FC<MetricsProps> = ({
  userCount = 0,
  apiStatus = "ONLINE",
  isReady = true,
}) => {
  const cards = [
    {
      title: "API Status",
      value: apiStatus,
      subtitle: "Litestar ASGI Engine",
      icon: <Activity className="h-5 w-5 text-emerald-500" />,
      badge: "Healthy",
      badgeColor: "text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
    },
    {
      title: "Database Cluster",
      value: isReady ? "PostgreSQL 16" : "Degraded",
      subtitle: "TimescaleDB + PgBouncer",
      icon: <Database className="h-5 w-5 text-primary" />,
      badge: "Connected",
      badgeColor: "text-primary bg-primary/10 border-primary/20",
    },
    {
      title: "Registered Users",
      value: String(userCount),
      subtitle: "Platform Accounts",
      icon: <Users className="h-5 w-5 text-blue-500" />,
      badge: "RBAC Guarded",
      badgeColor: "text-blue-600 dark:text-blue-400 bg-blue-500/10 border-blue-500/20",
    },
    {
      title: "Async Task Worker",
      value: "SAQ + Valkey",
      subtitle: "Distributed Queues",
      icon: <Zap className="h-5 w-5 text-amber-500" />,
      badge: "Active",
      badgeColor: "text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {cards.map((card, i) => (
        <Card key={i} className="flex flex-col justify-between hover:border-primary/40 transition-colors">
          <div className="flex items-center justify-between pb-2">
            <span className="text-xs font-medium text-muted-foreground">{card.title}</span>
            <div className="rounded-lg bg-accent p-2">{card.icon}</div>
          </div>
          <div className="space-y-1">
            <div className="text-xl font-bold tracking-tight text-card-foreground">{card.value}</div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{card.subtitle}</span>
              <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${card.badgeColor}`}>
                {card.badge}
              </span>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
};
