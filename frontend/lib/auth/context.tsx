"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { clearToken, getToken, setToken } from "@/lib/auth/session";
import type { Admin } from "@/lib/types/auth";

interface AuthContextValue {
  admin: Admin | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [admin, setAdmin] = useState<Admin | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setAdmin(null);
      setLoading(false);
      return;
    }
    try {
      const me = await authApi.me();
      setAdmin(me);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearToken();
      }
      setAdmin(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (username: string, password: string) => {
      const token = await authApi.login({ username, password });
      setToken(token.access_token, Math.max(1, Math.floor(token.expires_in / 86400)));
      const me = await authApi.me();
      setAdmin(me);
    },
    [],
  );

  const logout = useCallback(() => {
    clearToken();
    setAdmin(null);
    router.replace("/login");
  }, [router]);

  return (
    <AuthContext.Provider value={{ admin, loading, login, logout, refresh }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
