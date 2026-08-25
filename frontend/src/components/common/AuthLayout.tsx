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
      <div className="bg-muted dark:bg-zinc-900 relative hidden lg:flex lg:items-center lg:justify-center border-r border-border">
        <Logo variant="full" className="h-16 w-auto" asLink={false} />
      </div>

      {/* Right Form Area */}
      <div className="flex flex-col justify-between p-6 md:p-10 min-h-screen">
        <div className="flex justify-end">
          <Appearance />
        </div>

        <div className="flex flex-1 items-center justify-center py-8">
          <div className="w-full max-w-sm">{children}</div>
        </div>

        <Footer />
      </div>
    </div>
  );
};

export default AuthLayout;
