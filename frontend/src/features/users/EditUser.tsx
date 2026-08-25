import React, { useState } from "react";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { PasswordInput } from "@/components/ui/PasswordInput";
import { Alert, AlertDescription } from "@/components/ui/Alert";
import { useCustomToast } from "@/hooks/useCustomToast";
import { apiV1UsersUserIdUpdateUserAdmin } from "@/client/sdk.gen";
import type { UserRead } from "@/client/types.gen";

interface EditUserProps {
  user: UserRead;
  onSuccess: () => void;
}

export const EditUser: React.FC<EditUserProps> = ({ user, onSuccess }) => {
  const { showSuccessToast, showErrorToast } = useCustomToast();
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [email, setEmail] = useState<string>(user.email);
  const [fullName, setFullName] = useState<string>(user.full_name || "");
  const [password, setPassword] = useState<string>("");
  const [confirmPassword, setConfirmPassword] = useState<string>("");
  const [isSuperuser, setIsSuperuser] = useState<boolean>(!!user.is_superuser);
  const [isActive, setIsActive] = useState<boolean>(!!user.is_active);

  // Field validation errors
  const [emailError, setEmailError] = useState<string | null>(null);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [confirmPasswordError, setConfirmPasswordError] = useState<string | null>(null);

  // Server error
  const [serverError, setServerError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

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

    // Password check (optional in edit)
    if (password) {
      if (password.length < 8) {
        setPasswordError("Password must be at least 8 characters");
        isValid = false;
      } else {
        setPasswordError(null);
      }

      if (password !== confirmPassword) {
        setConfirmPasswordError("The passwords don't match");
        isValid = false;
      } else {
        setConfirmPasswordError(null);
      }
    } else {
      setPasswordError(null);
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
      const res = await apiV1UsersUserIdUpdateUserAdmin({
        path: { user_id: user.id },
        body: {
          email: email.trim(),
          full_name: fullName.trim() || null,
          password: password ? password : null,
          is_superuser: isSuperuser,
          is_active: isActive,
        },
      });

      if (res.response?.ok) {
        showSuccessToast("User updated successfully");
        setIsOpen(false);
        onSuccess();
      } else {
        const msg = res.error ? String(res.error) : "User update failed.";
        setServerError(msg);
        showErrorToast(msg);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update user.";
      setServerError(msg);
      showErrorToast(msg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-foreground hover:bg-accent rounded-md transition-colors text-left"
      >
        <Pencil className="h-3.5 w-3.5" />
        Edit User
      </button>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        title="Edit User"
        description="Update the user details below."
      >
        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          {serverError && (
            <Alert variant="destructive">
              <AlertDescription>{serverError}</AlertDescription>
            </Alert>
          )}

          <Input
            id={`edit_user_email_${user.id}`}
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
            id={`edit_user_fullname_${user.id}`}
            type="text"
            label="Full Name"
            placeholder="Full name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />

          <PasswordInput
            id={`edit_user_password_${user.id}`}
            label="Set Password"
            placeholder="Password (leave blank to keep unchanged)"
            value={password}
            onChange={(e) => {
              setPassword(e.target.value);
              if (passwordError) setPasswordError(null);
            }}
            error={passwordError ?? undefined}
          />

          <PasswordInput
            id={`edit_user_confirm_${user.id}`}
            label="Confirm Password"
            placeholder="Confirm password"
            value={confirmPassword}
            onChange={(e) => {
              setConfirmPassword(e.target.value);
              if (confirmPasswordError) setConfirmPasswordError(null);
            }}
            error={confirmPasswordError ?? undefined}
          />

          <div className="space-y-2 pt-2">
            <label className="flex items-center gap-2.5 cursor-pointer text-xs font-normal text-foreground">
              <input
                id={`edit_is_superuser_${user.id}`}
                type="checkbox"
                checked={isSuperuser}
                onChange={(e) => setIsSuperuser(e.target.checked)}
                className="h-4 w-4 rounded border-input text-primary focus:ring-ring"
              />
              <span>Is superuser?</span>
            </label>

            <label className="flex items-center gap-2.5 cursor-pointer text-xs font-normal text-foreground">
              <input
                id={`edit_is_active_${user.id}`}
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
              onClick={() => setIsOpen(false)}
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

export default EditUser;
