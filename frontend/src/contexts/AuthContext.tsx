"use client";

import { jwtDecode } from "jwt-decode";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { setTokenCookie, removeTokenCookie } from "@/lib/cookie";

interface User {
  id: string;
  username?: string;
  role: "doctor" | "researcher" | "admin" | string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (token: string, role: string, username?: string) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  const logout = () => {
    localStorage.removeItem("token");
    removeTokenCookie();
    setUser(null);
    router.push("/login");
  };

  useEffect(() => {
    const token = localStorage.getItem("token");
    if (token) {
      try {
        const decoded = jwtDecode(token) as any;
        if (decoded.exp * 1000 < Date.now()) {
          logout();
        } else {
          // Re-sync cookie on page load (covers tab restore / refresh)
          setTokenCookie(token);
          setUser({ id: decoded.sub, username: decoded.username, role: decoded.role });
        }
      } catch {
        logout();
      }
    } else {
      removeTokenCookie();
    }
    setLoading(false);
  }, []);

  const login = (token: string, role: string, username?: string) => {
    localStorage.setItem("token", token);
    setTokenCookie(token);
    const decoded = jwtDecode(token) as any;
    setUser({ id: decoded.sub, username: username || decoded.username, role: role as any });
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
