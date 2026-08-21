import React, { useState } from "react";
import { AlertTriangle, Check, AlertCircle } from "lucide-react";
import { Card, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/hooks/useAuth";
import { apiV1UsersMeUpdateMe, apiV1UsersMePasswordUpdatePasswordMe, apiV1UsersMeDeleteMe } from "@/client/sdk.gen";

export const SettingsPage: React.FC = () => {
  const { user, refreshProfile, logout } = useAuth();
  const [activeTab, setActiveTab] = useState<"profile" | "password" | "danger">("profile");

  // Profile Form State
  const [fullName, setFullName] = useState<string>(user?.full_name || "");
  const [email, setEmail] = useState<string>(user?.email || "");
  const [isUpdatingProfile, setIsUpdatingProfile] = useState<boolean>(false);
  const [profileMsg, setProfileMsg] = useState<string | null>(null);
  const [profileErr, setProfileErr] = useState<string | null>(null);

  // Password Form State
  const [currentPassword, setCurrentPassword] = useState<string>("");
  const [newPassword, setNewPassword] = useState<string>("");
  const [confirmPassword, setConfirmPassword] = useState<string>("");
  const [isUpdatingPassword, setIsUpdatingPassword] = useState<boolean>(false);
  const [passwordMsg, setPasswordMsg] = useState<string | null>(null);
  const [passwordErr, setPasswordErr] = useState<string | null>(null);

  // Danger Zone State
  const [isDeleteOpen, setIsDeleteOpen] = useState<boolean>(false);
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [deleteErr, setDeleteErr] = useState<string | null>(null);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsUpdatingProfile(true);
    setProfileMsg(null);
    setProfileErr(null);

    try {
      const res = await apiV1UsersMeUpdateMe({
        body: {
          full_name: fullName,
          email: email,
        },
      });

      if (res.response?.ok) {
        setProfileMsg("Profile updated successfully");
        await refreshProfile();
      } else {
        setProfileErr(res.error ? String(res.error) : "User with this email already exists");
      }
    } catch (err: unknown) {
      setProfileErr(err instanceof Error ? err.message : "Failed to update profile.");
    } finally {
      setIsUpdatingProfile(false);
    }
  };

  const handleUpdatePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPassword.length < 8) {
      setPasswordErr("New password must be at least 8 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordErr("The passwords don't match");
      return;
    }
    if (currentPassword === newPassword) {
      setPasswordErr("New password cannot be the same as the current one");
      return;
    }

    setIsUpdatingPassword(true);
    setPasswordMsg(null);
    setPasswordErr(null);

    try {
      const res = await apiV1UsersMePasswordUpdatePasswordMe({
        body: {
          current_password: currentPassword,
          new_password: newPassword,
        },
      });

      if (res.response?.ok) {
        setPasswordMsg("Password updated successfully");
        setCurrentPassword("");
        setNewPassword("");
        setConfirmPassword("");
      } else {
        setPasswordErr(res.error ? String(res.error) : "Incorrect password");
      }
    } catch (err: unknown) {
      setPasswordErr(err instanceof Error ? err.message : "Failed to update password.");
    } finally {
      setIsUpdatingPassword(false);
    }
  };

  const handleDeleteAccount = async () => {
    setIsDeleting(true);
    setDeleteErr(null);

    try {
      const res = await apiV1UsersMeDeleteMe();
      if (res.response?.ok) {
        await logout();
      } else {
        setDeleteErr(res.error ? String(res.error) : "Super users are not allowed to delete themselves");
      }
    } catch (err: unknown) {
      setDeleteErr(err instanceof Error ? err.message : "Failed to delete account.");
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">User Settings</h1>
        <p className="text-xs text-muted-foreground mt-1">Manage your account settings and preferences</p>
      </div>

      {/* Tabs Header */}
      <div className="flex gap-2 border-b border-border pb-2">
        <button
          onClick={() => setActiveTab("profile")}
          className={`px-4 py-2 text-xs font-medium rounded-lg transition-colors ${
            activeTab === "profile"
              ? "bg-accent text-accent-foreground font-semibold"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
          }`}
        >
          My profile
        </button>
        <button
          onClick={() => setActiveTab("password")}
          className={`px-4 py-2 text-xs font-medium rounded-lg transition-colors ${
            activeTab === "password"
              ? "bg-accent text-accent-foreground font-semibold"
              : "text-muted-foreground hover:text-foreground hover:bg-accent/50"
          }`}
        >
          Password
        </button>
        {!user?.is_superuser && (
          <button
            onClick={() => setActiveTab("danger")}
            className={`px-4 py-2 text-xs font-medium rounded-lg transition-colors ${
              activeTab === "danger"
                ? "bg-destructive/15 text-destructive font-semibold"
                : "text-muted-foreground hover:text-destructive hover:bg-destructive/10"
            }`}
          >
            Danger zone
          </button>
        )}
      </div>

      {/* Profile Tab */}
      {activeTab === "profile" && (
        <Card>
          <CardHeader>
            <CardTitle>User Information</CardTitle>
            <CardDescription>Update your personal information</CardDescription>
          </CardHeader>

          {profileMsg && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-xs text-emerald-600 dark:text-emerald-400">
              <Check className="h-4 w-4 shrink-0" />
              <span>{profileMsg}</span>
            </div>
          )}

          {profileErr && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-xs text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{profileErr}</span>
            </div>
          )}

          <form onSubmit={handleUpdateProfile} className="space-y-4">
            <Input
              type="email"
              label="Email *"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />

            <Input
              type="text"
              label="Full Name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
            />

            <div className="pt-4 flex justify-end">
              <Button type="submit" isLoading={isUpdatingProfile}>
                Save
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Password Tab */}
      {activeTab === "password" && (
        <Card>
          <CardHeader>
            <CardTitle>Change Password</CardTitle>
            <CardDescription>Update your account password</CardDescription>
          </CardHeader>

          {passwordMsg && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 p-3 text-xs text-emerald-600 dark:text-emerald-400">
              <Check className="h-4 w-4 shrink-0" />
              <span>{passwordMsg}</span>
            </div>
          )}

          {passwordErr && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-xs text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{passwordErr}</span>
            </div>
          )}

          <form onSubmit={handleUpdatePassword} className="space-y-4">
            <Input
              type="password"
              label="Current Password *"
              placeholder="Current password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />

            <Input
              type="password"
              label="New Password *"
              placeholder="New password (min 8 chars)"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
            />

            <Input
              type="password"
              label="Confirm Password *"
              placeholder="Confirm new password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
            />

            <div className="pt-4 flex justify-end">
              <Button type="submit" isLoading={isUpdatingPassword}>
                Save
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Danger Zone Tab */}
      {activeTab === "danger" && (
        <Card className="border-destructive/20 bg-destructive/5">
          <CardHeader>
            <CardTitle className="text-destructive flex items-center gap-2">
              <AlertTriangle className="h-5 w-5" />
              Delete Account
            </CardTitle>
            <CardDescription>
              Permanently delete your account and all associated data.
            </CardDescription>
          </CardHeader>

          {deleteErr && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-destructive/10 border border-destructive/20 p-3 text-xs text-destructive">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{deleteErr}</span>
            </div>
          )}

          <div className="flex justify-between items-center pt-4">
            <p className="text-xs text-muted-foreground">
              Once deleted, your account cannot be recovered.
            </p>
            <Button variant="destructive" onClick={() => setIsDeleteOpen(true)}>
              Delete Account
            </Button>
          </div>

          <Modal
            isOpen={isDeleteOpen}
            onClose={() => setIsDeleteOpen(false)}
            title="Delete Account"
            description="Are you sure you want to permanently delete your account?"
          >
            <p className="text-xs text-muted-foreground">
              This action cannot be undone. All your data will be permanently purged.
            </p>
            <div className="mt-6 flex justify-end gap-3 border-t border-border pt-4">
              <Button variant="outline" onClick={() => setIsDeleteOpen(false)}>
                Cancel
              </Button>
              <Button variant="destructive" onClick={handleDeleteAccount} isLoading={isDeleting}>
                Yes, Delete My Account
              </Button>
            </div>
          </Modal>
        </Card>
      )}
    </div>
  );
};
export default SettingsPage;
