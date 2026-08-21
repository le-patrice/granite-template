import React, { useState, useRef, useEffect } from "react";
import {
  Home,
  Users,
  Radio,
  Settings,
  LogOut,
  ChevronsUpDown,
  FileCode2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuth } from "@/hooks/useAuth";
import { Logo } from "@/components/common/Logo";
import { Appearance } from "@/components/common/Appearance";

export type NavItem = "dashboard" | "users" | "telemetry" | "settings";

interface SidebarProps {
  currentTab: NavItem;
  onSelectTab: (tab: NavItem) => void;
  isOpen: boolean;
  onToggle: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  isOpen,
}) => {
  const { user, isAdmin, logout } = useAuth();
  const [userMenuOpen, setUserMenuOpen] = useState<boolean>(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    if (userMenuOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [userMenuOpen]);

  const navItems: { id: NavItem; label: string; icon: React.ReactNode; adminOnly?: boolean }[] = [
    { id: "dashboard", label: "Dashboard", icon: <Home className="h-4 w-4" /> },
    { id: "telemetry", label: "Items & Telemetry", icon: <Radio className="h-4 w-4" /> },
    { id: "users", label: "Admin", icon: <Users className="h-4 w-4" />, adminOnly: true },
    { id: "settings", label: "User Settings", icon: <Settings className="h-4 w-4" /> },
  ];

  const getInitials = (name: string) => {
    return name
      .split(" ")
      .map((part) => part[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  return (
    <aside
      className={cn(
        "fixed inset-y-0 left-0 z-40 flex flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-all duration-200",
        isOpen ? "w-64" : "w-20"
      )}
    >
      {/* Brand Header */}
      <div className="flex h-16 items-center justify-between px-6 border-b border-sidebar-border">
        <Logo variant={isOpen ? "full" : "icon"} className="h-6 w-auto" />
      </div>

      {/* Navigation Menu */}
      <div className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        {navItems.map((item) => {
          if (item.adminOnly && !isAdmin) return null;
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground font-semibold"
                  : "text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground"
              )}
            >
              <span className={cn(isActive ? "text-primary" : "text-muted-foreground")}>
                {item.icon}
              </span>
              {isOpen && <span>{item.label}</span>}
            </button>
          );
        })}

        {/* OpenAPI Link */}
        <div className="pt-4 mt-4 border-t border-sidebar-border">
          <a
            href="/docs"
            target="_blank"
            rel="noreferrer"
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-sidebar-accent hover:text-sidebar-foreground transition-colors"
          >
            <FileCode2 className="h-4 w-4" />
            {isOpen && <span>API Docs (Scalar/Swagger)</span>}
          </a>
        </div>
      </div>

      {/* Sidebar Footer */}
      <div className="border-t border-sidebar-border p-3 space-y-2">
        <div className="flex items-center justify-between px-1">
          {isOpen && <span className="text-xs text-muted-foreground">Theme</span>}
          <Appearance />
        </div>

        {/* User Account Menu */}
        <div className="relative" ref={userMenuRef}>
          <button
            onClick={() => setUserMenuOpen((prev) => !prev)}
            className="flex w-full items-center justify-between rounded-lg p-2 hover:bg-sidebar-accent text-sidebar-foreground transition-colors text-left"
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary text-xs font-semibold">
                {getInitials(user?.full_name || user?.email || "User")}
              </div>
              {isOpen && (
                <div className="flex flex-col truncate min-w-0">
                  <span className="text-xs font-medium truncate">
                    {user?.full_name || "User"}
                  </span>
                  <span className="text-[10px] text-muted-foreground truncate">
                    {user?.email}
                  </span>
                </div>
              )}
            </div>
            {isOpen && <ChevronsUpDown className="h-4 w-4 text-muted-foreground shrink-0" />}
          </button>

          {userMenuOpen && (
            <div className="absolute bottom-full left-0 mb-2 w-full rounded-lg border border-border bg-popover p-1 shadow-xl z-50">
              <button
                onClick={() => {
                  setUserMenuOpen(false);
                  onSelectTab("settings");
                }}
                className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-xs text-popover-foreground hover:bg-accent transition-colors text-left"
              >
                <Settings className="h-3.5 w-3.5" />
                User Settings
              </button>
              <div className="my-1 border-t border-border" />
              <button
                onClick={() => {
                  setUserMenuOpen(false);
                  logout();
                }}
                className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-xs text-destructive hover:bg-destructive/10 transition-colors text-left"
              >
                <LogOut className="h-3.5 w-3.5" />
                Log Out
              </button>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
};
