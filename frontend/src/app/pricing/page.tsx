"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

const plans = [
  {
    name: "Standard",
    price: 200,
    annual: 170,
    pages: 10,
    perPage: "$20.00",
    roi: "15:1",
    features: [
      "10 pages / month",
      "Full CV + OCR pipeline",
      "TXT & JSON reports",
      "Email support",
    ],
    cta: "Get Started",
    highlighted: false,
  },
  {
    name: "Professional",
    price: 500,
    annual: 425,
    pages: 30,
    perPage: "$16.67",
    roi: "18:1",
    features: [
      "30 pages / month",
      "Full CV + OCR pipeline",
      "TXT & JSON reports",
      "Priority support",
      "Usage analytics",
    ],
    cta: "Get Started",
    highlighted: true,
  },
  {
    name: "Enterprise",
    price: null,
    annual: null,
    pages: null,
    perPage: "Custom",
    roi: "Custom",
    features: [
      "Unlimited pages",
      "Full CV + OCR pipeline",
      "TXT & JSON reports",
      "Dedicated support",
      "Custom integrations",
      "SLA guarantee",
    ],
    cta: "Contact Sales",
    highlighted: false,
  },
];

export default function PricingPage() {
  const router = useRouter();
  const { user } = useAuth();

  return (
    <div className="max-w-5xl mx-auto px-6 py-16">
      {/* Header */}
      <div className="text-center mb-14">
        <h1 className="text-3xl font-bold tracking-tight text-gray-50 mb-3">
          Simple, Transparent Pricing
        </h1>
        <p className="text-gray-400 max-w-lg mx-auto text-sm">
          Each page replaces ~30 minutes of manual takeoff. Pay a fraction of
          the labor you save — the tool pays for itself on the first drawing
          set.
        </p>
      </div>

      {/* Plan Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-16">
        {plans.map((plan) => (
          <div
            key={plan.name}
            className={`relative bg-gray-900 border rounded-xl p-6 flex flex-col ${
              plan.highlighted
                ? "border-primary-500 ring-1 ring-primary-500/20"
                : "border-gray-800"
            }`}
          >
            {plan.highlighted && (
              <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-3 py-0.5 bg-primary-600 rounded-full text-xs font-semibold tracking-wide">
                Most Popular
              </div>
            )}

            <div className="mb-6">
              <h3 className="text-lg font-semibold text-gray-100 mb-1">
                {plan.name}
              </h3>
              {plan.price !== null ? (
                <div className="flex items-baseline gap-1.5">
                  <span className="text-3xl font-bold text-gray-50">
                    ${plan.price}
                  </span>
                  <span className="text-sm text-gray-500">/month</span>
                </div>
              ) : (
                <div className="text-3xl font-bold text-gray-50">Custom</div>
              )}
              {plan.annual !== null && (
                <p className="text-xs text-gray-500 mt-1">
                  ${plan.annual}/mo billed annually (save 15%)
                </p>
              )}
            </div>

            {/* Stats Row */}
            <div className="grid grid-cols-2 gap-3 mb-6">
              <div className="bg-gray-950 rounded-lg p-3">
                <p className="text-xs text-gray-500 mb-0.5">Per Page</p>
                <p className="text-sm font-semibold text-gray-200">
                  {plan.perPage}
                </p>
              </div>
              <div className="bg-gray-950 rounded-lg p-3">
                <p className="text-xs text-gray-500 mb-0.5">ROI</p>
                <p className="text-sm font-semibold text-primary-400">
                  {plan.roi}
                </p>
              </div>
            </div>

            {/* Features */}
            <ul className="space-y-2.5 mb-8 flex-1">
              {plan.features.map((f) => (
                <li key={f} className="flex items-start gap-2 text-sm">
                  <svg
                    className="w-4 h-4 text-primary-500 mt-0.5 shrink-0"
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
                  <span className="text-gray-300">{f}</span>
                </li>
              ))}
            </ul>

            {/* CTA */}
            <button
              onClick={() => {
                if (plan.name === "Enterprise") {
                  // TODO: Open contact form
                  return;
                }
                router.push(user ? "/dashboard" : "/trial");
              }}
              className={`w-full py-2.5 rounded-lg text-sm font-semibold transition-colors ${
                plan.highlighted
                  ? "bg-primary-600 hover:bg-primary-500 text-white"
                  : "bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700"
              }`}
            >
              {plan.cta}
            </button>
          </div>
        ))}
      </div>

      {/* Overage & Details */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6 mb-8">
        <h3 className="font-semibold text-gray-100 mb-4">
          Additional Details
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 text-sm">
          <div>
            <p className="text-gray-400 font-medium mb-1">Overage Pricing</p>
            <p className="text-gray-500">
              $25 per page beyond your plan cap. No hard cutoff — finish your
              project, overages billed at end of cycle.
            </p>
          </div>
          <div>
            <p className="text-gray-400 font-medium mb-1">Annual Discount</p>
            <p className="text-gray-500">
              Save 15% with annual billing. Standard at $2,040/yr,
              Professional at $5,100/yr.
            </p>
          </div>
          <div>
            <p className="text-gray-400 font-medium mb-1">Free Trial</p>
            <p className="text-gray-500">
              3 PDF uploads per company, no time limit. No credit card
              required.
            </p>
          </div>
        </div>
      </div>

      {/* CTA */}
      <div className="text-center">
        <a
          href="/trial"
          className="inline-block px-8 py-3 bg-primary-600 hover:bg-primary-500 rounded-lg text-sm font-semibold transition-colors"
        >
          Start Free Trial — 3 Uploads, No Card Required
        </a>
        <p className="mt-3 text-xs text-gray-600">
          Already have an account?{" "}
          <a
            href="/"
            className="text-gray-500 hover:text-gray-400 transition-colors"
          >
            Sign in
          </a>
        </p>
      </div>
    </div>
  );
}
