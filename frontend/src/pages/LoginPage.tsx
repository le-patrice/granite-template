import React from "react";
import { AuthLayout } from "@/components/common/AuthLayout";
import { LoginForm } from "@/features/auth/LoginForm";

export const LoginPage: React.FC = () => {
  return (
    <AuthLayout>
      <LoginForm />
    </AuthLayout>
  );
};
export default LoginPage;
