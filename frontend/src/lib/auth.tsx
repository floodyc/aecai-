"use client";

import { createContext, useContext, useState, useEffect, ReactNode } from "react";

export interface User {
  id: string;
  email: string;
  company: string;
  plan: "trial" | "standard" | "professional" | "enterprise";
  pages_used: number;
  pages_limit: number;
  trial_uploads_remaining: number;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, company: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("aecai_user");
    if (stored) {
      try {
        setUser(JSON.parse(stored));
      } catch {
        localStorage.removeItem("aecai_user");
      }
    }
    setIsLoading(false);
  }, []);

  const login = async (email: string, _password: string) => {
    // TODO: Replace with real API call
    const mockUser: User = {
      id: crypto.randomUUID(),
      email,
      company: email.split("@")[1]?.split(".")[0] || "Company",
      plan: "trial",
      pages_used: 0,
      pages_limit: 3,
      trial_uploads_remaining: 3,
    };
    setUser(mockUser);
    localStorage.setItem("aecai_user", JSON.stringify(mockUser));
  };

  const signup = async (email: string, _password: string, company: string) => {
    // TODO: Replace with real API call
    const mockUser: User = {
      id: crypto.randomUUID(),
      email,
      company,
      plan: "trial",
      pages_used: 0,
      pages_limit: 3,
      trial_uploads_remaining: 3,
    };
    setUser(mockUser);
    localStorage.setItem("aecai_user", JSON.stringify(mockUser));
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem("aecai_user");
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
