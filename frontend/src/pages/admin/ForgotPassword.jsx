/**
 * ForgotPassword - Request password reset
 *
 * Allows users to request a password reset by submitting their email.
 * The request will be sent to admin for approval.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";

export default function ForgotPassword() {
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [resetUrl, setResetUrl] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!email) {
      toast.error("Please enter your email address");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/auth/password-reset/request`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email }),
      });

      const data = await res.json();

      if (res.ok) {
        // If reset_url is provided, email is not configured - show link directly
        if (data.reset_url) {
          setSubmitted(true);
          setResetUrl(data.reset_url);
          toast.success("Password reset link generated!");
        } else {
          setSubmitted(true);
          toast.success(data.message || "Password reset request submitted");
        }
      } else {
        const errorMsg =
          data.detail ||
          data.message ||
          "Failed to submit password reset request";
        toast.error(errorMsg);
      }
    } catch {
      toast.error("Network error. Please check your connection and try again.");
    } finally {
      setLoading(false);
    }
  };

  if (submitted) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div className="w-full max-w-md">
          {/* Logo */}
          <div className="text-center mb-8">
            <Link
              to="/"
              className="text-3xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-500 bg-clip-text text-transparent"
            >
              FilaOps
            </Link>
          </div>

          {/* Success Message */}
          <div className="rounded-xl p-6" style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}>
            <div className="text-center">
              <div className="mx-auto flex items-center justify-center h-12 w-12 rounded-full bg-green-500/20 mb-4">
                <svg
                  className="h-6 w-6 text-green-400"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
              </div>
              <h2 className="text-xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
                {resetUrl ? "Password Reset Link Ready" : "Request Submitted"}
              </h2>
              {resetUrl ? (
                <>
                  <p className="mb-4" style={{ color: 'var(--text-secondary)' }}>
                    Your password reset link has been generated. Click the
                    button below to reset your password.
                  </p>
                  <div className="rounded-lg p-4 mb-4" style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)' }}>
                    <p className="text-xs mb-2" style={{ color: 'var(--text-secondary)' }}>Reset Link:</p>
                    <p className="text-sm break-all" style={{ color: 'var(--primary)' }}>
                      {window.location.origin}
                      {resetUrl}
                    </p>
                  </div>
                  <div className="flex gap-3">
                    <Link
                      to={resetUrl}
                      className="inline-block px-6 py-2 rounded-lg transition-all"
                      style={{ background: 'linear-gradient(90deg, #16a34a, #059669)', color: 'white' }}
                    >
                      Reset My Password
                    </Link>
                    <Link
                      to="/admin/login"
                      className="inline-block px-6 py-2 rounded-lg transition-all"
                      style={{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text-primary)', border: '1px solid var(--border-subtle)' }}
                    >
                      Back to Login
                    </Link>
                  </div>
                </>
              ) : (
                <>
                  <p className="mb-6" style={{ color: 'var(--text-secondary)' }}>
                    If an account exists with this email, a password reset
                    request has been submitted for review. An administrator will
                    review your request and you will receive an email with reset
                    instructions if approved.
                  </p>
                  <Link
                    to="/admin/login"
                    className="inline-block px-6 py-2 rounded-lg transition-all"
                    style={{ background: 'linear-gradient(90deg, var(--primary), var(--primary-light))', color: 'white' }}
                  >
                    Back to Login
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link
            to="/"
            className="text-3xl font-bold bg-gradient-to-r from-emerald-400 to-cyan-500 bg-clip-text text-transparent"
          >
            FilaOps
          </Link>
          <h1 className="text-xl mt-4" style={{ color: 'var(--text-primary)' }}>Reset Password</h1>
          <p className="mt-2" style={{ color: 'var(--text-secondary)' }}>
            Enter your email to request a password reset
          </p>
        </div>

        {/* Form */}
        <div className="rounded-xl p-6" style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium mb-2"
                style={{ color: 'var(--text-secondary)' }}
              >
                Email Address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                className="w-full rounded-lg px-4 py-3 placeholder-gray-500 focus:outline-none focus:ring-2 transition-all"
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-primary)',
                  '--tw-ring-color': 'var(--primary)'
                }}
                placeholder="admin@example.com"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-lg font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: 'linear-gradient(90deg, var(--primary), var(--primary-light))',
                color: 'white'
              }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg
                    className="animate-spin h-5 w-5"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Submitting...
                </span>
              ) : (
                "Submit Request"
              )}
            </button>

            <div className="text-center">
              <Link
                to="/admin/login"
                className="text-sm transition-colors"
                style={{ color: 'var(--primary)' }}
              >
                Back to Login
              </Link>
            </div>
          </form>

          {/* Info Box */}
          <div className="mt-6 rounded-lg p-4" style={{ backgroundColor: 'rgba(2, 109, 248, 0.1)', border: '1px solid rgba(2, 109, 248, 0.3)' }}>
            <div className="flex items-start gap-3">
              <svg
                className="w-5 h-5 mt-0.5 flex-shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                style={{ color: 'var(--primary)' }}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <div>
                <h3 className="font-medium mb-1" style={{ color: 'var(--primary)' }}>
                  Admin Approval Required
                </h3>
                <p className="text-sm" style={{ color: 'var(--primary-light)' }}>
                  Your password reset request will be reviewed by an
                  administrator. You will receive an email with reset
                  instructions if approved.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
