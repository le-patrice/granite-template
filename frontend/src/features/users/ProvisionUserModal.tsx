import React, { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { apiV1UsersCreateUserAdmin } from "@/client/sdk.gen";
import type { UserAdminCreate } from "@/client/types.gen";

interface ProvisionUserModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export const ProvisionUserModal: React.FC<ProvisionUserModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
}) => {
  const [email, setEmail] = useState<string>("");
  const [fullName, setFullName] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [isSuperuser, setIsSuperuser] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const payload: UserAdminCreate = {
        email,
        full_name: fullName,
        password,
        is_superuser: isSuperuser,
        is_active: true,
      };

      const res = await apiV1UsersCreateUserAdmin({
        body: payload,
      });

      if (res.response?.ok) {
        setEmail("");
        setFullName("");
        setPassword("");
        setIsSuperuser(false);
        onSuccess();
        onClose();
      } else {
        setError("Failed to create user. Please verify user details or permissions.");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Error creating user");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Provision Platform User"
      description="Create a new platform user with designated RBAC privileges."
    >
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-xs text-red-400">
            {error}
          </div>
        )}

        <Input
          label="Full Name"
          placeholder="Jane Doe"
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
          required
        />

        <Input
          type="email"
          label="Email Address"
          placeholder="user@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />

        <Input
          type="password"
          label="Initial Password"
          placeholder="SecurePassword123!"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />

        <div className="flex items-center gap-2 pt-2">
          <input
            id="is_superuser"
            type="checkbox"
            checked={isSuperuser}
            onChange={(e) => setIsSuperuser(e.target.checked)}
            className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-blue-600 focus:ring-blue-500"
          />
          <label htmlFor="is_superuser" className="text-xs text-slate-300 select-none">
            Grant Superadmin Privileges (Elevated RBAC)
          </label>
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
          <Button variant="ghost" type="button" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" isLoading={isLoading}>
            Provision User
          </Button>
        </div>
      </form>
    </Modal>
  );
};
