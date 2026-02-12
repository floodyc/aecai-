"use client";

import { useAuth } from "@/lib/auth";
import { useRouter } from "next/navigation";

export default function NavBar() {
  const { user, logout } = useAuth();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.push("/");
  };

  return (
    <header className="border-b border-gray-800 bg-gray-950">
      <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <a
          href={user ? "/dashboard" : "/"}
          className="flex items-center gap-3"
        >
          <div className="w-8 h-8 bg-primary-600 rounded-lg flex items-center justify-center font-bold text-sm">
            AI
          </div>
          <span className="text-lg font-semibold tracking-tight">AECAI</span>
        </a>

        <div className="flex items-center gap-4">
          {user ? (
            <>
              <a
                href="/pricing"
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Pricing
              </a>
              <a
                href="/billing"
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Billing
              </a>
              <div className="h-4 w-px bg-gray-800" />
              <span className="text-xs text-gray-500">{user.email}</span>
              <button
                onClick={handleLogout}
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Sign Out
              </button>
            </>
          ) : (
            <>
              <a
                href="/pricing"
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
              >
                Pricing
              </a>
              <a
                href="/trial"
                className="text-xs text-primary-400 hover:text-primary-300 font-medium transition-colors"
              >
                Free Trial
              </a>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
