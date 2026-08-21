import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { client } from "@/client/client.gen";
import { apiV1AuthLogoutLogout, apiV1UsersMeGetMe } from "@/client/sdk.gen";
import type { TokenResponse, UserRead } from "@/client/types.gen";
import "@/lib/api"; // Initialize client config

interface AuthContextType {
  user: UserRead | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isAdmin: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<UserRead | null>(null);
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("access_token"));
  const [isLoading, setIsLoading] = useState<boolean>(true);

  const refreshProfile = useCallback(async () => {
    const currentToken = localStorage.getItem("access_token");
    if (!currentToken) {
      setUser(null);
      setIsLoading(false);
      return;
    }

    try {
      const response = await apiV1UsersMeGetMe();
      if (response.data) {
        setUser(response.data as UserRead);
      } else {
        // Token invalid / expired
        localStorage.removeItem("access_token");
        setToken(null);
        setUser(null);
      }
    } catch {
      localStorage.removeItem("access_token");
      setToken(null);
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshProfile();
  }, [refreshProfile]);

  const login = async (email: string, password: string) => {
    setIsLoading(true);
    try {
      const res = await client.post({
        url: "/api/v1/auth/login",
        body: {
          email,
          password,
        },
      });

      const data = res.data as TokenResponse | undefined;
      if (data?.access_token) {
        const accessToken = data.access_token;
        localStorage.setItem("access_token", accessToken);
        setToken(accessToken);
        await refreshProfile();
      } else {
        throw new Error(res.error ? String(res.error) : "Invalid credentials.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    try {
      await apiV1AuthLogoutLogout();
    } catch {
      // Best effort cleanup
    } finally {
      localStorage.removeItem("access_token");
      setToken(null);
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!token && !!user,
        isAdmin: !!user?.is_superuser,
        login,
        logout,
        refreshProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
