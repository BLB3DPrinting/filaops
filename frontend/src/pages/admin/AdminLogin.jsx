import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router-dom";
import { API_URL } from "../../config/api";
import logoFull from "../../assets/logo_full.png";
import logoBLB3D from "../../assets/logo_blb3d.svg";

export default function AdminLogin() {
  const navigate = useNavigate();
  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [checkingSetup, setCheckingSetup] = useState(true);
  const [apiError, setApiError] = useState(null);

  useEffect(() => {
    const checkSetupStatus = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/setup/status`);
        if (!res.ok) {
          throw new Error(`API returned ${res.status}`);
        }
        const data = await res.json();

        if (data.needs_setup) {
          // No users exist - redirect to onboarding
          navigate("/onboarding");
          return;
        }
      } catch {
        // Show connection error - this helps users diagnose VITE_API_URL issues
        setApiError(
          `Cannot connect to API at ${API_URL}. ` +
            (window.location.hostname !== "localhost" &&
            window.location.hostname !== "127.0.0.1"
              ? `If accessing remotely, ensure VITE_API_URL is set to the server's address (e.g., http://${window.location.hostname}:8000) and rebuild the frontend.`
              : "Please ensure the backend is running.")
        );
      } finally {
        setCheckingSetup(false);
      }
    };

    checkSetupStatus();
  }, [navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      // Login using OAuth2 form data format
      const formBody = new URLSearchParams();
      formBody.append("username", formData.email);
      formBody.append("password", formData.password);

      const res = await fetch(`${API_URL}/api/v1/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/x-www-form-urlencoded",
        },
        body: formBody,
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Login failed");
      }

      const data = await res.json();

      // In cookie mode, tokens are in httpOnly cookies — verify user via /me
      // In header mode (legacy), tokens are in the body
      let userData;
      if (data.user) {
        // Cookie mode: user info returned directly in login response
        userData = data.user;
      } else {
        // Header mode fallback: use access_token to call /me
        const meRes = await fetch(`${API_URL}/api/v1/auth/me`, {
          credentials: "include",
          headers: data.access_token
            ? { Authorization: `Bearer ${data.access_token}` }
            : {},
        });

        if (!meRes.ok) {
          throw new Error("Failed to verify user");
        }
        userData = await meRes.json();
      }

      if (!["admin", "operator"].includes(userData.account_type)) {
        throw new Error(
          "Access denied. Please use an admin or operator account."
        );
      }

      // Store non-sensitive user info for display (name, role, etc.)
      localStorage.setItem("adminUser", JSON.stringify(userData));

      // Redirect to admin dashboard
      navigate("/admin");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (checkingSetup) {
    return (
      <div className="min-h-screen flex items-center justify-center grid-pattern" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div style={{ color: 'var(--text-primary)' }}>Loading...</div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4 grid-pattern" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <div className="w-full max-w-md">
        {/* Dual Logos - BLB3D + FilaOps */}
        <div className="text-center mb-8">
          <Link to="/" className="inline-block">
            <div className="flex flex-col items-center gap-4">
              {/* BLB3D Logo with breathing glow */}
              <div className="logo-container">
                <img
                  src={logoBLB3D}
                  alt="BLB3D"
                  className="h-16 w-auto logo-breathe"
                />
              </div>
              {/* FilaOps Logo */}
              <img
                src={logoFull}
                alt="FilaOps"
                className="w-full max-w-xs mx-auto"
                style={{ filter: 'drop-shadow(0 0 25px rgba(2, 109, 248, 0.4))' }}
              />
            </div>
          </Link>
          <h1 className="text-2xl mt-6 font-display" style={{ color: 'var(--text-primary)' }}>Staff Login</h1>
          <p className="mt-2" style={{ color: 'var(--text-secondary)' }}>Sign in to access FilaOps ERP</p>
        </div>

        {/* API Connection Error */}
        {apiError && (
          <div className="rounded-xl p-4 mb-6" style={{ backgroundColor: 'rgba(238, 122, 8, 0.1)', border: '1px solid rgba(238, 122, 8, 0.3)' }}>
            <div className="flex items-start gap-3">
              <svg
                className="w-5 h-5 mt-0.5 flex-shrink-0"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                style={{ color: 'var(--accent)' }}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <div>
                <h3 className="font-medium" style={{ color: 'var(--accent)' }}>
                  Connection Issue
                </h3>
                <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>{apiError}</p>
              </div>
            </div>
          </div>
        )}

        {/* Login Form */}
        <div className="rounded-xl p-8" style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}>
          <form onSubmit={handleSubmit} className="space-y-6">
            {error && (
              <div className="rounded-lg p-4 text-sm" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#ef4444' }}>
                {error}
              </div>
            )}

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
                value={formData.email}
                onChange={(e) =>
                  setFormData({ ...formData, email: e.target.value })
                }
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

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium mb-2"
                style={{ color: 'var(--text-secondary)' }}
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                value={formData.password}
                onChange={(e) =>
                  setFormData({ ...formData, password: e.target.value })
                }
                required
                autoComplete="current-password"
                className="w-full rounded-lg px-4 py-3 placeholder-gray-500 focus:outline-none focus:ring-2 transition-all"
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-primary)',
                  '--tw-ring-color': 'var(--primary)'
                }}
                placeholder="Enter your password"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 rounded-lg font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              style={{
                background: 'linear-gradient(90deg, var(--primary), var(--primary-light))',
                color: 'white',
                boxShadow: loading ? 'none' : '0 0 20px -5px rgba(2, 109, 248, 0.5)'
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
                    ></circle>
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    ></path>
                  </svg>
                  Signing in...
                </span>
              ) : (
                "Sign In"
              )}
            </button>

            <div className="text-center">
              <Link
                to="/forgot-password"
                className="text-sm transition-colors"
                style={{ color: 'var(--primary)' }}
              >
                Forgot your password?
              </Link>
            </div>
          </form>
        </div>

        {/* Back link */}
        <div className="text-center mt-6">
          <Link
            to="/"
            className="text-sm transition-colors"
            style={{ color: 'var(--text-secondary)' }}
          ></Link>
        </div>
      </div>
    </div>
  );
}
