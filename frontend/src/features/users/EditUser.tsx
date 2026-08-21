import React, { useState } from "react";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { apiV1UsersUserIdUpdateUserAdmin } from "@/client/sdk.gen";
import type { UserRead } from "@/client/types.gen";

interface EditUserProps {
  user: UserRead;
  onSuccess: () => void;
}

export const EditUser: React.FC<EditUserProps> = ({ user, onSuccess }) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [email, setEmail] = useState<string>(user.email);
  const [fullName, setFullName] = useState<string>(user.full_name || "");
  const [password, setPassword] = useState<string>("");
  const [confirmPassword, setConfirmPassword] = useState<string>("");
  const [isSuperuser, setIsSuperuser] = useState<boolean>(!!user.is_superuser);
  const [isActive, setIsActive] = useState<boolean>(!!user.is_active);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password && password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (password && password !== confirmPassword) {
      setError("The passwords don't match");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const res = await apiV1UsersUserIdUpdateUserAdmin({
        path: { user_id: user.id },
        body: {
          email,
          full_name: fullName,
          password: password ? password : null,
          is_superuser: isSuperuser,
          is_active: isActive,
        },
      });

      if (res.response?.ok) {
        setIsOpen(false);
        onSuccess();
      } else {
        setError(res.error ? String(res.error) : "User update failed.");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update user.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800 hover:text-white rounded-md transition-colors text-left"
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
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-xs text-red-400">
              {error}
            </div>
          )}

          <Input
            type="email"
            label="Email *"
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />

          <Input
            type="text"
            label="Full Name"
            placeholder="Full name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />

          <Input
            type="password"
            label="Set Password"
            placeholder="Password (leave blank to keep unchanged)"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          <Input
            type="password"
            label="Confirm Password"
            placeholder="Confirm Password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />

          <div className="space-y-2 pt-2">
            <div className="flex items-center gap-2">
              <input
                id={`edit_is_superuser_${user.id}`}
                type="checkbox"
                checked={isSuperuser}
                onChange={(e) => setIsSuperuser(e.target.checked)}
                className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-blue-600 focus:ring-blue-500"
              />
              <label htmlFor={`edit_is_superuser_${user.id}`} className="text-xs text-slate-300 select-none">
                Is superuser?
              </label>
            </div>

            <div className="flex items-center gap-2">
              <input
                id={`edit_is_active_${user.id}`}
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
                className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-blue-600 focus:ring-blue-500"
              />
              <label htmlFor={`edit_is_active_${user.id}`} className="text-xs text-slate-300 select-none">
                Is active?
              </label>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
            <Button
              variant="outline"
              type="button"
              onClick={() => setIsOpen(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button type="submit" isLoading={isLoading}>
              Save
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
};
export default EditUser;
