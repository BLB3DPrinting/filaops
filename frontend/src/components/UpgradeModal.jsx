/**
 * UpgradeModal - Shows when user hits a tier limit
 *
 * Displays upgrade options when a feature/resource limit is reached.
 */
import { useState, useEffect } from "react";
import { on } from "../lib/events";
import Modal from "./Modal";

export default function UpgradeModal() {
  const [isOpen, setIsOpen] = useState(false);
  const [limitInfo, setLimitInfo] = useState(null);

  useEffect(() => {
    return on("tier:limit-reached", (info) => {
      setLimitInfo(info);
      setIsOpen(true);
    });
  }, []);

  const resourceName = limitInfo?.resource?.replace("_", " ") || "resource";
  const limit = limitInfo?.limit || 0;
  const current = limitInfo?.current || 0;

  return (
    <Modal isOpen={isOpen && !!limitInfo} onClose={() => setIsOpen(false)} title="Upgrade to Pro" className="max-w-md w-full">
        {/* Header */}
        <div className="p-6 border-b border-gray-700">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-full bg-yellow-500/20 flex items-center justify-center">
              <svg
                className="w-6 h-6 text-yellow-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
            </div>
            <div>
              <h2 className="text-xl font-semibold text-white">
                Upgrade to Pro
              </h2>
              <p className="text-sm text-gray-400">
                You've reached a limit
              </p>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-6">
          <p className="text-gray-300 mb-4">
            You've reached the <span className="text-white font-medium">{resourceName}</span> limit
            ({current}/{limit}) for the Community tier.
          </p>

          <div className="bg-gray-800 rounded-lg p-4 mb-6">
            <h3 className="text-white font-medium mb-2">Pro includes:</h3>
            <ul className="text-sm text-gray-400 space-y-2">
              <li className="flex items-center gap-2">
                <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Unlimited users
              </li>
              <li className="flex items-center gap-2">
                <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Unlimited printers
              </li>
              <li className="flex items-center gap-2">
                <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Customer quote portal
              </li>
              <li className="flex items-center gap-2">
                <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Advanced BOM features
              </li>
              <li className="flex items-center gap-2">
                <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                QuickBooks integration
              </li>
            </ul>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => setIsOpen(false)}
              className="flex-1 px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              Maybe Later
            </button>
            <a
              href="https://filaops.com/pricing"
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-center"
            >
              View Plans
            </a>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-800/50 border-t border-gray-700 rounded-b-xl">
          <p className="text-xs text-gray-500 text-center">
            Starting at $29/user/month (2 seat minimum)
          </p>
        </div>
    </Modal>
  );
}
