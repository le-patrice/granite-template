import React, { useState } from "react";
import { Eye, EyeOff, AlertCircle, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuth } from "@/hooks/useAuth";
import { ApiError } from "@/lib/api";

const defaultEmail = import.meta.env.VITE_INITIAL_ADMIN_EMAIL || "admin@platform.internal";
const defaultPassword = import.meta.env.VITE_INITIAL_ADMIN_PASSWORD || "";

export const LoginForm: React.FC = () => {
  const { login } = useAuth();
  const [email, setEmail] = useState<string>(defaultEmail);
  const [password, setPassword] = useState<string>(defaultPassword);
  const [showPassword, setShowPassword] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isWarning, setIsWarning] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsWarning(false);
    setIsLoading(true);

    try {
      await login(email, password);
    } catch (err: unknown) {
      if (import.meta.env.DEV) {
        console.debug("[LoginForm] Login attempt rejected:", err);
      }

      if (err instanceof ApiError) {
        setError(err.message);
        setIsWarning(err.status === 429);
      } else if (err instanceof Error) {
        setError(err.message || "Incorrect email or password. Please verify your credentials and try again.");
      } else if (typeof err === "string") {
        setError(err);
      } else {
        setError("Incorrect email or password. Please verify your credentials and try again.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (error) {
      setError(null);
      setIsWarning(false);
    }
    setEmail(e.target.value);
  };

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (error) {
      setError(null);
      setIsWarning(false);
    }
    setPassword(e.target.value);
  };

  return (
    <div className="flex flex-col gap-6 w-full">
      <div className="flex flex-col items-center gap-2 text-center">
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Login to your account
        </h1>
        <p className="text-xs text-muted-foreground">
          Enter your credentials below to access the platform.
        </p>
      </div>

      {error && (
        <div
          role="alert"
          className={
            isWarning
              ? "flex items-center gap-2.5 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-600 dark:text-amber-400"
              : "flex items-center gap-2.5 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive"
          }
        >
          {isWarning ? (
            <AlertTriangle className="h-4 w-4 shrink-0" />
          ) : (
            <AlertCircle className="h-4 w-4 shrink-0" />
          )}
          <span>{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <Input
            id="email"
            type="email"
            label="Email"
            placeholder="user@example.com"
            value={email}
            onChange={handleEmailChange}
            required
            autoComplete="username"
          />
        </div>

        <div className="relative">
          <div className="flex items-center justify-between mb-1.5">
            <label htmlFor="password" className="text-xs font-medium text-foreground">
              Password
            </label>
            <button
              type="button"
              onClick={() => alert("Password reset token dispatched via email in production.")}
              className="text-xs text-muted-foreground hover:text-primary transition-colors underline-offset-4 hover:underline"
            >
              Forgot your password?
            </button>
          </div>

          <div className="relative">
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              placeholder="••••••••••••"
              value={password}
              onChange={handlePasswordChange}
              required
              autoComplete="current-password"
              className="flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring pr-10"
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              className="absolute right-3 top-2 text-muted-foreground hover:text-foreground transition-colors"
              title={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        <Button
          type="submit"
          className="w-full mt-2"
          isLoading={isLoading}
        >
          Log In
        </Button>

        <div className="mt-2 text-center text-xs text-muted-foreground">
          Don't have an account yet?{" "}
          <span className="text-primary font-medium cursor-pointer hover:underline">
            Sign up
          </span>
        </div>
      </form>
    </div>
  );
};

