/**
 * First-Time Onboarding Wizard
 *
 * Multi-step wizard for new FilaOps installations:
 * 1. Admin account creation (+ currency / locale)
 * 2. Load example data
 * 3. CSV import for products
 * 4. CSV import for customers
 * 5. CSV import for orders
 * 6. CSV import for inventory (optional)
 * 7. Connect your first printer (optional)
 * 8. Complete - redirect to dashboard
 */
import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { API_URL } from "../config/api";

const STEPS = {
  ACCOUNT: 1,
  EXAMPLE_DATA: 2,
  PRODUCTS: 3,
  CUSTOMERS: 4,
  ORDERS: 5,
  INVENTORY: 6,
  PRINTER: 7,
  COMPLETE: 8,
};

// Community-tier brands (no PRO required).  Must stay in sync with
// _CORE_BRAND_CODES in backend/app/api/v1/endpoints/printers.py.
const COMMUNITY_BRANDS = [
  { value: "generic", label: "Generic / Other" },
  { value: "bambulab", label: "Bambu Lab" },
];

// Common currency options surfaced in the onboarding wizard.
// Full list is available in Admin → Settings after first login.
const COMMON_CURRENCIES = [
  { code: "USD", label: "USD — US Dollar" },
  { code: "CAD", label: "CAD — Canadian Dollar" },
  { code: "EUR", label: "EUR — Euro" },
  { code: "GBP", label: "GBP — British Pound" },
  { code: "AUD", label: "AUD — Australian Dollar" },
  { code: "NZD", label: "NZD — New Zealand Dollar" },
  { code: "JPY", label: "JPY — Japanese Yen" },
  { code: "MXN", label: "MXN — Mexican Peso" },
  { code: "BRL", label: "BRL — Brazilian Real" },
  { code: "INR", label: "INR — Indian Rupee" },
];

// Common BCP-47 locale options.
const COMMON_LOCALES = [
  { code: "en-US", label: "English (United States)" },
  { code: "en-CA", label: "English (Canada)" },
  { code: "en-GB", label: "English (United Kingdom)" },
  { code: "en-AU", label: "English (Australia)" },
  { code: "en-NZ", label: "English (New Zealand)" },
  { code: "fr-CA", label: "French (Canada)" },
  { code: "fr-FR", label: "French (France)" },
  { code: "de-DE", label: "German (Germany)" },
  { code: "es-MX", label: "Spanish (Mexico)" },
  { code: "es-ES", label: "Spanish (Spain)" },
  { code: "pt-BR", label: "Portuguese (Brazil)" },
  { code: "ja-JP", label: "Japanese (Japan)" },
];

