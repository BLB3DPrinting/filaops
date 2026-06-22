import { useState, useEffect } from "react";

// TODO: Re-enable after E2E tests stabilized
const DISABLED = true;

const PRO_FEATURES = [
  {
    icon: "💬",
    title: "Customer Quote Portal",
    description: "Let customers upload 3MF files and get instant quotes",
  },
  {
    icon: "🛒",
    title: "E-commerce Integrations",
    description: "Squarespace & WooCommerce webhooks for automatic order import",
  },
  {
    icon: "💳",
    title: "Payment Processing",
    description: "Stripe integration for seamless payment handling",
  },
  {
    icon: "📦",
    title: "Shipping Integrations",
    description: "USPS, FedEx, UPS API integration for label printing",
  },
  {
    icon: "📊",
    title: "Accounting Integrations",
    description: "QuickBooks, Xero, and more for financial sync",
  },
  {
    icon: "🖨️",
    title: "Printer Fleet Management",
    description: "Live monitoring and ML-powered print time estimation",
  },
];

export default function ProFeaturesAnnouncement() {
  const [isVisible, setIsVisible] = useState(false);
  // Initialize from localStorage to avoid setState in effect
  const [isDismissed, setIsDismissed] = useState(
    () => localStorage.getItem("proFeaturesDismissed") === "true"
  );

  useEffect(() => {
    // Check if user has dismissed this before
    const dismissed = localStorage.getItem("proFeaturesDismissed");
    if (!dismissed) {
      // Show after a short delay for better UX
      const timer = setTimeout(() => setIsVisible(true), 1000);
      return () => clearTimeout(timer);
    }
    // isDismissed is already initialized from localStorage
  }, []);

  const handleDismiss = (permanent = false) => {
    setIsVisible(false);
    if (permanent) {
      localStorage.setItem("proFeaturesDismissed", "true");
      setIsDismissed(true);
    }
  };

  if (DISABLED || isDismissed || !isVisible) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <div className="relative bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 border border-gray-700 rounded-2xl shadow-2xl max-w-4xl w-full mx-4 overflow-hidden">
        {/* Header */}
        <div className="bg-gradient-to-r from-blue-600 to-purple-600 p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white">
                🚀 FilaOps Pro - Coming 2026
              </h2>
              <p className="text-blue-100 mt-1">
                Unlock powerful features for your print farm
              </p>
            </div>
            <button
              onClick={() => handleDismiss(false)}
              className="text-white/80 hover:text-white transition-colors p-2 hover:bg-white/10 rounded-lg"
              aria-label="Close"
            >
              <svg
                className="w-6 h-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 max-h-[60vh] overflow-y-auto">
          <p className="text-gray-300 mb-6 text-center">
            You're using <span className="font-semibold text-blue-400">FilaOps Core</span> - 
            the open source ERP foundation. Pro features are coming in 2026!
          </p>

          {/* Features Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            {PRO_FEATURES.map((feature, idx) => (
              <div
                key={idx}
                className="bg-gray-800/50 border border-gray-700 rounded-lg p-4 hover:border-blue-500/50 transition-colors"
              >
                <div className="flex items-start gap-3">
                  <span className="text-3xl">{feature.icon}</span>
                  <div>
                    <h3 className="font-semibold text-white mb-1">
                      {feature.title}
                    </h3>
                    <p className="text-sm text-gray-400">
                      {feature.description}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Comparison */}
          <div className="bg-gray-800/30 border border-gray-700 rounded-lg p-4 mb-6">
            <h3 className="font-semibold text-white mb-3 text-center">
              What You Get Now vs. Pro
            </h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <h4 className="text-blue-400 font-medium mb-2">✅ Core (Now)</h4>
                <ul className="text-gray-400 space-y-1">
                  <li>• Products, BOMs, Inventory</li>
                  <li>• Sales & Production Orders</li>
                  <li>• MRP & Work Centers</li>
                  <li>• Admin Dashboard</li>
                  <li>• Traceability</li>
                </ul>
              </div>
              <div>
                <h4 className="text-purple-400 font-medium mb-2">🚀 Pro (2026)</h4>
                <ul className="text-gray-400 space-y-1">
                  <li>• Everything in Core</li>
                  <li>• Customer Portal</li>
                  <li>• E-commerce Integrations</li>
                  <li>• Payment & Shipping</li>
                  <li>• Printer Fleet Management</li>
                </ul>
              </div>
            </div>
          </div>

          {/* CTA */}
          <div className="text-center">
            <p className="text-gray-400 text-sm mb-4">
              Want to be notified when Pro launches?
            </p>
            <a
              href="https://github.com/BLB3DPrinting/filaops/discussions"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-block px-6 py-2 bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg hover:from-blue-500 hover:to-purple-500 transition-all font-medium"
            >
              Join the Discussion
            </a>
          </div>
        </div>

        {/* Footer */}
        <div className="bg-gray-800/50 border-t border-gray-700 px-6 py-4 flex items-center justify-between">
          <button
            onClick={() => handleDismiss(true)}
            className="text-gray-400 hover:text-gray-300 text-sm transition-colors"
          >
            Don't show this again
          </button>
          <button
            onClick={() => handleDismiss(false)}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors font-medium"
          >
            Got it, thanks!
          </button>
        </div>
      </div>
    </div>
  );
}

