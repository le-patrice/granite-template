import React, { useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { apiV1UsersUserIdDeleteUser } from "@/client/sdk.gen";

interface DeleteUserProps {
  id: string;
  onSuccess: () => void;
}

export const DeleteUser: React.FC<DeleteUserProps> = ({ id, onSuccess }) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleDelete = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);

    try {
      const res = await apiV1UsersUserIdDeleteUser({
        path: { user_id: id },
      });

      if (res.response?.ok) {
        setIsOpen(false);
        onSuccess();
      } else {
        setError(res.error ? String(res.error) : "User deletion failed.");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete user.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      <button
        onClick={() => setIsOpen(true)}
        className="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-red-400 hover:bg-red-500/10 rounded-md transition-colors text-left"
      >
        <Trash2 className="h-3.5 w-3.5" />
        Delete User
      </button>

      <Modal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        title="Delete User"
        description="Permanently remove this user account."
      >
        <form onSubmit={handleDelete} className="space-y-4">
          {error && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3 text-xs text-red-400">
              {error}
            </div>
          )}

          <p className="text-xs text-slate-300">
            All data associated with this user will be{" "}
            <strong className="text-red-400 font-semibold">permanently deleted.</strong> Are you sure? You will
            not be able to undo this action.
          </p>

          <div className="flex justify-end gap-3 pt-4 border-t border-slate-800">
            <Button
              variant="outline"
              type="button"
              onClick={() => setIsOpen(false)}
              disabled={isLoading}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              type="submit"
              isLoading={isLoading}
            >
              Delete
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
};
export default DeleteUser;
