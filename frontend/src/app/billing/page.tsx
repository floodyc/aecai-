"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth, User } from "@/lib/auth";

const plans = [
  {
    id: "standard" as const,
    name: "Standard",
    price: 200,
    annual: 170,
    pages: 10,
    perPage: "$20.00",
  },
  {
    id: "professional" as const,
    name: "Professional",
    price: 500,
    annual: 425,
    pages: 30,
    perPage: "$16.67",
  },
  {
    id: "enterprise" as const,
    name: "Enterprise",
    price: null,
    annual: null,
    pages: null,
    perPage: "Custom",
  },
];

const planLabels: Record<string, string> = {
  trial: "Free Trial",
  standard: "Standard",
  professional: "Professional",
  enterprise: "Enterprise",
};

export default function BillingPage() {
  const router = useRouter();
  const { user, isLoading } = useAuth();
  const [billingCycle, setBillingCycle] = useState<"monthly" | "annual">(
    "monthly"
  );

  if (!isLoading && !user) {
    router.replace("/");
    return null;
  }

  if (isLoading || !user) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const handleSelectPlan = (planId: User["plan"]) => {
    if (planId === "enterprise") {
      // TODO: Open contact form / mailto
      return;
    }
    // TODO: Integrate Stripe checkout
    alert(
      `Stripe checkout integration coming soon.\nSelected: ${planId} (${billingCycle})`
    );
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-12">
      {/* Header */}
      <div className="flex items-center justify-between mb-10">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-50 mb-1">
            Billing & Plan
          </h1>
          <p className="text-sm text-gray-400">
            Manage your subscription and payment method.
          </p>
        </div>
        <a
          href="/dashboard"
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-xs font-medium text-gray-300 transition-colors"
        >
          Back to Dashboard
        </a>
      </div>

      {/* Current Plan */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-8">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">
              Current Plan
            </p>
            <p className="text-xl font-bold text-gray-100">
              {planLabels[user.plan]}
            </p>
          </div>
          <div className="text-right">
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">
              Usage This Period
            </p>
            <p className="text-xl font-bold text-gray-100 tabular-nums">
              {user.pages_used}{" "}
              <span className="text-sm font-normal text-gray-500">
                / {user.pages_limit} pages
              </span>
            </p>
          </div>
        </div>

        {/* Usage Bar */}
        <div className="mt-4">
          <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${
                user.pages_used / user.pages_limit > 0.9
                  ? "bg-amber-500"
                  : "bg-primary-500"
              }`}
              style={{
                width: `${Math.min(
                  (user.pages_used / user.pages_limit) * 100,
                  100
                )}%`,
              }}
            />
          </div>
        </div>

        {user.plan === "trial" && (
          <div className="mt-4 p-3 bg-primary-950/30 border border-primary-900/50 rounded-lg">
            <p className="text-sm text-primary-300">
              You&apos;re on the free trial with{" "}
              {user.trial_uploads_remaining} upload
              {user.trial_uploads_remaining !== 1 ? "s" : ""} remaining.
              Upgrade below to unlock more pages.
            </p>
          </div>
        )}
      </div>

      {/* Billing Toggle */}
      <div className="flex items-center justify-center gap-3 mb-8">
        <button
          onClick={() => setBillingCycle("monthly")}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            billingCycle === "monthly"
              ? "bg-gray-800 text-gray-100"
              : "text-gray-500 hover:text-gray-300"
          }`}
        >
          Monthly
        </button>
        <button
          onClick={() => setBillingCycle("annual")}
          className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            billingCycle === "annual"
              ? "bg-gray-800 text-gray-100"
              : "text-gray-500 hover:text-gray-300"
          }`}
        >
          Annual
          <span className="ml-1.5 text-xs text-green-400">Save 15%</span>
        </button>
      </div>

      {/* Plan Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-10">
        {plans.map((plan) => {
          const isCurrent = user.plan === plan.id;
          const price =
            billingCycle === "annual" && plan.annual
              ? plan.annual
              : plan.price;

          return (
            <div
              key={plan.id}
              className={`bg-gray-900 border rounded-xl p-5 flex flex-col ${
                isCurrent
                  ? "border-primary-500 ring-1 ring-primary-500/20"
                  : "border-gray-800"
              }`}
            >
              <div className="mb-5">
                <div className="flex items-center justify-between mb-1">
                  <h3 className="font-semibold text-gray-100">{plan.name}</h3>
                  {isCurrent && (
                    <span className="px-2 py-0.5 bg-primary-600/20 text-primary-400 text-xs font-medium rounded-full">
                      Current
                    </span>
                  )}
                </div>
                {price !== null ? (
                  <div className="flex items-baseline gap-1">
                    <span className="text-2xl font-bold text-gray-50">
                      ${price}
                    </span>
                    <span className="text-sm text-gray-500">/mo</span>
                  </div>
                ) : (
                  <div className="text-2xl font-bold text-gray-50">Custom</div>
                )}
              </div>

              <div className="flex-1 mb-5">
                <div className="grid grid-cols-2 gap-2.5">
                  <div className="bg-gray-950 rounded-lg p-2.5">
                    <p className="text-xs text-gray-500">Pages</p>
                    <p className="text-sm font-semibold text-gray-200">
                      {plan.pages ?? "Unlimited"}
                    </p>
                  </div>
                  <div className="bg-gray-950 rounded-lg p-2.5">
                    <p className="text-xs text-gray-500">Per Page</p>
                    <p className="text-sm font-semibold text-gray-200">
                      {plan.perPage}
                    </p>
                  </div>
                </div>
              </div>

              <button
                onClick={() => handleSelectPlan(plan.id)}
                disabled={isCurrent}
                className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-colors ${
                  isCurrent
                    ? "bg-gray-800 text-gray-500 cursor-default"
                    : "bg-primary-600 hover:bg-primary-500 text-white"
                }`}
              >
                {isCurrent
                  ? "Current Plan"
                  : plan.id === "enterprise"
                  ? "Contact Sales"
                  : "Upgrade"}
              </button>
            </div>
          );
        })}
      </div>

      {/* Payment Method */}
      {user.plan !== "trial" && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-8">
          <h3 className="font-semibold text-gray-100 mb-4">Payment Method</h3>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-7 bg-gray-800 rounded flex items-center justify-center">
                <svg
                  className="w-6 h-4 text-gray-400"
                  fill="currentColor"
                  viewBox="0 0 24 16"
                >
                  <rect width="24" height="16" rx="2" opacity="0.3" />
                  <rect x="2" y="4" width="20" height="2" />
                </svg>
              </div>
              <div>
                <p className="text-sm text-gray-200">No card on file</p>
                <p className="text-xs text-gray-500">
                  Add a payment method to continue after trial
                </p>
              </div>
            </div>
            <button className="px-4 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-xs font-medium text-gray-300 transition-colors">
              Add Card
            </button>
          </div>
        </div>
      )}

      {/* Overage Info */}
      <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-5 text-center">
        <p className="text-sm text-gray-400 mb-1">
          Need more pages? No hard cutoffs.
        </p>
        <p className="text-xs text-gray-600">
          Pages beyond your plan cap are billed at $25/page at the end of
          your billing cycle.
        </p>
      </div>
    </div>
  );
}
