import React, { useState } from "react";
import { Sidebar, type NavItem } from "@/components/layout/Sidebar";
import { TopNavbar } from "@/components/layout/TopNavbar";
import { Footer } from "@/components/common/Footer";
import { cn } from "@/lib/utils";

interface AppShellProps {
  currentTab: NavItem;
  onSelectTab: (tab: NavItem) => void;
  children: React.ReactNode;
  onRefreshAll?: () => void;
  isRefreshing?: boolean;
}

export const AppShell: React.FC<AppShellProps> = ({
  currentTab,
  onSelectTab,
  children,
  onRefreshAll,
  isRefreshing,
}) => {
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(true);

  return (
    <div className="min-h-screen bg-background text-foreground flex flex-col">
      <div className="flex flex-1">
        <Sidebar
          currentTab={currentTab}
          onSelectTab={onSelectTab}
          isOpen={sidebarOpen}
          onToggle={() => setSidebarOpen((prev) => !prev)}
        />

        <div
          className={cn(
            "flex flex-1 flex-col transition-all duration-200 min-w-0",
            sidebarOpen ? "pl-64" : "pl-20"
          )}
        >
          <TopNavbar
            onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
            onRefreshAll={onRefreshAll}
            isRefreshing={isRefreshing}
          />
          <main className="flex-1 p-6 md:p-8 overflow-y-auto">{children}</main>
          <Footer />
        </div>
      </div>
    </div>
  );
};