export default function Onboarding() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(STEPS.ACCOUNT);
  const advanceTimeoutRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [error, setError] = useState(null);

  // Step 1: Admin account + currency/locale
  const [accountData, setAccountData] = useState({
    email: "",
    password: "",
    confirmPassword: "",
    full_name: "",
    company_name: "",
    currency_code: "USD",
    locale: "en-US",
  });
  const [submittingAccount, setSubmittingAccount] = useState(false);

  // Step 2: Example data
  const [seedExampleData, setSeedExampleData] = useState(true);
  const [seedingData, setSeedingData] = useState(false);
  const [seedResult, setSeedResult] = useState(null);

  // Step 3: Products CSV
  const [productsFile, setProductsFile] = useState(null);
  const [productsResult, setProductsResult] = useState(null);
  const [importingProducts, setImportingProducts] = useState(false);

  // Step 4: Customers CSV
  const [customersFile, setCustomersFile] = useState(null);
  const [customersResult, setCustomersResult] = useState(null);
  const [importingCustomers, setImportingCustomers] = useState(false);

  // Step 5: Orders CSV (optional)
  const [ordersFile, setOrdersFile] = useState(null);
  const [ordersResult, setOrdersResult] = useState(null);
  const [importingOrders, setImportingOrders] = useState(false);
  const [ordersSource, setOrdersSource] = useState("manual");

  // Step 6: Inventory CSV (optional)
  const [inventoryFile, setInventoryFile] = useState(null);
  const [inventoryResult, setInventoryResult] = useState(null);
  const [importingInventory, setImportingInventory] = useState(false);

  // Step 7: Printer (optional)
  const [printerData, setPrinterData] = useState({
    name: "",
    brand: "generic",
    model: "",
  });
  const [printerResult, setPrinterResult] = useState(null);
  const [savingPrinter, setSavingPrinter] = useState(false);

  // Auth token from step 1 — used as Authorization header for subsequent steps
  // (cookies alone are unreliable through nginx proxies in Docker)
  const [setupToken, setSetupToken] = useState(null);

  useEffect(() => {
    checkSetupStatus();
    return () => {
      if (advanceTimeoutRef.current) {
        clearTimeout(advanceTimeoutRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scheduleAdvance = (nextStep) => {
    if (advanceTimeoutRef.current) {
      clearTimeout(advanceTimeoutRef.current);
    }
    advanceTimeoutRef.current = setTimeout(() => {
      setCurrentStep(nextStep);
    }, 2000);
  };

  const checkSetupStatus = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/setup/status`);
      const data = await res.json();

      if (data.needs_setup) {
        setNeedsSetup(true);
      } else {
        navigate("/admin/login");
      }
    } catch {
      setError("Cannot connect to server. Please ensure FilaOps is running.");
    } finally {
      setLoading(false);
    }
  };

  const handleAccountChange = (e) => {
    setAccountData({ ...accountData, [e.target.name]: e.target.value });
    setError(null);
  };

  const validatePassword = (password) => {
    if (password.length < 8) return "Password must be at least 8 characters";
    if (!/[A-Z]/.test(password))
      return "Password must contain at least one uppercase letter";
    if (!/[a-z]/.test(password))
      return "Password must contain at least one lowercase letter";
    if (!/\d/.test(password))
      return "Password must contain at least one number";
    if (!/[!@#$%^&*(),.?":{}|<>_\-+=[\]\\/`~]/.test(password)) {
      return "Password must contain at least one special character (!@#$%^&*)";
    }
    return null;
  };

  const handleCreateAccount = async (e) => {
    e.preventDefault();
    setError(null);

    if (accountData.password !== accountData.confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    const passwordError = validatePassword(accountData.password);
    if (passwordError) {
      setError(passwordError);
      return;
    }

    setSubmittingAccount(true);

    try {
      const res = await fetch(`${API_URL}/api/v1/setup/initial-admin`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: accountData.email,
          password: accountData.password,
          full_name: accountData.full_name,
          company_name: accountData.company_name,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Setup failed");
      }

      // Save short-lived setup token (5 min) for subsequent wizard steps.
      // The full-duration token is in the httpOnly cookie; this one is just
      // for the wizard to use as an Authorization header through nginx.
      const token = data.setup_token || data.access_token;
      if (token) {
        setSetupToken(token);
      }

      // Fetch and store user data so AdminLayout knows the user is an admin
      try {
        const meRes = await fetch(`${API_URL}/api/v1/auth/me`, {
          credentials: "include",
          headers: token
            ? { Authorization: `Bearer ${token}` }
            : {},
        });
        if (meRes.ok) {
          const userData = await meRes.json();
          localStorage.setItem("adminUser", JSON.stringify(userData));
        }
      } catch {
        // If this fails, user will be treated as non-admin until re-login
      }

      // Persist currency + locale to company settings immediately after
      // account creation while we still have the setup token.
      try {
        await fetch(`${API_URL}/api/v1/settings/company`, {
          method: "PATCH",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            currency_code: accountData.currency_code || "USD",
            locale: accountData.locale || "en-US",
          }),
        });
      } catch {
        // Non-critical — operator can update in Settings later
      }

      // Move to next step (example data)
      setCurrentStep(STEPS.EXAMPLE_DATA);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmittingAccount(false);
    }
  };

  const handleSeedExampleData = async () => {
    if (!seedExampleData) {
      // Skip this step
      setCurrentStep(STEPS.PRODUCTS);
      return;
    }

    setSeedingData(true);
    setError(null);

    try {
      const res = await fetch(`${API_URL}/api/v1/setup/seed-example-data`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(setupToken ? { Authorization: `Bearer ${setupToken}` } : {}),
        },
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Seeding failed");
      }

      setSeedResult(data);
      scheduleAdvance(STEPS.PRODUCTS);
    } catch (err) {
      setError(err.message);
    } finally {
      setSeedingData(false);
    }
  };

  const handleProductsImport = async () => {
    if (!productsFile) {
      // Skip this step - no file selected
      setCurrentStep(STEPS.CUSTOMERS);
      return;
    }

    setImportingProducts(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", productsFile);

      const res = await fetch(`${API_URL}/api/v1/items/import`, {
        method: "POST",
        headers: setupToken ? { Authorization: `Bearer ${setupToken}` } : {},
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Import failed");
      }

      setProductsResult(data);
      scheduleAdvance(STEPS.CUSTOMERS);
    } catch (err) {
      setError(err.message);
    } finally {
      setImportingProducts(false);
    }
  };

  const handleCustomersImport = async () => {
    if (!customersFile) {
      // Skip this step - no file selected
      setCurrentStep(STEPS.ORDERS);
      return;
    }

    setImportingCustomers(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", customersFile);

      const res = await fetch(`${API_URL}/api/v1/admin/customers/import`, {
        method: "POST",
        headers: setupToken ? { Authorization: `Bearer ${setupToken}` } : {},
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Import failed");
      }

      setCustomersResult(data);
      scheduleAdvance(STEPS.ORDERS);
    } catch (err) {
      setError(err.message);
    } finally {
      setImportingCustomers(false);
    }
  };

  const handleOrdersImport = async () => {
    if (!ordersFile) {
      // Skip this step - no file selected
      setCurrentStep(STEPS.INVENTORY);
      return;
    }

    setImportingOrders(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", ordersFile);

      const params = new URLSearchParams();
      params.set("create_customers", "true");
      params.set("source", ordersSource);

      const url = `${API_URL}/api/v1/admin/orders/import?${params}`;

      const res = await fetch(url, {
        method: "POST",
        headers: setupToken ? { Authorization: `Bearer ${setupToken}` } : {},
        body: formData,
      });

      if (!res.ok) {
        let errorMessage = "Import failed";
        try {
          const errorData = await res.json();
          errorMessage = errorData.detail || errorData.message || errorMessage;
        } catch {
          errorMessage = `Server error: ${res.status} ${res.statusText}`;
        }
        throw new Error(errorMessage);
      }

      const data = await res.json();

      setOrdersResult(data);
      scheduleAdvance(STEPS.INVENTORY);
    } catch (err) {
      setError(err.message);
    } finally {
      setImportingOrders(false);
    }
  };

  const handleInventoryImport = async () => {
    if (!inventoryFile) {
      setCurrentStep(STEPS.PRINTER);
      return;
    }

    setImportingInventory(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", inventoryFile);

      const res = await fetch(`${API_URL}/api/v1/admin/import/inventory`, {
        method: "POST",
        headers: setupToken ? { Authorization: `Bearer ${setupToken}` } : {},
        body: formData,
      });

      if (!res.ok) {
        let errorMessage = "Import failed";
        try {
          const errorData = await res.json();
          errorMessage = errorData.detail || errorData.message || errorMessage;
        } catch {
          errorMessage = `Server error: ${res.status} ${res.statusText}`;
        }
        throw new Error(errorMessage);
      }

      const data = await res.json();

      setInventoryResult(data);
      scheduleAdvance(STEPS.PRINTER);
    } catch (err) {
      setError(err.message);
    } finally {
      setImportingInventory(false);
    }
  };

  /**
   * Step 7: Create a printer.
   *
   * Minimal payload — name + brand + model (all required by PrinterCreate).
   * The code is auto-generated server-side via GET /printers/generate-code
   * before the POST so we always supply a valid unique code.
   *
   * Only Community-tier brands (bambulab, generic) are offered here;
   * Klipper / OctoPrint / Prusa / Creality require PRO and can be added
   * from Admin → Printers after first login.
   */
  const handleAddPrinter = async () => {
    const { name, brand, model } = printerData;

    if (!name.trim() || !model.trim()) {
      setError("Printer name and model are required.");
      return;
    }

    setSavingPrinter(true);
    setError(null);

    try {
      // Auto-generate a printer code
      const prefix = brand === "generic" ? "PRT" : brand.toUpperCase().slice(0, 3);
      const codeRes = await fetch(
        `${API_URL}/api/v1/printers/generate-code?prefix=${prefix}`,
        {
          credentials: "include",
          headers: setupToken ? { Authorization: `Bearer ${setupToken}` } : {},
        }
      );
      let printerCode = `${prefix}-001`;
      if (codeRes.ok) {
        const codeData = await codeRes.json();
        printerCode = codeData.code;
      } else {
        // Code gen failed — fall back to a safe default.
        // The backend enforces duplicate-code uniqueness (400), so the POST
        // will surface a clear error to the user if the fallback is taken.
        // eslint-disable-next-line no-console
        console.warn(
          `[Onboarding] /printers/generate-code returned ${codeRes.status}; using fallback ${printerCode}`,
        );
      }

      const res = await fetch(`${API_URL}/api/v1/printers/`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(setupToken ? { Authorization: `Bearer ${setupToken}` } : {}),
        },
        body: JSON.stringify({
          code: printerCode,
          name: name.trim(),
          brand,
          model: model.trim(),
          active: true,
          connection_config: {},
          capabilities: {},
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "Failed to add printer");
      }

      setPrinterResult(data);
      scheduleAdvance(STEPS.COMPLETE);
    } catch (err) {
      setError(err.message);
    } finally {
      setSavingPrinter(false);
    }
  };

  const skipPrinterStep = () => {
    setCurrentStep(STEPS.COMPLETE);
  };

  const prevStep = () => {
    if (currentStep > STEPS.ACCOUNT) {
      if (advanceTimeoutRef.current) {
        clearTimeout(advanceTimeoutRef.current);
        advanceTimeoutRef.current = null;
      }
      setCurrentStep(currentStep - 1);
      setError(null);
    }
  };

  const handleComplete = () => {
    navigate("/admin");
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div style={{ color: 'var(--text-primary)' }}>Checking setup status...</div>
      </div>
    );
  }

  if (!needsSetup) {
    return null;
  }

  const getStepTitle = () => {
    switch (currentStep) {
      case STEPS.ACCOUNT:
        return "Create Admin Account";
      case STEPS.EXAMPLE_DATA:
        return "Load Example Data";
      case STEPS.PRODUCTS:
        return "Import Products";
      case STEPS.CUSTOMERS:
        return "Import Customers";
      case STEPS.ORDERS:
        return "Import Orders";
      case STEPS.INVENTORY:
        return "Import Inventory (Optional)";
      case STEPS.PRINTER:
        return "Connect Your First Printer";
      case STEPS.COMPLETE:
        return "Setup Complete!";
      default:
        return "Welcome to FilaOps";
    }
  };

  const getStepNumber = () => {
    return currentStep;
  };

  const getTotalSteps = () => {
    return 8;
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <div className="max-w-2xl w-full">
        {/* Progress Bar */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              Step {getStepNumber()} of {getTotalSteps()}
            </span>
            <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
              {Math.round((getStepNumber() / getTotalSteps()) * 100)}%
            </span>
          </div>
          <div className="w-full rounded-full h-2" style={{ backgroundColor: 'var(--bg-secondary)' }}>
            <div
              className="h-2 rounded-full transition-all duration-300"
              style={{ backgroundColor: 'var(--primary)', width: `${(getStepNumber() / getTotalSteps()) * 100}%` }}
            />
          </div>
        </div>

        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
            {getStepTitle()}
          </h1>
          <p style={{ color: 'var(--text-secondary)' }}>
            {currentStep === STEPS.ACCOUNT &&
              "Create your admin account to get started"}
            {currentStep === STEPS.EXAMPLE_DATA &&
              "Load example items and materials to help you get started"}
            {currentStep === STEPS.PRODUCTS &&
              "Upload a CSV file with your products, or skip to add them later"}
            {currentStep === STEPS.CUSTOMERS &&
              "Upload a CSV file with your customers, or skip to add them later"}
            {currentStep === STEPS.ORDERS &&
              "Upload a CSV file with your orders from your e-commerce platform, or skip to add them later"}
            {currentStep === STEPS.INVENTORY &&
              "Upload a CSV file with your inventory levels, or skip to add them later"}
            {currentStep === STEPS.PRINTER &&
              "Add your first printer, or skip to set up your fleet later"}
            {currentStep === STEPS.COMPLETE &&
              "You're all set! Start managing your print farm."}
          </p>
        </div>

        {/* Error Display */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm mb-6">
            {error}
          </div>
        )}

        {/* Step Content */}
        <div className="rounded-xl p-6" style={{ backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-subtle)' }}>
          {/* Step 1: Account Creation + Currency/Locale */}
          {currentStep === STEPS.ACCOUNT && (
            <form onSubmit={handleCreateAccount} className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-1"
                style={{ color: 'var(--text-secondary)' }}>
                  Your Name
                </label>
                <input
                  type="text"
                  name="full_name"
                  value={accountData.full_name}
                  onChange={handleAccountChange}
                  required
                  className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)'
                  }}
                  placeholder="John Smith"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1"
                style={{ color: 'var(--text-secondary)' }}>
                  Email Address
                </label>
                <input
                  type="email"
                  name="email"
                  value={accountData.email}
                  onChange={handleAccountChange}
                  required
                  className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)'
                  }}
                  placeholder="you@yourcompany.com"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1"
                style={{ color: 'var(--text-secondary)' }}>
                  Password
                </label>
                <input
                  type="password"
                  name="password"
                  value={accountData.password}
                  onChange={handleAccountChange}
                  required
                  minLength={8}
                  className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)'
                  }}
                  placeholder="••••••••"
                />
                <ul className="text-xs mt-1 space-y-0.5"
                style={{ color: 'var(--text-secondary)' }}>
                  <li>• At least 8 characters</li>
                  <li>• Uppercase and lowercase letters</li>
                  <li>• At least one number</li>
                  <li>• At least one special character</li>
                </ul>
              </div>

              <div>
                <label className="block text-sm font-medium mb-1"
                style={{ color: 'var(--text-secondary)' }}>
                  Confirm Password
                </label>
                <input
                  type="password"
                  name="confirmPassword"
                  value={accountData.confirmPassword}
                  onChange={handleAccountChange}
                  required
                  className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)'
                  }}
                  placeholder="••••••••"
                />
              </div>

              <div>
                <label className="block text-sm font-medium mb-1"
                style={{ color: 'var(--text-secondary)' }}>
                  Company Name <span style={{ color: 'var(--text-secondary)' }}>(optional)</span>
                </label>
                <input
                  type="text"
                  name="company_name"
                  value={accountData.company_name}
                  onChange={handleAccountChange}
                  className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)'
                  }}
                  placeholder="Your Print Farm"
                />
              </div>

              {/* Currency & Locale — affects invoices and number formatting */}
              <div className="pt-2 border-t" style={{ borderColor: 'var(--border-subtle)' }}>
                <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>
                  These settings control how money and dates appear on invoices and reports.
                  You can change them later in Admin → Settings.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-sm font-medium mb-1"
                    style={{ color: 'var(--text-secondary)' }}>
                      Currency
                    </label>
                    <select
                      name="currency_code"
                      value={accountData.currency_code}
                      onChange={handleAccountChange}
                      className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                      style={{
                        backgroundColor: 'var(--bg-secondary)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-primary)'
                      }}
                    >
                      {COMMON_CURRENCIES.map((c) => (
                        <option key={c.code} value={c.code}>{c.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1"
                    style={{ color: 'var(--text-secondary)' }}>
                      Locale
                    </label>
                    <select
                      name="locale"
                      value={accountData.locale}
                      onChange={handleAccountChange}
                      className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                      style={{
                        backgroundColor: 'var(--bg-secondary)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-primary)'
                      }}
                    >
                      {COMMON_LOCALES.map((l) => (
                        <option key={l.code} value={l.code}>{l.label}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <button
                type="submit"
                disabled={submittingAccount}
                className="w-full py-3 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                style={{
                  background: 'linear-gradient(90deg, var(--primary), var(--primary-light))',
                  color: 'white'
                }}
              >
                {submittingAccount
                  ? "Creating Account..."
                  : "Create Account & Continue"}
              </button>
            </form>
          )}

          {/* Step 2: Example Data */}
          {currentStep === STEPS.EXAMPLE_DATA && (
            <div className="space-y-6">
              <div className="rounded-lg p-4" style={{ backgroundColor: 'rgba(2, 109, 248, 0.1)', border: '1px solid rgba(2, 109, 248, 0.3)' }}>
                <h3 className="font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
                  Load BambuLab Materials &amp; Example Data?
                </h3>
                <p className="text-sm mb-4" style={{ color: 'var(--text-secondary)' }}>
                  We can populate your database with BambuLab-compatible materials:
                </p>
                <ul className="text-sm space-y-2 mb-4" style={{ color: 'var(--text-primary)' }}>
                  <li>
                    • <strong>18 material types</strong> (PLA Basic, PLA Matte, PLA Silk, PETG, ABS, ASA, TPU, PA-CF, PC)
                  </li>
                  <li>
                    • <strong>15 colors</strong> (Black, White, Gray, Red, Blue, Green, Yellow, Orange, Purple, Pink, Brown, Gold, Silver, Clear)
                  </li>
                  <li>
                    • <strong>24 material+color combinations</strong> ready to use for common filaments
                  </li>
                  <li>• Example items for each category (packaging, hardware, finished goods)</li>
                </ul>
                <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  This gives you a head start with ready-to-use material options. You can always add more materials and colors later!
                </p>
              </div>

              {!seedExampleData && (
                <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4">
                  <h4 className="text-yellow-400 font-medium mb-2">Skipping seed data?</h4>
                  <p className="text-yellow-200/70 text-sm">
                    Without seed data, you'll need to manually create colors when adding materials.
                    Use the <strong>"+ Create new color for this material"</strong> link in the material form to add colors as needed.
                  </p>
                </div>
              )}

              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="seedData"
                  checked={seedExampleData}
                  onChange={(e) => setSeedExampleData(e.target.checked)}
                  className="w-5 h-5 rounded"
                  style={{
                    borderColor: 'var(--border-subtle)',
                    backgroundColor: 'var(--bg-secondary)',
                    accentColor: 'var(--primary)'
                  }}
                />
                <label
                  htmlFor="seedData"
                  className="cursor-pointer"
                  style={{ color: 'var(--text-primary)' }}
                >
                  Yes, load example data (recommended)
                </label>
              </div>

              {seedResult && (
                <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                  <div className="text-green-400 font-medium mb-2">
                    Example data loaded successfully!
                  </div>
                  <div className="text-sm space-y-1" style={{ color: 'var(--text-primary)' }}>
                    <div>
                      • {seedResult.items_created} example items created
                    </div>
                    <div>
                      • {seedResult.materials_created} material types added
                      (BambuLab compatible)
                    </div>
                    <div>• {seedResult.colors_created} colors added</div>
                    <div>
                      •{" "}
                      {seedResult.material_products_created ||
                        seedResult.links_created}{" "}
                      material product SKUs created (0 on-hand)
                    </div>
                    <div className="text-xs mt-2" style={{ color: 'var(--text-secondary)' }}>
                      Just update inventory quantities to start using!
                    </div>
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={prevStep}
                  disabled={seedingData}
                  className="px-4 py-3 disabled:opacity-50 transition-colors"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Back
                </button>
                <button
                  onClick={handleSeedExampleData}
                  disabled={seedingData}
                  className="flex-1 py-3 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  style={{
                    background: 'linear-gradient(90deg, var(--primary), var(--primary-light))',
                    color: 'white'
                  }}
                >
                  {seedingData
                    ? "Loading..."
                    : seedExampleData
                    ? "Load Example Data"
                    : "Skip This Step"}
                </button>
              </div>
            </div>
          )}

          {/* Step 3: Products Import */}
          {currentStep === STEPS.PRODUCTS && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2"
                style={{ color: 'var(--text-secondary)' }}>
                  Products CSV File
                </label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setProductsFile(e.target.files[0])}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)'
                  }}
                />
                <p className="text-xs mt-2"
                style={{ color: 'var(--text-secondary)' }}>
                  CSV should include: SKU, Name, Description, Item Type, Unit,
                  Standard Cost, Selling Price
                </p>
              </div>

              {productsResult && (
                <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3 text-green-400 text-sm">
                  <div>Created: {productsResult.created || 0}</div>
                  <div>Updated: {productsResult.updated || 0}</div>
                  {productsResult.errors?.length > 0 && (
                    <div className="mt-2 text-red-400">
                      Errors: {productsResult.errors.length}
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={prevStep}
                  disabled={importingProducts}
                  className="px-4 py-3 disabled:opacity-50 transition-colors"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Back
                </button>
                <button
                  onClick={handleProductsImport}
                  disabled={importingProducts}
                  className="flex-1 py-3 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  style={{
                    background: 'linear-gradient(90deg, var(--primary), var(--primary-light))',
                    color: 'white'
                  }}
                >
                  {importingProducts
                    ? "Importing..."
                    : productsFile
                    ? "Import Products"
                    : "Skip This Step"}
                </button>
              </div>
            </div>
          )}

          {/* Step 4: Customers Import */}
          {currentStep === STEPS.CUSTOMERS && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2"
                style={{ color: 'var(--text-secondary)' }}>
                  Customers CSV File
                </label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setCustomersFile(e.target.files[0])}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)'
                  }}
                />
                <p className="text-xs mt-2"
                style={{ color: 'var(--text-secondary)' }}>
                  CSV should include: Email, First Name, Last Name, Company,
                  Phone, Address fields
                </p>
              </div>

              {customersResult && (
                <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3 text-green-400 text-sm">
                  <div>Imported: {customersResult.imported || 0}</div>
                  <div>Skipped: {customersResult.skipped || 0}</div>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={prevStep}
                  disabled={importingCustomers}
                  className="px-4 py-3 disabled:opacity-50 transition-colors"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Back
                </button>
                <button
                  onClick={handleCustomersImport}
                  disabled={importingCustomers}
                  className="flex-1 py-3 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  style={{
                    background: 'linear-gradient(90deg, var(--primary), var(--primary-light))',
                    color: 'white'
                  }}
                >
                  {importingCustomers
                    ? "Importing..."
                    : customersFile
                    ? "Import Customers"
                    : "Skip This Step"}
                </button>
              </div>
            </div>
          )}

          {/* Step 5: Orders Import */}
          {currentStep === STEPS.ORDERS && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2"
                style={{ color: 'var(--text-secondary)' }}>
                  Order Source
                </label>
                <select
                  value={ordersSource}
                  onChange={(e) => setOrdersSource(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)'
                  }}
                >
                  <option value="manual">Manual / Generic</option>
                  <option value="squarespace">Squarespace</option>
                  <option value="woocommerce">WooCommerce</option>
                  <option value="etsy">Etsy</option>
                  <option value="tiktok">TikTok Shop</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2"
                style={{ color: 'var(--text-secondary)' }}>
                  Orders CSV File
                </label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setOrdersFile(e.target.files?.[0] || null)}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)'
                  }}
                />
                <p className="text-xs mt-2"
                style={{ color: 'var(--text-secondary)' }}>
                  Required: Order ID, Customer Email, Product SKU, Quantity.
                  Optional: Customer Name, Shipping Address, Unit Price, Shipping
                  Cost, Tax Amount.
                </p>
              </div>

              {ordersResult && (
                <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3 text-green-400 text-sm">
                  <div>Created: {ordersResult.created || 0}</div>
                  {ordersResult.skipped > 0 && (
                    <div>Skipped: {ordersResult.skipped || 0}</div>
                  )}
                  {ordersResult.errors && ordersResult.errors.length > 0 && (
                    <div className="text-yellow-400 mt-2">
                      Errors: {ordersResult.errors.length}
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={prevStep}
                  disabled={importingOrders}
                  className="px-4 py-3 disabled:opacity-50 transition-colors"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Back
                </button>
                <button
                  onClick={handleOrdersImport}
                  disabled={importingOrders}
                  className="flex-1 py-3 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  style={{
                    background: 'linear-gradient(90deg, var(--primary), var(--primary-light))',
                    color: 'white'
                  }}
                >
                  {importingOrders
                    ? "Importing..."
                    : ordersFile
                    ? "Import Orders"
                    : "Skip This Step"}
                </button>
              </div>
            </div>
          )}

          {/* Step 6: Inventory Import (Optional) */}
          {currentStep === STEPS.INVENTORY && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2"
                style={{ color: 'var(--text-secondary)' }}>
                  Inventory CSV File (Optional)
                </label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setInventoryFile(e.target.files[0])}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{
                    backgroundColor: 'var(--bg-secondary)',
                    border: '1px solid var(--border-subtle)',
                    color: 'var(--text-primary)'
                  }}
                />
                <p className="text-xs mt-2"
                style={{ color: 'var(--text-secondary)' }}>
                  CSV should include: SKU, Location, Quantity
                </p>
              </div>

              {inventoryResult && (
                <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3 text-green-400 text-sm">
                  <div>Created: {inventoryResult.created || 0}</div>
                  <div>Updated: {inventoryResult.updated || 0}</div>
                  {inventoryResult.errors && inventoryResult.errors.length > 0 && (
                    <div className="text-yellow-400 mt-2">
                      Errors: {inventoryResult.errors.length}
                    </div>
                  )}
                </div>
              )}

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={prevStep}
                  disabled={importingInventory}
                  className="px-4 py-3 disabled:opacity-50 transition-colors"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Back
                </button>
                <button
                  onClick={handleInventoryImport}
                  disabled={importingInventory}
                  className="flex-1 py-3 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  style={{
                    background: 'linear-gradient(90deg, var(--primary), var(--primary-light))',
                    color: 'white'
                  }}
                >
                  {importingInventory
                    ? "Importing..."
                    : inventoryFile
                    ? "Import Inventory"
                    : "Skip This Step"}
                </button>
              </div>
            </div>
          )}

          {/* Step 7: Connect First Printer (Optional) */}
          {currentStep === STEPS.PRINTER && (
            <div className="space-y-4">
              <div className="rounded-lg p-4" style={{ backgroundColor: 'rgba(2, 109, 248, 0.1)', border: '1px solid rgba(2, 109, 248, 0.3)' }}>
                <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                  Register your first printer so FilaOps can track print jobs and
                  material consumption. Bambu Lab and generic printers are supported
                  on Community. Additional brands (Klipper, OctoPrint, Prusa,
                  Creality) require a PRO license.
                </p>
              </div>

              {printerResult ? (
                <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                  <div className="text-green-400 font-medium mb-1">
                    Printer added — {printerResult.name} ({printerResult.code})
                  </div>
                  <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                    You can configure the IP address and connection settings from
                    Admin → Printers.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  <div>
                    <label className="block text-sm font-medium mb-1"
                    style={{ color: 'var(--text-secondary)' }}>
                      Printer Name <span style={{ color: 'var(--text-secondary)' }}>(e.g. "X1C Bay 1")</span>
                    </label>
                    <input
                      type="text"
                      value={printerData.name}
                      onChange={(e) =>
                        setPrinterData({ ...printerData, name: e.target.value })
                      }
                      className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                      style={{
                        backgroundColor: 'var(--bg-secondary)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-primary)'
                      }}
                      placeholder="X1C Bay 1"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-sm font-medium mb-1"
                      style={{ color: 'var(--text-secondary)' }}>
                        Brand
                      </label>
                      <select
                        value={printerData.brand}
                        onChange={(e) =>
                          setPrinterData({ ...printerData, brand: e.target.value, model: "" })
                        }
                        className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                        style={{
                          backgroundColor: 'var(--bg-secondary)',
                          border: '1px solid var(--border-subtle)',
                          color: 'var(--text-primary)'
                        }}
                      >
                        {COMMUNITY_BRANDS.map((b) => (
                          <option key={b.value} value={b.value}>{b.label}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-1"
                      style={{ color: 'var(--text-secondary)' }}>
                        Model
                      </label>
                      {printerData.brand === "bambulab" ? (
                        <select
                          value={printerData.model}
                          onChange={(e) =>
                            setPrinterData({ ...printerData, model: e.target.value })
                          }
                          className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                          style={{
                            backgroundColor: 'var(--bg-secondary)',
                            border: '1px solid var(--border-subtle)',
                            color: 'var(--text-primary)'
                          }}
                        >
                          <option value="">Select model…</option>
                          <option value="X1C">X1 Carbon</option>
                          <option value="X1E">X1E</option>
                          <option value="P1S">P1S</option>
                          <option value="P1P">P1P</option>
                          <option value="A1">A1</option>
                          <option value="A1 mini">A1 mini</option>
                        </select>
                      ) : (
                        <input
                          type="text"
                          value={printerData.model}
                          onChange={(e) =>
                            setPrinterData({ ...printerData, model: e.target.value })
                          }
                          className="w-full px-3 py-2 rounded-lg focus:outline-none transition-all"
                          style={{
                            backgroundColor: 'var(--bg-secondary)',
                            border: '1px solid var(--border-subtle)',
                            color: 'var(--text-primary)'
                          }}
                          placeholder="e.g. Ender 3 Pro"
                        />
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={prevStep}
                  disabled={savingPrinter}
                  className="px-4 py-3 disabled:opacity-50 transition-colors"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  Back
                </button>

                {!printerResult && (
                  <>
                    <button
                      type="button"
                      onClick={handleAddPrinter}
                      disabled={savingPrinter || !printerData.name.trim() || !printerData.model.trim()}
                      className="flex-1 py-3 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      style={{
                        background: 'linear-gradient(90deg, var(--primary), var(--primary-light))',
                        color: 'white'
                      }}
                    >
                      {savingPrinter ? "Adding Printer…" : "Add Printer"}
                    </button>
                    <button
                      type="button"
                      onClick={skipPrinterStep}
                      disabled={savingPrinter}
                      className="px-4 py-3 rounded-lg disabled:opacity-50 transition-colors"
                      style={{
                        backgroundColor: 'var(--bg-secondary)',
                        border: '1px solid var(--border-subtle)',
                        color: 'var(--text-secondary)'
                      }}
                    >
                      Skip
                    </button>
                  </>
                )}

                {printerResult && (
                  <button
                    type="button"
                    onClick={() => setCurrentStep(STEPS.COMPLETE)}
                    className="flex-1 py-3 rounded-lg font-medium transition-colors"
                    style={{
                      background: 'linear-gradient(90deg, var(--primary), var(--primary-light))',
                      color: 'white'
                    }}
                  >
                    Continue
                  </button>
                )}
              </div>

              {/* Plain anchor (not react-router Link) is intentional here.
                  Clicking it mid-wizard abandons onboarding and navigates to
                  the printers page — the full-page reload is the right UX
                  because the user is explicitly leaving the setup flow. */}
              <p className="text-xs text-center" style={{ color: 'var(--text-secondary)' }}>
                You can manage your full printer fleet from{" "}
                <a
                  href="/admin/printers"
                  className="underline"
                  style={{ color: 'var(--primary)' }}
                >
                  Admin → Printers
                </a>{" "}
                after setup.
              </p>
            </div>
          )}

          {/* Step 8: Complete */}
          {currentStep === STEPS.COMPLETE && (
            <div className="text-center space-y-6">
              <div className="text-6xl mb-4">🎉</div>
              <h2 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
                Welcome to FilaOps!
              </h2>
              <p style={{ color: 'var(--text-secondary)' }}>
                Your ERP system is ready to use. Start managing your print farm
                operations.
              </p>
              <button
                onClick={handleComplete}
                className="w-full py-3 rounded-lg font-medium transition-colors"
                style={{
                  background: 'linear-gradient(90deg, var(--primary), var(--primary-light))',
                  color: 'white'
                }}
              >
                Go to Dashboard
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-sm mt-6" style={{ color: 'var(--text-secondary)' }}>
          You can always import data later from the admin panel.
        </p>
      </div>
    </div>
  );
}
