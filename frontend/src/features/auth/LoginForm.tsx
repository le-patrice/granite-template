import React, { useState } from "react";
import { Mail, Lock } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { Alert, AlertDescription } from "@/components/ui/Alert";
import { Logo } from "@/components/common/Logo";
import { useAuth } from "@/hooks/useAuth";
import { useCustomToast } from "@/hooks/useCustomToast";
import { ApiError } from "@/lib/api";

const defaultEmail = import.meta.env.VITE_INITIAL_ADMIN_EMAIL || "admin@platform.internal";
const defaultPassword = import.meta.env.VITE_INITIAL_ADMIN_PASSWORD || "";

export const LoginForm: React.FC = () => {
  const { login } = useAuth();
  const { showErrorToast, showWarningToast } = useCustomToast();

  const [email, setEmail] = useState<string>(defaultEmail);
  const [password, setPassword] = useState<string>(defaultPassword);

  // Field validation errors
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);

  // Server error banner
  const [serverError, setServerError] = useState<string | null>(null);
  const [isRateLimited, setIsRateLimited] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const validateEmail = (val: string): boolean => {
    if (!val.trim()) {
      setEmailError("Invalid email address");
      return false;
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(val.trim())) {
      setEmailError("Invalid email address");
      return false;
    }
    setEmailError(null);
    return true;
  };

  const validatePassword = (val: string): boolean => {
    if (!val) {
      setPasswordError("Password is required");
      return false;
    }
    if (val.length < 8) {
      setPasswordError("Password must be at least 8 characters");
      return false;
    }
    setPasswordError(null);
    return true;
  };

  const handleEmailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setEmail(val);
    if (emailError) {
      setEmailError(null);
    }
    if (serverError) {
      setServerError(null);
      setIsRateLimited(false);
    }
  };

  const handlePasswordChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setPassword(val);
    if (passwordError) {
      setPasswordError(null);
    }
    if (serverError) {
      setServerError(null);
      setIsRateLimited(false);
    }
  };

  const handleEmailBlur = () => {
    if (email) {
      validateEmail(email);
    }
  };

  const handlePasswordBlur = () => {
    if (password) {
      validatePassword(password);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError(null);
    setIsRateLimited(false);

    const isEmailValid = validateEmail(email);
    const isPasswordValid = validatePassword(password);

    if (!isEmailValid || !isPasswordValid) {
      return;
    }

    setIsLoading(true);

    try {
      await login(email.trim(), password);
    } catch (err: unknown) {
      if (import.meta.env.DEV) {
        console.debug("[LoginForm] Authentication failed:", err);
      }

      let errorMsg = "Unable to communicate with the server. Please try again later";
      let is429 = false;

      if (err instanceof ApiError) {
        errorMsg = err.message;
        is429 = err.status === 429;
      } else if (err instanceof Error && err.message) {
        errorMsg = err.message;
      } else if (typeof err === "string") {
        errorMsg = err;
      }

      setServerError(errorMsg);
      setIsRateLimited(is429);

      if (is429) {
        showWarningToast(errorMsg, "Rate Limited");
      } else {
        showErrorToast(errorMsg, "Authentication Error");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 w-full">
      {/* Header Branding */}
      <div className="flex flex-col items-center gap-2 text-center">
        <div className="lg:hidden mb-2">
          <Logo variant="icon" className="h-10 w-10" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          Login to your account
        </h1>
        <p className="text-xs text-muted-foreground">
          Enter your credentials below to access the platform.
        </p>
      </div>

      {/* Server Level Alert Banner */}
      {serverError && (
        <Alert variant={isRateLimited ? "warning" : "destructive"}>
          <AlertDescription>{serverError}</AlertDescription>
        </Alert>
      )}

      {/* Form Fields */}
      <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
        {/* Email Field */}
        <div>
          <Input
            id="email"
            name="email"
            type="email"
            label="Email"
            placeholder="user@example.com"
            value={email}
            onChange={handleEmailChange}
            onBlur={handleEmailBlur}
            error={emailError ?? undefined}
            icon={<Mail className="h-4 w-4" />}
            autoComplete="username"
            required
          />
        </div>

        {/* Password Field */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label
              htmlFor="password"
              className={`block text-xs font-medium tracking-tight ${
                passwordError ? "text-destructive" : "text-foreground"
              }`}
            >
              Password
            </label>
            <button
              type="button"
              onClick={() =>
                alert("Password reset instructions dispatched to registered email.")
              }
              className="text-xs font-medium text-primary hover:underline underline-offset-4 transition-colors"
            >
              Forgot your password?
            </button>
          </div>

          <PasswordInput
            id="password"
            name="password"
            placeholder="•••••••••"
            value={password}
            onChange={handlePasswordChange}
            onBlur={handlePasswordBlur}
            error={passwordError ?? undefined}
            showLeftLock={true}
            autoComplete="current-password"
            required
          />
        </div>

        {/* Submit Button */}
        <Button
          type="submit"
          variant="primary"
          className="w-full mt-2 font-medium"
          loading={isLoading}
        >
          Log In
        </Button>

        {/* Signup Microcopy */}
        <div className="mt-2 text-center text-xs text-muted-foreground">
          Don't have an account yet?{" "}
          <button
            type="button"
            onClick={() =>
              alert("Self-registration is managed by platform administrator.")
            }
            className="text-primary font-medium hover:underline underline-offset-4 cursor-pointer"
          >
            Sign up
          </button>
        </div>
      </form>
    </div>
  );
};

export default LoginForm;
