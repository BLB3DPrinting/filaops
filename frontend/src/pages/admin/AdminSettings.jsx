import React, { useState, useEffect, useRef } from "react";
import { useApi } from "../../hooks/useApi";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import { useVersionCheck } from "../../hooks/useVersionCheck";
import { getCurrentVersion, getCurrentVersionSync, formatVersion } from "../../utils/version";
import { formatPhoneNumber, timezoneOptions } from "../../components/settings/constants";
import { currencyOptions, localeOptions } from "../../components/settings/i18nConstants";
import { useLocale } from "../../contexts/LocaleContext";
import AiSettingsSection from "../../components/settings/AiSettingsSection";
import { useApp } from "../../contexts/AppContext";

const AdminSettings = () => {
  const api = useApi();
  const toast = useToast();
  const { smtpConfigured } = useApp();
  const { updateLocaleSettings } = useLocale();
  const [taxRates, setTaxRates] = useState([]);
  const [newTaxRate, setNewTaxRate] = useState({ name: "", rate_percent: "", is_default: false });
  const [savingTaxRate, setSavingTaxRate] = useState(false);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploadingLogo, setUploadingLogo] = useState(false);
  const fileInputRef = useRef(null);
  const {
    latestVersion,
    updateAvailable,
    loading: checkingUpdate,
    checkForUpdates,
  } = useVersionCheck();
  const [checkingManually, setCheckingManually] = useState(false);
  const [currentVersion, setCurrentVersion] = useState(getCurrentVersionSync());

  // Form state
  const [form, setForm] = useState({
    company_name: "",
    company_address_line1: "",
    company_address_line2: "",
    company_city: "",
    company_state: "",
    company_zip: "",
    company_country: "USA",
    timezone: "America/New_York",
    currency_code: "USD",
    locale: "en-US",
    company_phone: "",
    company_email: "",
    company_website: "",
    tax_enabled: false,
    tax_rate_percent: "",
    tax_name: "Sales Tax",
    tax_registration_number: "",
    default_quote_validity_days: 30,
    quote_terms: "",
    quote_footer: "",
    business_hours_start: 8,
    business_hours_end: 16,
    business_days_per_week: 5,
    business_work_days: "0,1,2,3,4", // Mon-Fri
    default_margin_percent: "",
  });

  useEffect(() => {
    fetchSettings();
    fetchCurrentVersion();
    fetchTaxRates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchCurrentVersion = async () => {
    try {
      const version = await getCurrentVersion();
      setCurrentVersion(version);
    } catch (error) {
      console.error('Failed to fetch current version:', error);
      // Keep the sync fallback version
    }
  };

  const fetchSettings = async () => {
    try {
      const data = await api.get(`/api/v1/settings/company`);
      setSettings(data);
      setForm({
        company_name: data.company_name || "",
        company_address_line1: data.company_address_line1 || "",
        company_address_line2: data.company_address_line2 || "",
        company_city: data.company_city || "",
        company_state: data.company_state || "",
        company_zip: data.company_zip || "",
        company_country: data.company_country || "USA",
        timezone: data.timezone || "America/New_York",
        currency_code: data.currency_code || "USD",
        locale: data.locale || "en-US",
        company_phone: data.company_phone || "",
        company_email: data.company_email || "",
        company_website: data.company_website || "",
        tax_enabled: data.tax_enabled || false,
        tax_rate_percent: data.tax_rate_percent || "",
        tax_name: data.tax_name || "Sales Tax",
        tax_registration_number: data.tax_registration_number || "",
        default_quote_validity_days: data.default_quote_validity_days || 30,
        quote_terms: data.quote_terms || "",
        quote_footer: data.quote_footer || "",
        business_hours_start: data.business_hours_start ?? 8,
        business_hours_end: data.business_hours_end ?? 16,
        business_days_per_week: data.business_days_per_week ?? 5,
        business_work_days: data.business_work_days || "0,1,2,3,4",
        default_margin_percent: data.default_margin_percent ?? "",
      });
    } catch (error) {
      toast.error("Failed to load settings: " + error.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);

    try {
      const data = await api.patch(`/api/v1/settings/company`, {
        ...form,
        tax_rate_percent: form.tax_rate_percent
          ? parseFloat(form.tax_rate_percent)
          : null,
        default_quote_validity_days: parseInt(
          form.default_quote_validity_days
        ),
        default_margin_percent: form.default_margin_percent
          ? parseFloat(form.default_margin_percent)
          : null,
      });
      setSettings(data);
      // Push locale changes so all components reflect immediately without reload
      updateLocaleSettings({ currency_code: data.currency_code, locale: data.locale });
      toast.success("Settings saved successfully!");
    } catch (error) {
      toast.error("Failed to save settings: " + error.message);
    } finally {
      setSaving(false);
    }
  };

  // --------------- Tax Rate CRUD ---------------

  const fetchTaxRates = async () => {
    try {
      const data = await api.get("/api/v1/tax-rates");
      setTaxRates(data);
    } catch { /* non-critical */ }
  };

  const handleAddTaxRate = async (e) => {
    e.preventDefault();
    if (!newTaxRate.name || !newTaxRate.rate_percent) return;
    setSavingTaxRate(true);
    try {
      await api.post("/api/v1/tax-rates", {
        name: newTaxRate.name,
        rate_percent: parseFloat(newTaxRate.rate_percent),
        is_default: newTaxRate.is_default,
      });
      setNewTaxRate({ name: "", rate_percent: "", is_default: false });
      await fetchTaxRates();
      toast.success("Tax rate added");
    } catch (err) {
      toast.error("Failed to add tax rate: " + err.message);
    } finally {
      setSavingTaxRate(false);
    }
  };

  const handleSetDefault = async (id) => {
    try {
      await api.patch(`/api/v1/tax-rates/${id}`, { is_default: true });
      await fetchTaxRates();
    } catch (err) {
      toast.error("Failed to update: " + err.message);
    }
  };

  const handleDeleteTaxRate = async (id) => {
    try {
      await api.delete(`/api/v1/tax-rates/${id}`);
      await fetchTaxRates();
      toast.success("Tax rate deactivated");
    } catch (err) {
      toast.error("Failed to deactivate: " + err.message);
    }
  };

  // --------------- Logo ---------------

  const handleLogoUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setUploadingLogo(true);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_URL}/api/v1/settings/company/logo`, {
        method: "POST",
        credentials: "include",
        body: formData,
      });

      if (response.ok) {
        toast.success("Logo uploaded successfully!");
        fetchSettings();
      } else {
        const errData = await response.json();
        toast.error(errData.detail || "Failed to upload logo");
      }
    } catch (error) {
      toast.error("Failed to upload logo: " + error.message);
    } finally {
      setUploadingLogo(false);
    }
  };

  const handleLogoDelete = async () => {
    if (!confirm("Are you sure you want to delete the company logo?")) return;

    try {
      await api.del(`/api/v1/settings/company/logo`);
      toast.success("Logo deleted successfully!");
      fetchSettings();
    } catch (error) {
      toast.error("Failed to delete logo: " + error.message);
    }
  };

  if (loading) {
    return <div className="p-6 text-white">Loading...</div>;
  }

  return (
    <div className="p-6 space-y-6 max-w-4xl">
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">Company Settings</h1>
        <p className="text-gray-400">
          Configure your company information, logo, and tax settings
        </p>
      </div>

      {smtpConfigured === false && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-xl p-4 flex items-start gap-3">
          <svg className="w-5 h-5 text-amber-400 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
          <div>
            <h3 className="text-sm font-medium text-amber-400">Email (SMTP) Not Configured</h3>
            <p className="text-sm text-amber-400/80 mt-1">
              Password resets will auto-approve and display the reset link on screen.
              Configure SMTP_USER and SMTP_PASSWORD in your .env file to enable email-based password resets with admin approval.
            </p>
          </div>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-6">
        {/* Company Logo */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4">
            Company Logo
          </h2>
          <div className="flex items-center gap-6">
            {settings?.has_logo ? (
              <div className="relative">
                <img
                  src={`${API_URL}/api/v1/settings/company/logo?t=${Date.now()}`}
                  alt="Company Logo"
                  className="w-32 h-32 object-contain bg-gray-700 rounded-lg"
                />
                <button
                  type="button"
                  onClick={handleLogoDelete}
                  className="absolute -top-2 -right-2 bg-red-600 hover:bg-red-700 text-white rounded-full w-6 h-6 flex items-center justify-center text-sm"
                >
                  ×
                </button>
              </div>
            ) : (
              <div className="w-32 h-32 bg-gray-700 rounded-lg flex items-center justify-center text-gray-500">
                No Logo
              </div>
            )}
            <div>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleLogoUpload}
                accept="image/png,image/jpeg,image/gif,image/webp"
                className="hidden"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadingLogo}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors"
              >
                {uploadingLogo
                  ? "Uploading..."
                  : settings?.has_logo
                  ? "Change Logo"
                  : "Upload Logo"}
              </button>
              <p className="text-sm text-gray-400 mt-2">
                PNG, JPEG, GIF, or WebP. Max 2MB.
              </p>
            </div>
          </div>
        </div>

        {/* Company Information */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4">
            Company Information
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Company Name
              </label>
              <input
                type="text"
                name="company_name"
                value={form.company_name}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="Your Company Name"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Address Line 1
              </label>
              <input
                type="text"
                name="company_address_line1"
                value={form.company_address_line1}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="123 Main Street"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Address Line 2
              </label>
              <input
                type="text"
                name="company_address_line2"
                value={form.company_address_line2}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="Suite 100"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                City
              </label>
              <input
                type="text"
                name="company_city"
                value={form.company_city}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                State
              </label>
              <input
                type="text"
                name="company_state"
                value={form.company_state}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="TX"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                ZIP Code
              </label>
              <input
                type="text"
                name="company_zip"
                value={form.company_zip}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Country
              </label>
              <input
                type="text"
                name="company_country"
                value={form.company_country}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Timezone
              </label>
              <select
                name="timezone"
                value={form.timezone}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
              >
                {timezoneOptions.map((tz) => (
                  <option key={tz.value} value={tz.value}>
                    {tz.label}
                  </option>
                ))}
              </select>
              <p className="text-sm text-gray-400 mt-1">
                Used for date/time displays in reports and charts
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Phone
              </label>
              <input
                type="tel"
                name="company_phone"
                value={form.company_phone}
                onChange={(e) =>
                  setForm((prev) => ({
                    ...prev,
                    company_phone: formatPhoneNumber(e.target.value),
                  }))
                }
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="(555) 123-4567"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Email
              </label>
              <input
                type="email"
                name="company_email"
                value={form.company_email}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="info@yourcompany.com"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Website
              </label>
              <input
                type="url"
                name="company_website"
                value={form.company_website}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="https://yourcompany.com"
              />
            </div>
          </div>
        </div>

        {/* Regional Settings */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-1">
            Regional Settings
          </h2>
          <p className="text-sm text-gray-400 mb-4">
            Controls how currency amounts and numbers are displayed across the entire application.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Currency
              </label>
              <select
                name="currency_code"
                value={form.currency_code}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
              >
                {currencyOptions.map((c) => (
                  <option key={c.value} value={c.value}>{c.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Number &amp; Date Format
              </label>
              <select
                name="locale"
                value={form.locale}
                onChange={handleChange}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
              >
                {localeOptions.map((l) => (
                  <option key={l.value} value={l.value}>{l.label}</option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Controls decimal separators, thousands separators, and date formats.
              </p>
            </div>
          </div>
        </div>

        {/* Tax Settings */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4">
            Tax Settings
          </h2>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="tax_enabled"
                name="tax_enabled"
                checked={form.tax_enabled}
                onChange={handleChange}
                className="w-5 h-5 rounded bg-gray-700 border-gray-600 text-blue-600 focus:ring-blue-500"
              />
              <label htmlFor="tax_enabled" className="text-white">
                Enable sales tax on quotes
              </label>
            </div>

            {form.tax_enabled && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pl-8">
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Tax Rate (%)
                  </label>
                  <input
                    type="number"
                    name="tax_rate_percent"
                    value={form.tax_rate_percent}
                    onChange={handleChange}
                    step="0.01"
                    min="0"
                    max="100"
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                    placeholder="8.25"
                  />
                  <p className="text-sm text-gray-400 mt-1">
                    e.g., 8.25 for 8.25% tax
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Tax Name
                  </label>
                  <input
                    type="text"
                    name="tax_name"
                    value={form.tax_name}
                    onChange={handleChange}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                    placeholder="Sales Tax"
                  />
                </div>

                <div className="md:col-span-2">
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Tax Registration Number (optional)
                  </label>
                  <input
                    type="text"
                    name="tax_registration_number"
                    value={form.tax_registration_number}
                    onChange={handleChange}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                    placeholder="Your tax ID or VAT number"
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Tax Rate Management */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-1">Tax Rates</h2>
          <p className="text-sm text-gray-400 mb-4">
            Named tax rates (GST, QST, VAT). When 2+ rates exist, quotes show a dropdown selector.
          </p>

          {/* Existing rates */}
          {taxRates.length > 0 && (
            <div className="mb-4 space-y-2">
              {taxRates.map((tr) => (
                <div key={tr.id} className="flex items-center justify-between bg-gray-700 rounded-lg px-4 py-2">
                  <div className="flex items-center gap-3">
                    <span className="text-white font-medium">{tr.name}</span>
                    <span className="text-gray-300 text-sm">{tr.rate_percent.toFixed(2)}%</span>
                    {tr.is_default && (
                      <span className="text-xs bg-blue-600 text-white px-2 py-0.5 rounded-full">Default</span>
                    )}
                  </div>
                  <div className="flex gap-2">
                    {!tr.is_default && (
                      <button
                        type="button"
                        onClick={() => handleSetDefault(tr.id)}
                        className="text-xs text-blue-400 hover:text-blue-300"
                      >
                        Set default
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => handleDeleteTaxRate(tr.id)}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Add rate form */}
          <form onSubmit={handleAddTaxRate} className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Name</label>
              <input
                type="text"
                value={newTaxRate.name}
                onChange={(e) => setNewTaxRate((r) => ({ ...r, name: e.target.value }))}
                placeholder="e.g. GST"
                className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm w-36"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Rate (%)</label>
              <input
                type="number"
                step="0.001"
                min="0"
                max="100"
                value={newTaxRate.rate_percent}
                onChange={(e) => setNewTaxRate((r) => ({ ...r, rate_percent: e.target.value }))}
                placeholder="5.0"
                className="bg-gray-700 border border-gray-600 rounded-lg px-3 py-2 text-white text-sm w-24"
              />
            </div>
            <div className="flex items-center gap-2 pb-2">
              <input
                type="checkbox"
                id="new_tr_default"
                checked={newTaxRate.is_default}
                onChange={(e) => setNewTaxRate((r) => ({ ...r, is_default: e.target.checked }))}
                className="w-4 h-4"
              />
              <label htmlFor="new_tr_default" className="text-sm text-gray-300">Default</label>
            </div>
            <button
              type="submit"
              disabled={savingTaxRate}
              className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-lg disabled:opacity-50"
            >
              {savingTaxRate ? "Adding…" : "Add Rate"}
            </button>
          </form>
        </div>

        {/* Quote Settings */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4">
            Quote Settings
          </h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Default Quote Validity (days)
              </label>
              <input
                type="number"
                name="default_quote_validity_days"
                value={form.default_quote_validity_days}
                onChange={handleChange}
                min="1"
                max="365"
                className="w-full md:w-48 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Quote Terms & Conditions
              </label>
              <textarea
                name="quote_terms"
                value={form.quote_terms}
                onChange={handleChange}
                rows={4}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="Enter your standard terms and conditions..."
              />
              <p className="text-sm text-gray-400 mt-1">
                Displayed on quote PDFs
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Quote Footer Message
              </label>
              <textarea
                name="quote_footer"
                value={form.quote_footer}
                onChange={handleChange}
                rows={2}
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="Thank you for your business! Contact us at..."
              />
            </div>
          </div>
        </div>

        {/* Pricing Settings */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-1">Pricing</h2>
          <p className="text-sm text-gray-400 mb-4">
            Default target margin used by the &quot;Suggest Prices&quot; tool on the Items page.
          </p>
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Default Target Margin (%)
            </label>
            <input
              type="number"
              name="default_margin_percent"
              value={form.default_margin_percent}
              onChange={handleChange}
              min="0"
              max="99.99"
              step="0.01"
              className="w-full md:w-48 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
              placeholder="71.43"
            />
            <p className="text-sm text-gray-500 mt-1">
              71.43% margin = 3.5x markup. Formula: price = cost / (1 - margin% / 100)
            </p>
          </div>
        </div>

        {/* Business Hours Settings */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4">
            Business Hours (Production Operations)
          </h2>
          <p className="text-sm text-gray-400 mb-4">
            Configure default business hours for non-printer operations. These hours apply to all work centers except printer pools.
            Printer pools run 20 hours/day (4am-12am, daily) and are not affected by these settings.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Start Time (Hour)
              </label>
              <input
                type="number"
                name="business_hours_start"
                value={form.business_hours_start}
                onChange={handleChange}
                min="0"
                max="23"
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="8"
              />
              <p className="text-sm text-gray-400 mt-1">
                0-23 (e.g., 8 for 8am)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                End Time (Hour)
              </label>
              <input
                type="number"
                name="business_hours_end"
                value={form.business_hours_end}
                onChange={handleChange}
                min="0"
                max="23"
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="16"
              />
              <p className="text-sm text-gray-400 mt-1">
                0-23 (e.g., 16 for 4pm)
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Days Per Week
              </label>
              <input
                type="number"
                name="business_days_per_week"
                value={form.business_days_per_week}
                onChange={handleChange}
                min="1"
                max="7"
                className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="5"
              />
              <p className="text-sm text-gray-400 mt-1">
                1-7 (default: 5 for Mon-Fri)
              </p>
            </div>
          </div>
          <div className="mt-4">
            <label className="block text-sm font-medium text-gray-300 mb-1">
              Work Days (comma-separated)
            </label>
            <input
              type="text"
              name="business_work_days"
              value={form.business_work_days}
              onChange={handleChange}
              className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
              placeholder="0,1,2,3,4"
            />
            <p className="text-sm text-gray-400 mt-1">
              0=Monday, 1=Tuesday, ..., 6=Sunday. Example: "0,1,2,3,4" for Mon-Fri
            </p>
          </div>
        </div>

        {/* AI Configuration */}
        <AiSettingsSection />


        {/* Version & Updates */}
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4">
            Version & Updates
          </h2>
          <div className="space-y-4">
            <div>
              <p className="text-sm text-gray-400 mb-2">Current Version</p>
              <p className="text-lg font-semibold text-white">
                v{formatVersion(currentVersion)}
              </p>
            </div>

            {latestVersion && (
              <div>
                <p className="text-sm text-gray-400 mb-2">Latest Version</p>
                <div className="flex items-center gap-3">
                  <p className="text-lg font-semibold text-white">
                    v{formatVersion(latestVersion)}
                  </p>
                  {updateAvailable ? (
                    <span className="px-2 py-1 bg-blue-600 text-blue-100 text-xs rounded-md">
                      Update Available
                    </span>
                  ) : (
                    <span className="px-2 py-1 bg-green-600 text-green-100 text-xs rounded-md">
                      Up to Date
                    </span>
                  )}
                </div>
              </div>
            )}

            <div className="flex items-center gap-3 pt-2">
              <button
                type="button"
                onClick={async () => {
                  setCheckingManually(true);
                  await checkForUpdates(true);
                  setCheckingManually(false);
                  if (updateAvailable) {
                    toast.success(
                      `Update available: v${formatVersion(latestVersion)}`
                    );
                  } else {
                    toast.success("You're running the latest version!");
                  }
                }}
                disabled={checkingUpdate || checkingManually}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors text-sm"
              >
                {checkingUpdate || checkingManually
                  ? "Checking..."
                  : "Check for Updates"}
              </button>
              {latestVersion && updateAvailable && (
                <a
                  href={`https://github.com/Blb3D/filaops/releases/tag/v${formatVersion(
                    latestVersion
                  )}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:text-blue-300 text-sm underline"
                >
                  View Release Notes
                </a>
              )}
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white font-semibold px-6 py-3 rounded-lg transition-colors"
          >
            {saving ? "Saving..." : "Save Settings"}
          </button>
        </div>
      </form>
    </div>
  );
};

export default AdminSettings;
