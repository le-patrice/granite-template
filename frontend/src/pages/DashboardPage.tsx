import React, { useEffect, useState } from "react";
import { MetricsOverviewCards } from "@/features/dashboard/MetricsOverviewCards";
import { SystemHealthCard } from "@/features/dashboard/SystemHealthCard";
import { TelemetryStream } from "@/features/dashboard/TelemetryStream";
import { apiV1UsersListUsers, healthGetHealth } from "@/client/sdk.gen";
import { useAuth } from "@/hooks/useAuth";

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();
  const [userCount, setUserCount] = useState<number>(1);
  const [apiStatus, setApiStatus] = useState<string>("ONLINE");

  const loadDashboardData = async () => {
    try {
      const healthRes = await healthGetHealth();
      if (healthRes.response?.ok) {
        setApiStatus("ONLINE");
      } else {
        setApiStatus("DEGRADED");
      }
    } catch {
      setApiStatus("OFFLINE");
    }

    if (user?.is_superuser) {
      try {
        const usersRes = await apiV1UsersListUsers({ query: { skip: 0, limit: 100 } });
        if (usersRes.data?.count !== undefined) {
          setUserCount(usersRes.data.count);
        } else if (Array.isArray(usersRes.data)) {
          setUserCount(usersRes.data.length);
        }
      } catch {
        // non-critical
      }
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, [user]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground truncate max-w-lg">
          Hi, {user?.full_name || user?.email} 👋
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          Welcome back, nice to see you again!
        </p>
      </div>

      <MetricsOverviewCards userCount={userCount} apiStatus={apiStatus} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SystemHealthCard />
        <TelemetryStream />
      </div>
    </div>
  );
};

export default DashboardPage;
