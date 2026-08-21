import React from "react";
import { Appearance } from "@/components/common/Appearance";
import { Logo } from "@/components/common/Logo";
import { Footer } from "@/components/common/Footer";

interface AuthLayoutProps {
  children: React.ReactNode;
}

export const AuthLayout: React.FC<AuthLayoutProps> = ({ children }) => {
  return (
    <div className="grid min-h-screen lg:grid-cols-2 bg-background text-foreground">
      {/* Left Branding Panel */}
      <div className="bg-muted dark:bg-zinc-900/80 border-r border-border hidden lg:flex lg:flex-col lg:items-center lg:justify-center p-12 relative overflow-hidden">
        <div className="flex flex-col items-center gap-6 max-w-sm text-center">
          <Logo variant="full" className="h-16 w-auto" />
          <div className="space-y-2">
            <h2 className="text-xl font-bold tracking-tight">Enterprise Platform</h2>
            <p className="text-sm text-muted-foreground">
              Ultra high-performance ASGI backend with role-based access governance and TimescaleDB analytics.
            </p>
          </div>
        </div>
      </div>

      {/* Right Form Area */}
      <div className="flex flex-col min-h-screen justify-between p-6 md:p-10">
        <div className="flex justify-end">
          <Appearance />
        </div>

        <div className="flex flex-1 items-center justify-center my-8">
          <div className="w-full max-w-sm">{children}</div>
        </div>

        <Footer />
      </div>
    </div>
  );
};
