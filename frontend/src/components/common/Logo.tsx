import React from "react";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

interface LogoProps {
  variant?: "full" | "icon";
  className?: string;
  asLink?: boolean;
}

export const Logo: React.FC<LogoProps> = ({
  variant = "full",
  className,
}) => {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const fullLogo = isDark
    ? "/assets/images/fastapi-logo-light.svg"
    : "/assets/images/fastapi-logo.svg";
  const iconLogo = isDark
    ? "/assets/images/fastapi-icon-light.svg"
    : "/assets/images/fastapi-icon.svg";

  return (
    <div className="flex items-center gap-2.5">
      <img
        src={variant === "full" ? fullLogo : iconLogo}
        alt="Platform"
        className={cn(variant === "full" ? "h-7 w-auto" : "h-6 w-6", className)}
        onError={(e) => {
          // Graceful fallback if svg not found
          const target = e.currentTarget;
          target.style.display = "none";
        }}
      />
    </div>
  );
};
