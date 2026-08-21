import React from "react";
import { Badge } from "@/components/ui/Badge";

export const UserRoleBadge: React.FC<{ isSuperuser?: boolean | null }> = ({ isSuperuser }) => {
  if (isSuperuser) {
    return <Badge variant="warning">Superadmin</Badge>;
  }
  return <Badge variant="default">Standard User</Badge>;
};

export const UserStatusBadge: React.FC<{ isActive?: boolean | null }> = ({ isActive }) => {
  if (isActive) {
    return <Badge variant="success">Active</Badge>;
  }
  return <Badge variant="destructive">Inactive</Badge>;
};
