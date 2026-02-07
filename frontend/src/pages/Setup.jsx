/**
 * First-Run Setup Page
 * 
 * Shown when no admin user exists. Allows creating the initial admin account.
 * Redirects to login/dashboard once setup is complete.
 */
import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { API_URL } from "../config/api";

export default function Setup() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  
  const [formData, setFormData] = useState({
    email: "",
    password: "",
    confirmPassword: "",
    full_name: "",
    company_name: ""
  });

  // Check if setup is needed
  useEffect(() => {
    checkSetupStatus();
  }, []);

  const checkSetupStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/setup/status`);
      const data = await res.json();
      
      if (data.needs_setup) {
        setNeedsSetup(true);
      } else {
        // Already set up - redirect to login
        navigate("/admin/login");
      }
    } catch {
      setError("Cannot connect to server. Please ensure FilaOps is running.");
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
    setError(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    // Validate passwords match
    if (formData.password !== formData.confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    // Validate password strength
    if (formData.password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (!/[A-Z]/.test(formData.password)) {
      setError("Password must contain at least one uppercase letter");
      return;
    }
    if (!/[a-z]/.test(formData.password)) {
      setError("Password must contain at least one lowercase letter");
      return;
    }
    if (!/\d/.test(formData.password)) {
      setError("Password must contain at least one number");
      return;
    }
    if (!/[!@#$%^&*(),.?":{}|<>_\-+=[\]\\/`~]/.test(formData.password)) {
      setError("Password must contain at least one special character (!@#$%^&*)");
      return;
    }

    setSubmitting(true);

    try {
      const res = await fetch(`${API_URL}/api/v1/setup/initial-admin`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: formData.email,
          password: formData.password,
          full_name: formData.full_name,
          company_name: formData.company_name
        })
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Setup failed");
      }

      // Token is now in an httpOnly cookie (or in body for header mode)
      // Fetch and store user data so AdminLayout knows the user is an admin
      try {
        const meRes = await fetch(`${API_URL}/api/v1/auth/me`, {
          credentials: "include",
          headers: data.access_token
            ? { Authorization: `Bearer ${data.access_token}` }
            : {},
        });
        if (meRes.ok) {
          const userData = await meRes.json();
          localStorage.setItem("adminUser", JSON.stringify(userData));
        }
      } catch {
        // If this fails, user will be treated as non-admin until re-login
      }

      // Redirect to dashboard
      navigate("/admin");
      
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-white">Checking setup status...</div>
      </div>
    );
  }

  if (!needsSetup) {
    return null; // Will redirect
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        {/* Logo/Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">
            Welcome to FilaOps
          </h1>
          <p className="text-gray-400">
            Create your admin account to get started
          </p>
        </div>

        {/* Setup Form */}
        <form onSubmit={handleSubmit} className="bg-gray-900 border border-gray-800 rounded-xl p-6 space-y-4">
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
              {error}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Your Name
            </label>
            <input
              type="text"
              name="full_name"
              value={formData.full_name}
              onChange={handleChange}
              required
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
              placeholder="John Smith"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Email Address
            </label>
            <input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleChange}
              required
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
              placeholder="you@yourcompany.com"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Password
            </label>
            <input
              type="password"
              name="password"
              value={formData.password}
              onChange={handleChange}
              required
              minLength={8}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
              placeholder="••••••••"
            />
            <ul className="text-xs text-gray-500 mt-1 space-y-0.5">
              <li>• At least 8 characters</li>
              <li>• Uppercase and lowercase letters</li>
              <li>• At least one number</li>
              <li>• At least one special character (!@#$%^&*)</li>
            </ul>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Confirm Password
            </label>
            <input
              type="password"
              name="confirmPassword"
              value={formData.confirmPassword}
              onChange={handleChange}
              required
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
              placeholder="••••••••"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Company Name <span className="text-gray-500">(optional)</span>
            </label>
            <input
              type="text"
              name="company_name"
              value={formData.company_name}
              onChange={handleChange}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
              placeholder="Your Print Farm"
            />
          </div>

          <button
            type="submit"
            disabled={submitting}
            className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? "Creating Account..." : "Create Admin Account"}
          </button>
        </form>

        {/* Footer */}
        <p className="text-center text-gray-500 text-sm mt-6">
          This creates the first admin account for your FilaOps installation.
        </p>
      </div>
    </div>
  );
}
