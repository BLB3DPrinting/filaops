/**
 * AiSettingsSection - AI provider configuration (Anthropic / Ollama).
 *
 * Extracted from AdminSettings.jsx (ARCHITECT-002)
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";

export default function AiSettingsSection() {
  const toast = useToast();
  const [aiSettings, setAiSettings] = useState(null);
  const [aiForm, setAiForm] = useState({
    ai_provider: "",
    ai_api_key: "",
    ai_ollama_url: "http://localhost:11434",
    ai_ollama_model: "llama3.2",
    ai_anthropic_model: "claude-haiku-3-5-20241022",
    external_ai_blocked: false,
  });
  const [savingAi, setSavingAi] = useState(false);
  const [testingAi, setTestingAi] = useState(false);
  const [startingOllama, setStartingOllama] = useState(false);
  const [anthropicStatus, setAnthropicStatus] = useState({ installed: false, version: null, loading: true });
  const [installingAnthropic, setInstallingAnthropic] = useState(false);

  useEffect(() => {
    fetchAiSettings();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (aiForm.ai_provider === "anthropic") {
      setAnthropicStatus((prev) => ({ ...prev, loading: true }));
      checkAnthropicStatus();
    } else {
      setAnthropicStatus((prev) => ({ ...prev, loading: false }));
    }
  }, [aiForm.ai_provider]);

  const fetchAiSettings = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      if (!token) {
        setAnthropicStatus((prev) => ({ ...prev, loading: false }));
        return;
      }

      const response = await fetch(`${API_URL}/api/v1/settings/ai`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      if (response.ok) {
        const data = await response.json();
        setAiSettings(data);
        setAiForm({
          ai_provider: data.ai_provider || "",
          ai_api_key: "", // Don't populate - it's masked
          ai_ollama_url: data.ai_ollama_url || "http://localhost:11434",
          ai_ollama_model: data.ai_ollama_model || "llama3.2",
          ai_anthropic_model: data.ai_anthropic_model || "claude-haiku-3-5-20241022",
          external_ai_blocked: data.external_ai_blocked || false,
        });
        // Only check Anthropic package status if relevant (anthropic selected or no provider)
        if (data.ai_provider === "anthropic" || !data.ai_provider) {
          checkAnthropicStatus();
        } else {
          // Not using Anthropic, so mark loading as done
          setAnthropicStatus((prev) => ({ ...prev, loading: false }));
        }
      } else {
        const errData = await response.json().catch(() => ({}));
        toast.error(errData.detail || `Error ${response.status}: Failed to load AI settings`);
        setAnthropicStatus((prev) => ({ ...prev, loading: false }));
      }
    } catch (error) {
      console.error("Failed to fetch AI settings:", error);
      setAnthropicStatus((prev) => ({ ...prev, loading: false }));
    }
  };

  const checkAnthropicStatus = async () => {
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(`${API_URL}/api/v1/settings/ai/anthropic-status`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (response.ok) {
        const data = await response.json();
        setAnthropicStatus({ ...data, loading: false });
      } else {
        setAnthropicStatus((prev) => ({ ...prev, loading: false }));
      }
    } catch (error) {
      console.error("Failed to check anthropic status:", error);
      setAnthropicStatus((prev) => ({ ...prev, loading: false }));
    }
  };

  const handleInstallAnthropic = async () => {
    setInstallingAnthropic(true);
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(`${API_URL}/api/v1/settings/ai/install-anthropic`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      const data = await response.json();
      if (response.ok && data.success) {
        toast.success(data.message);
        // Recheck status
        await checkAnthropicStatus();
      } else {
        toast.error(data.message || "Failed to install package");
      }
    } catch (error) {
      toast.error("Failed to install package: " + error.message);
    } finally {
      setInstallingAnthropic(false);
    }
  };

  const handleAiFormChange = (e) => {
    const { name, value } = e.target;
    setAiForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSaveAiSettings = async () => {
    setSavingAi(true);
    try {
      const token = localStorage.getItem("adminToken");

      const payload = {
        ai_provider: aiForm.ai_provider || null,
        ai_ollama_url: aiForm.ai_ollama_url || null,
        ai_ollama_model: aiForm.ai_ollama_model || null,
        ai_anthropic_model: aiForm.ai_anthropic_model || null,
      };
      if (aiForm.ai_api_key) {
        payload.ai_api_key = aiForm.ai_api_key;
      }

      const response = await fetch(`${API_URL}/api/v1/settings/ai`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (response.ok) {
        const data = await response.json();
        setAiSettings(data);
        setAiForm({
          ai_provider: data.ai_provider || "",
          ai_api_key: "", // Don't populate - it's masked
          ai_ollama_url: data.ai_ollama_url || "http://localhost:11434",
          ai_ollama_model: data.ai_ollama_model || "llama3.2",
          ai_anthropic_model: data.ai_anthropic_model || "claude-haiku-3-5-20241022",
          external_ai_blocked: data.external_ai_blocked || false,
        });
        toast.success("AI settings saved successfully!");
      } else {
        const errData = await response.json();
        toast.error(errData.detail || "Failed to save AI settings");
      }
    } catch (error) {
      toast.error("Failed to save AI settings: " + error.message);
    } finally {
      setSavingAi(false);
    }
  };

  const handleTestAiConnection = async () => {
    setTestingAi(true);
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(`${API_URL}/api/v1/settings/ai/test`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      const data = await response.json();
      if (response.ok && data.success) {
        toast.success(data.message || "AI connection successful!");
      } else {
        toast.error(data.message || "AI connection failed");
      }
    } catch (error) {
      toast.error("Failed to test AI connection: " + error.message);
    } finally {
      setTestingAi(false);
    }
  };

  const handleClearAiSettings = async () => {
    if (!confirm("Are you sure you want to disable AI and clear all settings?")) return;

    setSavingAi(true);
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(`${API_URL}/api/v1/settings/ai`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          ai_provider: null,
          ai_api_key: "",
        }),
      });

      if (response.ok) {
        await fetchAiSettings();
        toast.success("AI settings cleared");
      } else {
        const errData = await response.json();
        toast.error(errData.detail || "Failed to clear AI settings");
      }
    } catch (error) {
      toast.error("Failed to clear AI settings: " + error.message);
    } finally {
      setSavingAi(false);
    }
  };

  const handleStartOllama = async () => {
    setStartingOllama(true);
    try {
      const token = localStorage.getItem("adminToken");
      const response = await fetch(`${API_URL}/api/v1/settings/ai/start-ollama`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      const data = await response.json();
      if (response.ok && data.success) {
        toast.success(data.message || "Ollama started!");
      } else {
        toast.error(data.message || "Failed to start Ollama");
      }
    } catch (error) {
      toast.error("Failed to start Ollama: " + error.message);
    } finally {
      setStartingOllama(false);
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg p-6">
      <h2 className="text-xl font-semibold text-white mb-4">
        AI Configuration
      </h2>
      <p className="text-sm text-gray-400 mb-4">
        Configure AI for enhanced invoice parsing. When enabled, invoices can be automatically
        parsed to extract line items, vendor information, and amounts.
      </p>

      {/* Block External AI Toggle */}
      <div className={`mb-6 p-4 rounded-lg border-2 ${aiForm.external_ai_blocked ? 'border-green-600 bg-green-900/20' : 'border-gray-600 bg-gray-700/50'}`}>
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <svg className={`w-5 h-5 ${aiForm.external_ai_blocked ? 'text-green-400' : 'text-gray-400'}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
              <h3 className="text-white font-bold">Block External AI Services</h3>
            </div>
            <p className="text-gray-400 text-sm mt-1">
              {aiForm.external_ai_blocked
                ? "External AI is blocked. Only local AI (Ollama) can be used. No data leaves this machine."
                : "Enable to force local-only AI processing. Blocks cloud AI providers for data privacy."}
            </p>
          </div>
          <button
            type="button"
            onClick={async () => {
              const newValue = !aiForm.external_ai_blocked;
              setSavingAi(true);
              try {
                const token = localStorage.getItem("adminToken");
                const response = await fetch(`${API_URL}/api/v1/settings/ai`, {
                  method: "PATCH",
                  headers: {
                    Authorization: `Bearer ${token}`,
                    "Content-Type": "application/json",
                  },
                  body: JSON.stringify({ external_ai_blocked: newValue }),
                });
                if (response.ok) {
                  const data = await response.json();
                  setAiSettings(data);
                  setAiForm((prev) => ({
                    ...prev,
                    external_ai_blocked: data.external_ai_blocked,
                    ai_provider: data.ai_provider || "",
                  }));
                  toast.success(newValue ? "External AI blocked - data stays local" : "External AI unblocked");
                } else {
                  const errData = await response.json();
                  toast.error(errData.detail || "Failed to update setting");
                }
              } catch (error) {
                toast.error("Failed to update setting: " + error.message);
              } finally {
                setSavingAi(false);
              }
            }}
            disabled={savingAi}
            className={`ml-4 relative inline-flex h-8 w-14 items-center rounded-full transition-colors ${
              aiForm.external_ai_blocked ? 'bg-green-600' : 'bg-gray-600'
            } ${savingAi ? 'opacity-50' : ''}`}
          >
            <span
              className={`inline-block h-6 w-6 transform rounded-full bg-white transition-transform ${
                aiForm.external_ai_blocked ? 'translate-x-7' : 'translate-x-1'
              }`}
            />
          </button>
        </div>
      </div>

      {/* Status indicator */}
      {aiSettings && (
        <div className="mb-4 p-3 rounded-lg bg-gray-700">
          <div className="flex items-center gap-2">
            <span
              className={`w-3 h-3 rounded-full ${
                aiSettings.ai_status === "configured"
                  ? "bg-green-500"
                  : aiSettings.ai_status === "error"
                  ? "bg-red-500"
                  : "bg-yellow-500"
              }`}
            />
            <span className="text-white font-medium">
              {aiSettings.ai_status === "configured"
                ? "AI Configured"
                : aiSettings.ai_status === "error"
                ? "Configuration Error"
                : "Not Configured"}
            </span>
          </div>
          {aiSettings.ai_status_message && (
            <p className="text-sm text-gray-400 mt-1 ml-5">
              {aiSettings.ai_status_message}
            </p>
          )}
          {aiSettings.ai_api_key_masked && (
            <p className="text-sm text-gray-400 mt-1 ml-5">
              API Key: {aiSettings.ai_api_key_masked}
            </p>
          )}
        </div>
      )}

      <div className="space-y-4">
        {/* Provider Selection */}
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-1">
            AI Provider
          </label>
          <select
            name="ai_provider"
            value={aiForm.ai_provider}
            onChange={handleAiFormChange}
            className="w-full md:w-64 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
          >
            <option value="">Disabled</option>
            <option value="anthropic" disabled={aiForm.external_ai_blocked}>
              Anthropic Claude {aiForm.external_ai_blocked && "(blocked)"}
            </option>
            <option value="ollama">Ollama (Local)</option>
          </select>
        </div>

        {/* Anthropic Settings */}
        {aiForm.ai_provider === "anthropic" && (
          <div className="pl-4 border-l-2 border-blue-600 space-y-4">
            <div className="p-3 bg-gray-700 rounded-lg border-l-4 border-yellow-500">
              <p className="text-sm text-yellow-300 font-medium mb-1">
                Data Privacy Notice
              </p>
              <p className="text-sm text-gray-300">
                <strong>Anthropic Claude</strong> is a cloud-based AI service. Invoice and purchase order
                data (vendor names, amounts, line items) will be sent to Anthropic&apos;s servers for processing.
              </p>
              <p className="text-sm text-gray-400 mt-2">
                <strong>Not recommended</strong> for businesses with data compliance requirements
                (HIPAA, ITAR, SOX, GDPR, etc.). Consider <strong>Ollama</strong> for fully local processing.
              </p>
              <p className="text-sm text-gray-400 mt-2">
                Usage is billed per request (typically a few cents per invoice).{" "}
                <a
                  href="https://www.anthropic.com/pricing"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-400 hover:underline"
                >
                  See pricing
                </a>
              </p>
            </div>

            {/* Package Installation Check */}
            {anthropicStatus.loading && (
              <div className="p-3 bg-gray-700 rounded-lg text-gray-300 text-sm">
                Checking Anthropic package status...
              </div>
            )}
            {!anthropicStatus.loading && !anthropicStatus.installed && (
              <div className="p-3 bg-red-900/30 border border-red-600 rounded-lg">
                <p className="text-sm text-red-300 font-medium mb-2">
                  Required Package Not Installed
                </p>
                <p className="text-sm text-gray-300 mb-3">
                  The Anthropic Python package needs to be installed before you can use Claude AI.
                </p>
                <button
                  type="button"
                  onClick={handleInstallAnthropic}
                  disabled={installingAnthropic}
                  className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
                >
                  {installingAnthropic ? (
                    <>
                      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Installing...
                    </>
                  ) : (
                    "Install Anthropic Package"
                  )}
                </button>
              </div>
            )}

            {anthropicStatus.installed && (
              <>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    API Key
                  </label>
                  <input
                    type="password"
                    name="ai_api_key"
                    value={aiForm.ai_api_key}
                    onChange={handleAiFormChange}
                    className="w-full bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                    placeholder={
                      aiSettings?.ai_api_key_set
                        ? "••••••••••••••• (key is set)"
                        : "sk-ant-..."
                    }
                  />
                  <p className="text-sm text-gray-400 mt-1">
                    Get your API key from{" "}
                    <a
                      href="https://console.anthropic.com/account/keys"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-400 hover:underline"
                    >
                      console.anthropic.com
                    </a>
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-300 mb-1">
                    Model
                  </label>
                  <select
                    name="ai_anthropic_model"
                    value={aiForm.ai_anthropic_model}
                    onChange={handleAiFormChange}
                    className="w-full md:w-96 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                  >
                    <option value="claude-haiku-3-5-20241022">
                      Haiku 3.5 - Fastest (~$0.001/doc)
                    </option>
                    <option value="claude-sonnet-4-20250514">
                      Sonnet 4 - Balanced (~$0.004/doc)
                    </option>
                    <option value="claude-opus-4-5-20251101">
                      Opus 4.5 - Best Quality (~$0.02/doc)
                    </option>
                  </select>
                  <p className="text-sm text-gray-400 mt-1">
                    Cost estimates based on ~2,000 token invoices. Opus provides best extraction accuracy.
                  </p>
                </div>
              </>
            )}
          </div>
        )}

        {/* Ollama Settings */}
        {aiForm.ai_provider === "ollama" && (
          <div className="pl-4 border-l-2 border-green-600 space-y-4">
            <div className="p-3 bg-gray-700 rounded-lg border-l-4 border-green-500">
              <p className="text-sm text-green-300 font-medium mb-1">
                Privacy-First Option
              </p>
              <p className="text-sm text-gray-300">
                <strong>Ollama</strong> runs AI models entirely on your computer. No invoice or purchase
                order data ever leaves your machine - ideal for regulated industries and sensitive data.
              </p>
              <p className="text-sm text-gray-400 mt-2">
                First-time setup requires downloading a model (2-8 GB). Processing speed depends on
                your computer&apos;s hardware (GPU recommended but not required).
              </p>
              <p className="text-sm text-gray-400 mt-2">
                <a
                  href="https://ollama.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-green-400 hover:underline"
                >
                  Download Ollama
                </a>
                {" "}if not already installed.
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Ollama Server URL
              </label>
              <input
                type="text"
                name="ai_ollama_url"
                value={aiForm.ai_ollama_url}
                onChange={handleAiFormChange}
                className="w-full md:w-96 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="http://localhost:11434"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-1">
                Model Name
              </label>
              <input
                type="text"
                name="ai_ollama_model"
                value={aiForm.ai_ollama_model}
                onChange={handleAiFormChange}
                className="w-full md:w-64 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 text-white"
                placeholder="llama3.2"
              />
              <p className="text-sm text-gray-400 mt-1">
                Common models: llama3.2, mistral, codellama
              </p>
            </div>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-wrap gap-3 pt-2">
          <button
            type="button"
            onClick={handleSaveAiSettings}
            disabled={savingAi}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors"
          >
            {savingAi ? "Saving..." : "Save AI Settings"}
          </button>
          {aiForm.ai_provider && (
            <button
              type="button"
              onClick={handleTestAiConnection}
              disabled={testingAi || savingAi}
              className="bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors"
            >
              {testingAi ? "Testing..." : "Test Connection"}
            </button>
          )}
          {aiForm.ai_provider === "ollama" && (
            <button
              type="button"
              onClick={handleStartOllama}
              disabled={startingOllama || savingAi}
              className="bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors"
            >
              {startingOllama ? "Starting..." : "Start Ollama"}
            </button>
          )}
          {aiSettings?.ai_provider && (
            <button
              type="button"
              onClick={handleClearAiSettings}
              disabled={savingAi}
              className="bg-red-600 hover:bg-red-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors"
            >
              Disable AI
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
