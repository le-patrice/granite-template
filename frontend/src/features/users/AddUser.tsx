import React, { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { Alert, AlertDescription } from "@/components/ui/Alert";
import { useCustomToast } from "@/hooks/useCustomToast";
import { apiV1UsersCreateUserAdmin } from "@/client/sdk.gen";

interface AddUserProps {
  onSuccess: () => void;
}

export const AddUser: React.FC<AddUserProps> = ({ onSuccess }) => {
  const { showSuccessToast, showErrorToast } = useCustomToast();
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [email, setEmail] = useState<string>("");
  const [fullName, setFullName] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [confirmPassword, setConfirmPassword] = useState<string>("");
  const [isSuperuser, setIsSuperuser] = useState<boolean>(false);
  const [isActive, setIsActive] = useState<boolean>(true);

  // Field validation errors
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [confirmPasswordError, setConfirmPasswordError] = useState<string | null>(null);

  // Server error
  const [serverError, setServerError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const resetForm = () => {
    setEmail("");
    setFullName("");
    setPassword("");
    setConfirmPassword("");
    setIsSuperuser(false);
    setIsActive(true);
    setEmailError(null);
    setPasswordError(null);
    setConfirmPasswordError(null);
    setServerError(null);
  };

  const validate = (): boolean => {
    let isValid = true;

    // Email check
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!email.trim() || !emailRegex.test(email.trim())) {
      setEmailError("Invalid email address");
      isValid = false;
    } else {
      setEmailError(null);
    }

    // Password check
    if (!password) {
      setPasswordError("Password is required");
      isValid = false;
    } else if (password.length < 8) {
      setPasswordError("Password must be at least 8 characters");
      isValid = false;
    } else {
      setPasswordError(null);
    }

    // Confirm password check
    if (!confirmPassword) {
      setConfirmPasswordError("Please confirm your password");
      isValid = false;
    } else if (password !== confirmPassword) {
      setConfirmPasswordError("The passwords don't match");
      isValid = false;
    } else {
      setConfirmPasswordError(null);
    }

    return isValid;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError(null);

    if (!validate()) {
      return;
    }

    setIsLoading(true);

    try {
      const res = await apiV1UsersCreateUserAdmin({
        body: {
          email: email.trim(),
          full_name: fullName.trim(),
          password,
          is_superuser: isSuperuser,
          is_active: isActive,
        },
      });

      if (res.response?.ok) {
        showSuccessToast("User created successfully");
        resetForm();
        setIsOpen(false);
        onSuccess();
      } else {
        const msg = res.error
          ? String(res.error)
          : "The user with this email already exists in the system.";
        setServerError(msg);
        showErrorToast(msg);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create user.";
      setServerError(msg);
      showErrorToast(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <Button onClick={() => setIsOpen(true)} className="gap-2">
        <Plus className="h-4 w-4" />
        Add User
      </Button>

      <Modal
        isOpen={isOpen}
        onClose={() => {
          resetForm();
          setIsOpen(false);
        }}
        title="Add User"
        description="Fill in the form below to add a new user to the system."
      >
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {serverError && (
            <Alert variant="destructive">
              <AlertDescription>{serverError}</AlertDescription>
            </Alert>
          )}

          <Input
            id="add_user_email"
            type="email"
            label="Email *"
            placeholder="Email"
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              if (emailError) setEmailError(null);
            }}
            error={emailError ?? undefined}
            required
          />

          <Input
            id="add_user_fullname"
            type="text"
            label="Full Name"
            placeholder="Full name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />

          <PasswordInput
            id="add_user_password"
            label="Set Password *"
            placeholder="Password"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              if (passwordError) setPasswordError(null);
            }}
            error={passwordError ?? undefined}
            required
          />

          <PasswordInput
            id="add_user_confirm_password"
            label="Confirm Password *"
            placeholder="Password"
            value={confirmPassword}
            onChange={(e) => {
              setConfirmPassword(e.target.value);
              if (confirmPasswordError) setConfirmPasswordError(null);
            }}
            error={confirmPasswordError ?? undefined}
            required
          />

          <div className="space-y-2 pt-2">
            <label className="flex items-center gap-2.5 cursor-pointer text-xs font-normal text-foreground">
              <input
                id="add_is_superuser"
                type="checkbox"
                checked={isSuperuser}
                onChange={(e) => setIsSuperuser(e.target.checked)}
                className="h-4 w-4 rounded border-input text-primary focus:ring-ring"
              />
              <span>Is superuser?</span>
            </label>

            <label className="flex items-center gap-2.5 cursor-pointer text-xs font-normal text-foreground">
              <input
                id="add_is_active"
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="h-4 w-4 rounded border-input text-primary focus:ring-ring"
              />
              <span>Is active?</span>
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-border">
            <Button
              variant="outline"
              type="button"
              onClick={() => {
                resetForm();
                setIsOpen(false);
              }}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button type="submit" loading={isLoading}>
              Save
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
};

export default AddUser;
