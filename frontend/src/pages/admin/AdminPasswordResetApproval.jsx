import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { API_URL } from "../../config/api";

export default function AdminPasswordResetApproval() {
  const { action, token } = useParams();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [confirmed, setConfirmed] = useState(false);

  const isApprove = action === "approve";

  const processApproval = async () => {
    setLoading(true);
    setError(null);
    try {
      const endpoint = isApprove
        ? `${API_URL}/api/v1/auth/password-reset/approve`
        : `${API_URL}/api/v1/auth/password-reset/deny`;

      const res = await fetch(endpoint, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approval_token: token }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to process request");
      }

      const data = await res.json();
      setResult(data);
      setConfirmed(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
        <div className="w-full max-w-md text-center">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-8">
            <div className="w-16 h-16 bg-red-500/20 rounded-full flex items-center justify-center mx-auto mb-6">
              <svg className="w-8 h-8 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h1 className="text-2xl font-bold text-white mb-4">Error</h1>
            <p className="text-gray-400 mb-6">{error}</p>
            <Link
              to="/admin"
              className="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Go to Admin Dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Show confirmation result
  if (confirmed && result) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
        <div className="w-full max-w-md text-center">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-8">
            <div className={`w-16 h-16 ${isApprove ? 'bg-green-500/20' : 'bg-red-500/20'} rounded-full flex items-center justify-center mx-auto mb-6`}>
              {isApprove ? (
                <svg className="w-8 h-8 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="w-8 h-8 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              )}
            </div>

            <h1 className="text-2xl font-bold text-white mb-4">
              Password Reset {isApprove ? "Approved" : "Denied"}
            </h1>

            <div className="bg-gray-800 rounded-lg p-4 mb-6 text-left">
              <div className="text-sm">
                <p className="text-gray-400">User Email:</p>
                <p className="text-white font-medium">{result?.user_email}</p>
              </div>
              <div className="text-sm mt-3">
                <p className="text-gray-400">Status:</p>
                <p className={`font-medium ${isApprove ? 'text-green-400' : 'text-red-400'}`}>
                  {result?.status?.toUpperCase()}
                </p>
              </div>
            </div>

            <p className="text-gray-400 mb-6">
              {isApprove
                ? "The user has been notified and can now reset their password."
                : "The user has been notified that their request was denied."}
            </p>

            <Link
              to="/admin"
              className="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Go to Admin Dashboard
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Confirmation prompt — ask admin to confirm before making the POST
  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-950 px-4">
      <div className="w-full max-w-md text-center">
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8">
          <div className={`w-16 h-16 ${isApprove ? 'bg-blue-500/20' : 'bg-orange-500/20'} rounded-full flex items-center justify-center mx-auto mb-6`}>
            <svg className={`w-8 h-8 ${isApprove ? 'text-blue-400' : 'text-orange-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>

          <h1 className="text-2xl font-bold text-white mb-4">
            {isApprove ? "Approve" : "Deny"} Password Reset?
          </h1>

          <p className="text-gray-400 mb-8">
            {isApprove
              ? "This will allow the user to reset their password. They will receive a reset link via email."
              : "This will deny the password reset request. The user will be notified."}
          </p>

          <div className="flex gap-3 justify-center">
            <Link
              to="/admin"
              className="px-6 py-3 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
            >
              Cancel
            </Link>
            <button
              onClick={processApproval}
              disabled={loading}
              className={`px-6 py-3 text-white rounded-lg font-medium disabled:opacity-50 ${
                isApprove
                  ? "bg-green-600 hover:bg-green-700"
                  : "bg-red-600 hover:bg-red-700"
              }`}
            >
              {loading
                ? "Processing..."
                : isApprove
                  ? "Approve Reset"
                  : "Deny Reset"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
