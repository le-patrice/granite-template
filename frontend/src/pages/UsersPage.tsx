import React from "react";
import { UsersDataTable } from "@/features/users/UsersDataTable";

export const UsersPage: React.FC = () => {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-100">User Governance</h1>
        <p className="text-xs text-slate-400 mt-1">
          Manage system administrators, provision accounts, and govern role-based access.
        </p>
      </div>

      <UsersDataTable />
    </div>
  );
};
