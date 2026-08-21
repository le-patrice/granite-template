import React, { useState } from "react";
import { AuthProvider, useAuth } from "@/hooks/useAuth";
import { ThemeProvider } from "@/hooks/useTheme";
import { AppShell } from "@/components/layout/AppShell";
import type { NavItem } from "@/components/layout/Sidebar";
import { LoginPage } from "@/pages/LoginPage";
import { DashboardPage } from "@/pages/DashboardPage";
import { UsersPage } from "@/pages/UsersPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { TelemetryStream } from "@/features/dashboard/TelemetryStream";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
import { ErrorBoundary } from "@/components/common/ErrorBoundary";

const AuthenticatedApp: React.FC = () => {
  const { isAuthenticated, isLoading, refreshProfile } = useAuth();
  const [currentTab, setCurrentTab] = useState<NavItem>("dashboard");
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-950">
        <LoadingSpinner label="Authenticating platform session..." />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  const handleRefreshAll = async () => {
    setIsRefreshing(true);
    try {
      await refreshProfile();
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <AppShell
      currentTab={currentTab}
      onSelectTab={setCurrentTab}
      onRefreshAll={handleRefreshAll}
      isRefreshing={isRefreshing}
    >
      {currentTab === "dashboard" && <DashboardPage />}
      {currentTab === "users" && <UsersPage />}
      {currentTab === "telemetry" && (
        <div className="space-y-6 max-w-4xl">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-100">Telemetry & TimescaleDB</h1>
            <p className="text-xs text-slate-400 mt-1">
              Time-series hypertables with hyper-scale compression and automated retention policies.
            </p>
          </div>
          <TelemetryStream />
        </div>
      )}
      {currentTab === "settings" && <SettingsPage />}
    </AppShell>
  );
};

export default function App() {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <AuthProvider>
          <AuthenticatedApp />
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}
