import React, { forwardRef, useState } from "react";
import { Eye, EyeOff, Lock } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PasswordInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  showLeftLock?: boolean;
}

export const PasswordInput = forwardRef<HTMLInputElement, PasswordInputProps>(
  ({ className, label, error, helperText, showLeftLock = false, id, ...props }, ref) => {
    const [showPassword, setShowPassword] = useState(false);
    const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);
    const errorId = inputId ? `${inputId}-error` : undefined;
    const isInvalid = Boolean(error || props["aria-invalid"]);

    return (
      <div className="w-full text-left space-y-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className={cn(
              "block text-xs font-medium tracking-tight text-foreground",
              isInvalid && "text-destructive"
            )}
          >
            {label}
          </label>
        )}

        <div className="relative flex items-center">
          {showLeftLock && (
            <div className="pointer-events-none absolute left-3 flex items-center justify-center text-muted-foreground [&_svg]:size-4">
              <Lock className="h-4 w-4" />
            </div>
          )}

          <input
            id={inputId}
            type={showPassword ? "text" : "password"}
            ref={ref}
            aria-invalid={isInvalid}
            aria-describedby={isInvalid && errorId ? errorId : undefined}
            className={cn(
              "flex h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-1 pr-10 text-sm shadow-xs transition-[color,box-shadow] outline-none placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50",
              "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]",
              isInvalid &&
                "border-destructive text-destructive placeholder:text-destructive/60 focus-visible:border-destructive focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 focus-visible:ring-[3px]",
              showLeftLock && "pl-10",
              className
            )}
            {...props}
          />

          <button
            type="button"
            onClick={() => setShowPassword((prev) => !prev)}
            aria-label={showPassword ? "Hide password" : "Show password"}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1.5 text-muted-foreground hover:text-foreground rounded-md transition-colors"
          >
            {showPassword ? (
              <EyeOff className="h-4 w-4 text-muted-foreground" />
            ) : (
              <Eye className="h-4 w-4 text-muted-foreground" />
            )}
          </button>
        </div>

        {error && (
          <p
            id={errorId}
            role="alert"
            className="text-xs font-normal text-destructive mt-1 text-left animate-in fade-in-0 duration-150"
          >
            {error}
          </p>
        )}

        {!error && helperText && (
          <p className="text-xs text-muted-foreground mt-1 text-left">{helperText}</p>
        )}
      </div>
    );
  }
);

PasswordInput.displayName = "PasswordInput";
export default PasswordInput;
