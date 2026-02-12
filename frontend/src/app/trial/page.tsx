"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function TrialPage() {
  const router = useRouter();
  const { user, signup, isLoading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [company, setCompany] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Redirect if already logged in
  if (!isLoading && user) {
    router.replace("/dashboard");
    return null;
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email || !password || !company) {
      setError("Please fill in all fields.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setSubmitting(true);
    try {
      await signup(email, password, company);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Signup failed");
      setSubmitting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-md mx-auto px-6 py-16">
      {/* Header */}
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 bg-green-950/50 border border-green-900 rounded-full text-xs font-medium text-green-400 mb-5">
          <svg
            className="w-3.5 h-3.5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M5 13l4 4L19 7"
            />
          </svg>
          No credit card required
        </div>
        <h1 className="text-3xl font-bold tracking-tight text-gray-50 mb-3">
          Start Your Free Trial
        </h1>
        <p className="text-gray-400 text-sm">
          Get 3 free PDF uploads to see AECAI in action.
          <br />
          No time limit. Upgrade when you&apos;re ready.
        </p>
      </div>

      {/* What You Get */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 mb-6">
        <p className="text-xs font-medium text-gray-400 uppercase tracking-wider mb-3">
          Free Trial Includes
        </p>
        <ul className="space-y-2.5">
          {[
            "3 full PDF uploads (multi-page)",
            "Complete CV + OCR fixture detection",
            "TXT & JSON report downloads",
            "No time limit on your trial",
          ].map((item) => (
            <li key={item} className="flex items-start gap-2.5 text-sm">
              <svg
                className="w-4 h-4 text-green-500 mt-0.5 shrink-0"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
              <span className="text-gray-300">{item}</span>
            </li>
          ))}
        </ul>
      </div>

      {/* Signup Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
          <div>
            <label
              htmlFor="company"
              className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5"
            >
              Company Name
            </label>
            <input
              id="company"
              type="text"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="Acme Electrical Engineering"
              className="w-full px-4 py-2.5 bg-gray-950 border border-gray-700 rounded-lg text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500 transition-colors"
            />
          </div>
          <div>
            <label
              htmlFor="email"
              className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5"
            >
              Work Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className="w-full px-4 py-2.5 bg-gray-950 border border-gray-700 rounded-lg text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500 transition-colors"
              autoComplete="email"
            />
          </div>
          <div>
            <label
              htmlFor="password"
              className="block text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              className="w-full px-4 py-2.5 bg-gray-950 border border-gray-700 rounded-lg text-sm text-gray-100 placeholder-gray-600 focus:outline-none focus:border-primary-500 focus:ring-1 focus:ring-primary-500 transition-colors"
              autoComplete="new-password"
            />
          </div>

          {error && (
            <div className="p-3 bg-red-950/50 border border-red-900 rounded-lg text-sm text-red-300">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-primary-800 disabled:text-primary-400 rounded-lg text-sm font-semibold transition-colors"
          >
            {submitting ? "Creating account..." : "Create Free Account"}
          </button>
        </div>
      </form>

      {/* Links */}
      <div className="mt-6 text-center space-y-3">
        <p className="text-sm text-gray-500">
          Already have an account?{" "}
          <a
            href="/"
            className="text-primary-400 hover:text-primary-300 font-medium transition-colors"
          >
            Sign in
          </a>
        </p>
        <a
          href="/pricing"
          className="inline-block text-xs text-gray-600 hover:text-gray-400 transition-colors"
        >
          Compare pricing plans
        </a>
      </div>

      {/* Value prop */}
      <div className="mt-14 bg-gray-900/50 border border-gray-800 rounded-xl p-5 text-center">
        <p className="text-sm text-gray-400 mb-1">
          Each page saves ~30 min of manual takeoff
        </p>
        <p className="text-xs text-gray-600">
          At typical estimator rates, that&apos;s $30-50 in labor savings per
          page processed.
        </p>
      </div>
    </div>
  );
}
