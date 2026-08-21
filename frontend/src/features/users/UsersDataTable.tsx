import React, { useEffect, useState } from "react";
import { Search, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { AddUser } from "@/features/users/AddUser";
import { UserActionsMenu } from "@/features/users/UserActionsMenu";
import { LoadingSpinner } from "@/components/common/LoadingSpinner";
import { EmptyState } from "@/components/common/EmptyState";
import { apiV1UsersListUsers } from "@/client/sdk.gen";
import type { UserRead } from "@/client/types.gen";
import { useAuth } from "@/hooks/useAuth";

export const UsersDataTable: React.FC = () => {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<UserRead[]>([]);
  const [search, setSearch] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const fetchUsers = async () => {
    setIsLoading(true);
    try {
      const res = await apiV1UsersListUsers({
        query: { skip: 0, limit: 100 },
      });
      if (res.data?.data) {
        setUsers(res.data.data);
      } else if (Array.isArray(res.data)) {
        setUsers(res.data as UserRead[]);
      }
    } catch (err) {
      console.error("Failed to load users:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const filteredUsers = users.filter(
    (u) =>
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      (u.full_name && u.full_name.toLowerCase().includes(search.toLowerCase()))
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">Users Management</h1>
          <p className="text-xs text-muted-foreground mt-1">Manage user accounts, RBAC permissions, and roles</p>
        </div>
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            onClick={fetchUsers}
            disabled={isLoading}
            className="gap-1.5 text-xs"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? "animate-spin text-primary" : ""}`} />
            Refresh
          </Button>
          <AddUser onSuccess={fetchUsers} />
        </div>
      </div>

      <div className="relative w-full max-w-sm">
        <Search className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          placeholder="Filter users..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full rounded-md border border-input bg-background pl-9 pr-4 py-1.5 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
        />
      </div>

      <div className="rounded-xl border border-border bg-card overflow-hidden shadow-sm">
        {isLoading ? (
          <LoadingSpinner label="Loading users..." />
        ) : filteredUsers.length === 0 ? (
          <EmptyState
            title="No Users Found"
            description={search ? "No users match your filter criteria." : "No platform users registered yet."}
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-border bg-muted/40 text-muted-foreground font-semibold uppercase tracking-wider text-[10px]">
                <tr>
                  <th className="px-6 py-3.5">Full Name</th>
                  <th className="px-6 py-3.5">Email</th>
                  <th className="px-6 py-3.5">Role</th>
                  <th className="px-6 py-3.5">Status</th>
                  <th className="px-6 py-3.5 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredUsers.map((u) => {
                  const isCurrentUser = currentUser?.id === u.id;

                  return (
                    <tr key={u.id} className="hover:bg-accent/50 transition-colors">
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-foreground">
                            {u.full_name || "N/A"}
                          </span>
                          {isCurrentUser && (
                            <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                              You
                            </Badge>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4 text-muted-foreground font-mono">
                        {u.email}
                      </td>
                      <td className="px-6 py-4">
                        <Badge variant={u.is_superuser ? "default" : "outline"}>
                          {u.is_superuser ? "Superuser" : "User"}
                        </Badge>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <span
                            className={`h-2 w-2 rounded-full ${
                              u.is_active ? "bg-emerald-500" : "bg-muted-foreground"
                            }`}
                          />
                          <span className={u.is_active ? "text-foreground" : "text-muted-foreground"}>
                            {u.is_active ? "Active" : "Inactive"}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <UserActionsMenu user={u} onSuccess={fetchUsers} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
export default UsersDataTable;
