import React, { useState, useRef, useEffect } from "react";
import { MoreVertical } from "lucide-react";
import type { UserRead } from "@/client/types.gen";
import { useAuth } from "@/hooks/useAuth";
import { EditUser } from "@/features/users/EditUser";
import { DeleteUser } from "@/features/users/DeleteUser";

interface UserActionsMenuProps {
  user: UserRead;
  onSuccess: () => void;
}

export const UserActionsMenu: React.FC<UserActionsMenuProps> = ({ user, onSuccess }) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const { user: currentUser } = useAuth();
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  if (user.id === currentUser?.id) {
    return null;
  }

  return (
    <div className="relative inline-block text-left" ref={menuRef}>
      <button
        onClick={() => setIsOpen((prev) => !prev)}
        className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-slate-200 transition-colors"
        title="User Actions"
      >
        <MoreVertical className="h-4 w-4" />
      </button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-1 w-36 rounded-lg border border-slate-800 bg-slate-900 p-1 shadow-xl">
          <EditUser user={user} onSuccess={() => { setIsOpen(false); onSuccess(); }} />
          <DeleteUser id={user.id} onSuccess={() => { setIsOpen(false); onSuccess(); }} />
        </div>
      )}
    </div>
  );
};
export default UserActionsMenu;
