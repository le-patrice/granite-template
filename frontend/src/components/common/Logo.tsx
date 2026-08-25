import React from "react";
import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/utils";

interface LogoProps {
  variant?: "full" | "icon" | "responsive";
  className?: string;
  asLink?: boolean;
}

export const Logo: React.FC<LogoProps> = ({
  variant = "full",
  className,
  asLink = false,
}) => {
  const { theme } = useTheme();
  const isDark = theme === "dark";

  const fullLogo = isDark
    ? "/assets/images/granite-logo-dark.png"
    : "/assets/images/granite-logo-light.png";
  const iconLogo = isDark
    ? "/assets/images/granite-logo.png"
    : "/assets/images/granite-logo.png";

  const content =
    variant === "responsive" ? (
      <div className="flex items-center">
        <img
          src={fullLogo}
          alt="Granite"
          className={cn("h-6 w-auto block group-data-[collapsible=icon]:hidden", className)}
        />
        <img
          src={iconLogo}
          alt="FastAPI"
          className={cn("size-5 hidden group-data-[collapsible=icon]:block", className)}
        />
      </div>
    ) : (
      <img
        src={variant === "full" ? fullLogo : iconLogo}
        alt="FastAPI"
        className={cn(variant === "full" ? "h-7 w-auto" : "h-6 w-6", className)}
      />
    );

  if (!asLink) {
    return <div className="inline-flex items-center">{content}</div>;
  }

  return (
    <a href="/" className="inline-flex items-center">
      {content}
    </a>
  );
};

export default Logo;
