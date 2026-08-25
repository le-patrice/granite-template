import React, { useState, useRef, useEffect } from "react";
import { EllipsisVertical } from "lucide-react";
import type { UserRead } from "@/client/types.gen";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";
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
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={() => setIsOpen((prev) => !prev)}
        className="h-8 w-8 text-muted-foreground hover:text-foreground"
        title="User Actions"
        aria-label="User Actions"
      >
        <EllipsisVertical className="h-4 w-4" />
      </Button>

      {isOpen && (
        <div className="absolute right-0 z-50 mt-1 w-36 rounded-lg border border-border bg-popover p-1 shadow-xl animate-in fade-in-0 zoom-in-95 duration-100">
          <EditUser
            user={user}
            onSuccess={() => {
              setIsOpen(false);
              onSuccess();
            }}
          />
          <DeleteUser
            id={user.id}
            onSuccess={() => {
              setIsOpen(false);
              onSuccess();
            }}
          />
        </div>
      )}
    </div>
  );
};

export default UserActionsMenu;
