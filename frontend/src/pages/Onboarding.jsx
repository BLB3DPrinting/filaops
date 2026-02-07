/**
 * First-Time Onboarding Wizard
 *
 * Multi-step wizard for new FilaOps installations:
 * 1. Admin account creation
 * 2. CSV import for products
 * 3. CSV import for customers
 * 4. CSV import for inventory (optional)
 * 5. Complete - redirect to dashboard
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
  COMPLETE: 7,
};

export default function Onboarding() {
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(STEPS.ACCOUNT);
  const advanceTimeoutRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [needsSetup, setNeedsSetup] = useState(false);
  const [error, setError] = useState(null);

  // Step 1: Admin account
  const [accountData, setAccountData] = useState({
    email: "",
    password: "",
    confirmPassword: "",
    full_name: "",
    company_name: "",
  });
  const [submittingAccount, setSubmittingAccount] = useState(false);

  // Step 2: Products CSV
  const [productsFile, setProductsFile] = useState(null);
  const [productsResult, setProductsResult] = useState(null);
  const [importingProducts, setImportingProducts] = useState(false);

  // Step 3: Customers CSV
  const [customersFile, setCustomersFile] = useState(null);
  const [customersResult, setCustomersResult] = useState(null);
  const [importingCustomers, setImportingCustomers] = useState(false);

  // Step 2: Example Data (optional)
  const [seedExampleData, setSeedExampleData] = useState(true); // Default to true
  const [seedingData, setSeedingData] = useState(false);
  const [seedResult, setSeedResult] = useState(null);

  // Step 5: Orders CSV (optional)
  const [ordersFile, setOrdersFile] = useState(null);
  const [ordersResult, setOrdersResult] = useState(null);
  const [importingOrders, setImportingOrders] = useState(false);
  const [ordersSource, setOrdersSource] = useState("manual");

  // Step 6: Inventory CSV (optional)
  const [inventoryFile, setInventoryFile] = useState(null);
  const [inventoryResult, setInventoryResult] = useState(null);
  const [importingInventory, setImportingInventory] = useState(false);

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
        credentials: "include",
        headers: { "Content-Type": "application/json" },
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
        credentials: "include",
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
        credentials: "include",
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
        credentials: "include",
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
      setCurrentStep(STEPS.COMPLETE);
      return;
    }

    setImportingInventory(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", inventoryFile);

      const res = await fetch(`${API_URL}/api/v1/admin/import/inventory`, {
        method: "POST",
        credentials: "include",
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
      scheduleAdvance(STEPS.COMPLETE);
    } catch (err) {
      setError(err.message);
    } finally {
      setImportingInventory(false);
    }
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
      <div className="min-h-screen bg-gray-950 flex items-center justify-center">
        <div className="text-white">Checking setup status...</div>
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
    return 7;
  };

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="max-w-2xl w-full">
        {/* Progress Bar */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-gray-400">
              Step {getStepNumber()} of {getTotalSteps()}
            </span>
            <span className="text-sm text-gray-400">
              {Math.round((getStepNumber() / getTotalSteps()) * 100)}%
            </span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-2">
            <div
              className="bg-blue-600 h-2 rounded-full transition-all duration-300"
              style={{ width: `${(getStepNumber() / getTotalSteps()) * 100}%` }}
            />
          </div>
        </div>

        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-white mb-2">
            {getStepTitle()}
          </h1>
          <p className="text-gray-400">
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
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          {/* Step 1: Account Creation */}
          {currentStep === STEPS.ACCOUNT && (
            <form onSubmit={handleCreateAccount} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Your Name
                </label>
                <input
                  type="text"
                  name="full_name"
                  value={accountData.full_name}
                  onChange={handleAccountChange}
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
                  value={accountData.email}
                  onChange={handleAccountChange}
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
                  value={accountData.password}
                  onChange={handleAccountChange}
                  required
                  minLength={8}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  placeholder="••••••••"
                />
                <ul className="text-xs text-gray-500 mt-1 space-y-0.5">
                  <li>• At least 8 characters</li>
                  <li>• Uppercase and lowercase letters</li>
                  <li>• At least one number</li>
                  <li>• At least one special character</li>
                </ul>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-1">
                  Confirm Password
                </label>
                <input
                  type="password"
                  name="confirmPassword"
                  value={accountData.confirmPassword}
                  onChange={handleAccountChange}
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
                  value={accountData.company_name}
                  onChange={handleAccountChange}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                  placeholder="Your Print Farm"
                />
              </div>

              <button
                type="submit"
                disabled={submittingAccount}
                className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
              <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-4">
                <h3 className="text-white font-medium mb-2">
                  Load BambuLab Materials & Example Data?
                </h3>
                <p className="text-gray-400 text-sm mb-4">
                  We can populate your database with BambuLab-compatible materials:
                </p>
                <ul className="text-gray-300 text-sm space-y-2 mb-4">
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
                <p className="text-gray-400 text-sm">
                  This gives you a head start with ready-to-use material options. You can always add more materials and colors later!
                </p>
              </div>

              {!seedExampleData && (
                <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-4">
                  <h4 className="text-yellow-400 font-medium mb-2">⚠️ Skipping seed data?</h4>
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
                  className="w-5 h-5 rounded border-gray-700 bg-gray-800 text-blue-600 focus:ring-blue-500"
                />
                <label
                  htmlFor="seedData"
                  className="text-gray-300 cursor-pointer"
                >
                  Yes, load example data (recommended)
                </label>
              </div>

              {seedResult && (
                <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
                  <div className="text-green-400 font-medium mb-2">
                    ✅ Example data loaded successfully!
                  </div>
                  <div className="text-gray-300 text-sm space-y-1">
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
                    <div className="text-gray-400 text-xs mt-2">
                      💡 Just update inventory quantities to start using!
                    </div>
                  </div>
                </div>
              )}

              <div className="flex gap-3">
                <button
                  type="button"
                  onClick={prevStep}
                  disabled={seedingData}
                  className="px-4 py-3 text-gray-400 hover:text-white disabled:opacity-50 transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={handleSeedExampleData}
                  disabled={seedingData}
                  className="flex-1 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Products CSV File
                </label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setProductsFile(e.target.files[0])}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm"
                />
                <p className="text-xs text-gray-500 mt-2">
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
                  className="px-4 py-3 text-gray-400 hover:text-white disabled:opacity-50 transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={handleProductsImport}
                  disabled={importingProducts}
                  className="flex-1 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Customers CSV File
                </label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setCustomersFile(e.target.files[0])}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm"
                />
                <p className="text-xs text-gray-500 mt-2">
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
                  className="px-4 py-3 text-gray-400 hover:text-white disabled:opacity-50 transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={handleCustomersImport}
                  disabled={importingCustomers}
                  className="flex-1 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Order Source
                </label>
                <select
                  value={ordersSource}
                  onChange={(e) => setOrdersSource(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500"
                >
                  <option value="manual">Manual / Generic</option>
                  <option value="squarespace">Squarespace</option>
                  <option value="woocommerce">WooCommerce</option>
                  <option value="etsy">Etsy</option>
                  <option value="tiktok">TikTok Shop</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Orders CSV File
                </label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setOrdersFile(e.target.files?.[0] || null)}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm"
                />
                <p className="text-xs text-gray-500 mt-2">
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
                  className="px-4 py-3 text-gray-400 hover:text-white disabled:opacity-50 transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={handleOrdersImport}
                  disabled={importingOrders}
                  className="flex-1 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Inventory CSV File (Optional)
                </label>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setInventoryFile(e.target.files[0])}
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white text-sm"
                />
                <p className="text-xs text-gray-500 mt-2">
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
                  className="px-4 py-3 text-gray-400 hover:text-white disabled:opacity-50 transition-colors"
                >
                  Back
                </button>
                <button
                  onClick={handleInventoryImport}
                  disabled={importingInventory}
                  className="flex-1 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
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

          {/* Step 5: Complete */}
          {currentStep === STEPS.COMPLETE && (
            <div className="text-center space-y-6">
              <div className="text-6xl mb-4">🎉</div>
              <h2 className="text-2xl font-bold text-white">
                Welcome to FilaOps!
              </h2>
              <p className="text-gray-400">
                Your ERP system is ready to use. Start managing your print farm
                operations.
              </p>
              <button
                onClick={handleComplete}
                className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
              >
                Go to Dashboard
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-gray-500 text-sm mt-6">
          You can always import data later from the admin panel.
        </p>
      </div>
    </div>
  );
}
