import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { API_URL } from "../config/api";
import { useToast } from "./Toast";
import Modal from "./Modal";
import {
  CloseIcon,
  CheckCircleIcon,
  MagicWandIcon,
  TerminalIcon,
} from "./remediation/icons";
import ManualStepCard from "./remediation/ManualStepCard";

const RemediationModal = ({ isOpen, onClose, check, onComplete }) => {
  const navigate = useNavigate();
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [guide, setGuide] = useState(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [completedSteps, setCompletedSteps] = useState(new Set());
  const [generatedKey, setGeneratedKey] = useState(null);
  const [generatingKey, setGeneratingKey] = useState(false);
  const [copied, setCopied] = useState(false);
  const [autoFixing, setAutoFixing] = useState(false);
  const [autoFixComplete, setAutoFixComplete] = useState(false);
  const [openingFile, setOpeningFile] = useState(false);
  const [openingTerminal, setOpeningTerminal] = useState(false);
  const [fixingDependencies, setFixingDependencies] = useState(false);
  const [dependencyFixResult, setDependencyFixResult] = useState(null);
  const [fixingRateLimiting, setFixingRateLimiting] = useState(false);
  const [rateLimitingFixResult, setRateLimitingFixResult] = useState(null);
  const [httpsFixing, setHttpsFixing] = useState(false);
  const [httpsFixResult, setHttpsFixResult] = useState(null);
  const [httpsDomain, setHttpsDomain] = useState("");
  const [fixingDotfiles, setFixingDotfiles] = useState(false);
  const [dotfileFixResult, setDotfileFixResult] = useState(null);

  useEffect(() => {
    if (isOpen && check) {
      fetchRemediationGuide();
      setCurrentStep(0);
      setCompletedSteps(new Set());
      setGeneratedKey(null);
      setAutoFixComplete(false);
      setDependencyFixResult(null);
      setRateLimitingFixResult(null);
      setHttpsFixResult(null);
      setHttpsDomain("");
      setDotfileFixResult(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, check]);

  const fetchRemediationGuide = async () => {
    setLoading(true);
    try {

      const response = await fetch(`${API_URL}/api/v1/security/remediate/${check.id}`, {
        credentials: "include",
      });

      if (response.ok) {
        const data = await response.json();
        setGuide(data);
      } else {
        toast.error("Failed to load remediation guide");
        onClose();
      }
    } catch {
      toast.error("Failed to load remediation guide");
      onClose();
    } finally {
      setLoading(false);
    }
  };

  const handleAutoFix = async () => {
    setAutoFixing(true);
    try {

      const response = await fetch(`${API_URL}/api/v1/security/remediate/update-secret-key`, {
        method: "POST",
        credentials: "include",
      });

      if (response.ok) {
        const data = await response.json();
        setAutoFixComplete(true);
        toast.success(data.message);
        // Mark all steps as complete
        const allSteps = new Set(guide.steps.map((_, i) => i));
        setCompletedSteps(allSteps);
      } else {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.detail || errorData.message || `Error ${response.status}`;
        toast.error(`Auto-fix failed: ${errorMsg}`);
      }
    } catch (err) {
      toast.error(`Auto-fix failed: ${err.message}`);
    } finally {
      setAutoFixing(false);
    }
  };

  const handleFixDependencies = async () => {
    setFixingDependencies(true);
    setDependencyFixResult(null);
    try {

      const response = await fetch(`${API_URL}/api/v1/security/remediate/fix-dependencies`, {
        method: "POST",
        credentials: "include",
      });

      const data = await response.json();

      if (response.ok) {
        setDependencyFixResult(data);
        setAutoFixComplete(true);
        toast.success(data.message);
        // Mark all steps as complete
        const allSteps = new Set(guide.steps.map((_, i) => i));
        setCompletedSteps(allSteps);
      } else {
        const errorMsg = data.detail || data.message || `Error ${response.status}`;
        toast.error(`Fix failed: ${errorMsg}`);
      }
    } catch (err) {
      toast.error(`Fix failed: ${err.message}`);
    } finally {
      setFixingDependencies(false);
    }
  };

  const handleFixRateLimiting = async () => {
    setFixingRateLimiting(true);
    setRateLimitingFixResult(null);
    try {

      const response = await fetch(`${API_URL}/api/v1/security/remediate/fix-rate-limiting`, {
        method: "POST",
        credentials: "include",
      });

      const data = await response.json();

      if (response.ok) {
        setRateLimitingFixResult(data);
        setAutoFixComplete(true);
        toast.success(data.message);
        const allSteps = new Set(guide.steps.map((_, i) => i));
        setCompletedSteps(allSteps);
      } else {
        const errorMsg = data.detail || data.message || `Error ${response.status}`;
        toast.error(`Fix failed: ${errorMsg}`);
      }
    } catch (err) {
      toast.error(`Fix failed: ${err.message}`);
    } finally {
      setFixingRateLimiting(false);
    }
  };

  const handleSetupHTTPS = async () => {
    if (!httpsDomain.trim()) {
      toast.error("Please enter a domain");
      return;
    }

    setHttpsFixing(true);
    setHttpsFixResult(null);
    try {

      const response = await fetch(`${API_URL}/api/v1/security/remediate/setup-https`, {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ domain: httpsDomain.trim() })
      });

      const data = await response.json();

      if (response.ok) {
        setHttpsFixResult(data);
        setAutoFixComplete(true);
        toast.success(data.message);
        const allSteps = new Set(guide.steps.map((_, i) => i));
        setCompletedSteps(allSteps);
      } else {
        const errorMsg = data.detail || data.message || `Error ${response.status}`;
        toast.error(`HTTPS setup failed: ${errorMsg}`);
      }
    } catch (err) {
      toast.error(`HTTPS setup failed: ${err.message}`);
    } finally {
      setHttpsFixing(false);
    }
  };

  const handleFixDotfiles = async () => {
    setFixingDotfiles(true);
    setDotfileFixResult(null);
    try {

      const response = await fetch(`${API_URL}/api/v1/security/remediate/fix-dotfile-blocking`, {
        method: "POST",
        credentials: "include",
      });

      const data = await response.json();

      if (response.ok) {
        setDotfileFixResult(data);
        setAutoFixComplete(true);
        toast.success(data.message);
        const allSteps = new Set(guide.steps.map((_, i) => i));
        setCompletedSteps(allSteps);
      } else {
        const errorMsg = data.detail || data.message || `Error ${response.status}`;
        toast.error(`Fix failed: ${errorMsg}`);
      }
    } catch (err) {
      toast.error(`Fix failed: ${err.message}`);
    } finally {
      setFixingDotfiles(false);
    }
  };

  const handleOpenInNotepad = async () => {
    setOpeningFile(true);
    try {

      const response = await fetch(`${API_URL}/api/v1/security/remediate/open-env-file`, {
        method: "POST",
        credentials: "include",
      });

      if (response.ok) {
        toast.success("File opened in Notepad!");
      } else {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.detail || errorData.message || `Error ${response.status}`;
        toast.error(`Could not open file: ${errorMsg}`);
      }
    } catch (err) {
      toast.error(`Could not open file: ${err.message}`);
    } finally {
      setOpeningFile(false);
    }
  };

  const handleOpenTerminal = async () => {
    setOpeningTerminal(true);
    try {

      const response = await fetch(`${API_URL}/api/v1/security/remediate/open-restart-terminal`, {
        method: "POST",
        credentials: "include",
      });

      if (response.ok) {
        toast.success("Terminal opened! Run the command shown to restart.");
      } else {
        const errorData = await response.json().catch(() => ({}));
        const errorMsg = errorData.detail || errorData.message || `Error ${response.status}`;
        toast.error(`Could not open terminal: ${errorMsg}`);
      }
    } catch (err) {
      toast.error(`Could not open terminal: ${err.message}`);
    } finally {
      setOpeningTerminal(false);
    }
  };

  const handleGenerateKey = async () => {
    setGeneratingKey(true);
    try {

      const response = await fetch(`${API_URL}/api/v1/security/remediate/generate-secret-key`, {
        method: "POST",
        credentials: "include",
      });

      if (response.ok) {
        const data = await response.json();
        setGeneratedKey(data.secret_key);
        toast.success("Secure key generated!");
      } else {
        toast.error("Failed to generate key");
      }
    } catch {
      toast.error("Failed to generate key");
    } finally {
      setGeneratingKey(false);
    }
  };

  const handleCopyKey = async () => {
    if (generatedKey) {
      await navigator.clipboard.writeText(generatedKey);
      setCopied(true);
      toast.success("Key copied to clipboard!");
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleStepComplete = (stepIndex) => {
    const newCompleted = new Set(completedSteps);
    newCompleted.add(stepIndex);
    setCompletedSteps(newCompleted);

    if (stepIndex < (guide?.steps?.length || 0) - 1) {
      setCurrentStep(stepIndex + 1);
    }
  };

  const handleNavigate = (path) => {
    onClose();
    navigate(path);
  };

  const handleFinish = () => {
    onClose();
    if (onComplete) {
      onComplete();
    }
  };

  const allStepsCompleted = guide?.steps && completedSteps.size >= guide.steps.length;
  const canAutoFixSecretKey = guide?.can_auto_generate && check?.id?.includes("secret_key");
  const canAutoFixDependencies = guide?.can_auto_fix_dependencies && check?.id === "dependencies_secure";
  const canAutoFixRateLimiting = guide?.can_auto_fix_rate_limiting && check?.id === "rate_limiting_enabled";
  const canAutoFixHTTPS = guide?.can_auto_fix_https && check?.id === "https_enabled";
  const canAutoFixDotfiles = guide?.can_auto_fix_dotfiles && check?.id === "env_file_not_exposed";

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Remediation Guide" className="w-full max-w-2xl max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-700">
          <div>
            <h2 className="text-xl font-bold text-white">
              {loading ? "Loading..." : guide?.title || "Remediation Guide"}
            </h2>
            {guide && (
              <p className="text-sm text-gray-400 mt-1">
                Estimated time: {guide.estimated_time}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
          >
            <CloseIcon />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 overflow-y-auto max-h-[60vh]">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
            </div>
          ) : guide ? (
            <div className="space-y-6">
              {/* Auto-Fix Option for Dependencies */}
              {canAutoFixDependencies && !autoFixComplete && (
                <div className="bg-gradient-to-r from-blue-900/50 to-indigo-900/50 border-2 border-blue-500 rounded-xl p-6">
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-blue-600 rounded-full">
                      <MagicWandIcon />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-white mb-2">Scan & Fix Automatically</h3>
                      <p className="text-gray-300 mb-4">
                        Click the button below and we'll automatically scan your dependencies for security issues and upgrade any vulnerable packages.
                      </p>
                      <button
                        onClick={handleFixDependencies}
                        disabled={fixingDependencies}
                        className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white font-semibold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2 text-lg"
                      >
                        {fixingDependencies ? (
                          <>
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                            Scanning & Fixing (this may take a minute)...
                          </>
                        ) : (
                          <>
                            <MagicWandIcon />
                            Scan & Fix Dependencies
                          </>
                        )}
                      </button>
                      <p className="text-xs text-gray-400 mt-2 text-center">
                        This will scan for known vulnerabilities and upgrade affected packages.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Dependency Fix Success Message */}
              {canAutoFixDependencies && autoFixComplete && dependencyFixResult && (
                <div className="bg-green-900/30 border-2 border-green-500 rounded-xl p-6">
                  <div className="flex justify-center mb-4">
                    <div className="p-4 bg-green-600 rounded-full">
                      <CheckCircleIcon />
                    </div>
                  </div>
                  <h3 className="text-xl font-bold text-green-400 mb-2 text-center">
                    {dependencyFixResult.vulnerabilities_found === 0
                      ? "No Vulnerabilities Found!"
                      : "Dependencies Updated!"}
                  </h3>
                  <p className="text-gray-300 mb-4 text-center">
                    {dependencyFixResult.message}
                  </p>

                  {dependencyFixResult.packages_upgraded?.length > 0 && (
                    <div className="bg-gray-900/50 rounded-lg p-4 mb-4">
                      <p className="text-sm text-gray-400 mb-2">Upgraded packages:</p>
                      <div className="flex flex-wrap gap-2">
                        {dependencyFixResult.packages_upgraded.map((pkg, i) => (
                          <span key={i} className="px-2 py-1 bg-green-800 text-green-200 rounded text-sm">
                            {pkg}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {dependencyFixResult.requires_restart && (
                    <>
                      <button
                        onClick={handleOpenTerminal}
                        disabled={openingTerminal}
                        className="w-full bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-600 text-white font-semibold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2 text-lg mb-4"
                      >
                        {openingTerminal ? (
                          <>
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                            Opening...
                          </>
                        ) : (
                          <>
                            <TerminalIcon />
                            Open Terminal to Restart
                          </>
                        )}
                      </button>
                      <p className="text-sm text-gray-400 text-center">
                        Restart the backend to apply the updated packages.
                      </p>
                    </>
                  )}
                </div>
              )}

              {/* Auto-Fix Option for Rate Limiting */}
              {canAutoFixRateLimiting && !autoFixComplete && (
                <div className="bg-gradient-to-r from-purple-900/50 to-violet-900/50 border-2 border-purple-500 rounded-xl p-6">
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-purple-600 rounded-full">
                      <MagicWandIcon />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-white mb-2">Install Rate Limiting</h3>
                      <p className="text-gray-300 mb-4">
                        Click the button below to install SlowAPI. FilaOps will automatically enable rate limiting after you restart.
                      </p>
                      <button
                        onClick={handleFixRateLimiting}
                        disabled={fixingRateLimiting}
                        className="w-full bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 text-white font-semibold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2 text-lg"
                      >
                        {fixingRateLimiting ? (
                          <>
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                            Installing...
                          </>
                        ) : (
                          <>
                            <MagicWandIcon />
                            Install SlowAPI
                          </>
                        )}
                      </button>
                      <p className="text-xs text-gray-400 mt-2 text-center">
                        Protects your API from brute force and denial of service attacks.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Rate Limiting Fix Success Message */}
              {canAutoFixRateLimiting && autoFixComplete && rateLimitingFixResult && (
                <div className="bg-green-900/30 border-2 border-green-500 rounded-xl p-6">
                  <div className="flex justify-center mb-4">
                    <div className="p-4 bg-green-600 rounded-full">
                      <CheckCircleIcon />
                    </div>
                  </div>
                  <h3 className="text-xl font-bold text-green-400 mb-2 text-center">
                    Rate Limiting Installed!
                  </h3>
                  <p className="text-gray-300 mb-4 text-center">
                    {rateLimitingFixResult.message}
                  </p>

                  {rateLimitingFixResult.requires_restart && (
                    <>
                      <button
                        onClick={handleOpenTerminal}
                        disabled={openingTerminal}
                        className="w-full bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-600 text-white font-semibold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2 text-lg mb-4"
                      >
                        {openingTerminal ? (
                          <>
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                            Opening...
                          </>
                        ) : (
                          <>
                            <TerminalIcon />
                            Open Terminal to Restart
                          </>
                        )}
                      </button>
                      <p className="text-sm text-gray-400 text-center">
                        Restart the backend to enable rate limiting.
                      </p>
                    </>
                  )}
                </div>
              )}

              {/* Auto-Fix Option for HTTPS */}
              {canAutoFixHTTPS && !autoFixComplete && (
                <div className="bg-gradient-to-r from-orange-900/50 to-amber-900/50 border-2 border-orange-500 rounded-xl p-6">
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-orange-600 rounded-full">
                      <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                      </svg>
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-white mb-2">Set Up HTTPS Automatically</h3>
                      <p className="text-gray-300 mb-4">
                        Enter your domain name and we'll set everything up for you - including a desktop shortcut to start FilaOps!
                      </p>

                      <div className="mb-4">
                        <label className="block text-sm font-medium text-gray-300 mb-2">
                          What's your domain?
                        </label>
                        <input
                          type="text"
                          value={httpsDomain}
                          onChange={(e) => setHttpsDomain(e.target.value)}
                          placeholder="e.g., filaops.local or mycompany.com"
                          className="w-full px-4 py-3 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
                        />
                        <p className="text-xs text-gray-400 mt-1">
                          For local use, try something like <code className="text-orange-300">filaops.local</code>
                        </p>
                      </div>

                      <button
                        onClick={handleSetupHTTPS}
                        disabled={httpsFixing || !httpsDomain.trim()}
                        className="w-full bg-orange-600 hover:bg-orange-700 disabled:bg-gray-600 text-white font-semibold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2 text-lg"
                      >
                        {httpsFixing ? (
                          <>
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                            Setting up HTTPS (this may take a few minutes)...
                          </>
                        ) : (
                          <>
                            <MagicWandIcon />
                            Set Up HTTPS
                          </>
                        )}
                      </button>
                      <p className="text-xs text-gray-400 mt-2 text-center">
                        We'll install Caddy (if needed), create the config, and add a desktop shortcut.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* HTTPS Fix Success Message */}
              {canAutoFixHTTPS && autoFixComplete && httpsFixResult && (
                <div className={`${httpsFixResult.needs_caddy_install ? "bg-yellow-900/30 border-yellow-500" : "bg-green-900/30 border-green-500"} border-2 rounded-xl p-6`}>
                  <div className="flex justify-center mb-4">
                    <div className={`p-4 ${httpsFixResult.needs_caddy_install ? "bg-yellow-600" : "bg-green-600"} rounded-full`}>
                      {httpsFixResult.needs_caddy_install ? (
                        <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                      ) : (
                        <CheckCircleIcon />
                      )}
                    </div>
                  </div>
                  <h3 className={`text-xl font-bold ${httpsFixResult.needs_caddy_install ? "text-yellow-400" : "text-green-400"} mb-2 text-center`}>
                    {httpsFixResult.needs_caddy_install ? "Almost Done!" : "HTTPS is Ready!"}
                  </h3>
                  <p className="text-gray-300 mb-4 text-center">
                    {httpsFixResult.message}
                  </p>

                  {/* Need to install Caddy */}
                  {httpsFixResult.needs_caddy_install && (
                    <div className="mb-4 p-4 bg-yellow-900/40 border border-yellow-600 rounded-lg">
                      <p className="text-yellow-200 text-center mb-3">
                        <strong>One more step:</strong> Download and install Caddy
                      </p>
                      <a
                        href="https://caddyserver.com/download"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block w-full bg-yellow-600 hover:bg-yellow-700 text-white font-semibold py-3 px-6 rounded-lg transition-colors text-center text-lg"
                      >
                        Download Caddy (Free)
                        <svg className="w-4 h-4 inline ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                        </svg>
                      </a>
                      <p className="text-xs text-yellow-300/70 mt-2 text-center">
                        Choose "Windows amd64" and run the installer. Then use the desktop shortcut!
                      </p>
                    </div>
                  )}

                  <div className="bg-gray-900/50 rounded-lg p-4 mb-4 space-y-2">
                    <div className="flex items-center gap-2">
                      {httpsFixResult.caddy_installed ? (
                        <span className="flex items-center gap-1 text-green-400 text-sm">
                          <CheckCircleIcon /> Caddy {httpsFixResult.caddy_was_installed ? "downloaded from GitHub" : "installed"}
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-yellow-400 text-sm">
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                          </svg>
                          Caddy needs to be installed
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {httpsFixResult.caddyfile_created && (
                        <span className="flex items-center gap-1 text-green-400 text-sm">
                          <CheckCircleIcon /> Caddyfile created
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {httpsFixResult.shortcut_created && (
                        <span className="flex items-center gap-1 text-green-400 text-sm">
                          <CheckCircleIcon /> Desktop shortcut created
                        </span>
                      )}
                    </div>
                    {httpsFixResult.caddy_started && (
                      <div className="flex items-center gap-2">
                        <span className="flex items-center gap-1 text-green-400 text-sm">
                          <CheckCircleIcon /> Caddy server running
                        </span>
                      </div>
                    )}
                  </div>

                  <div className="text-center">
                    <p className="text-gray-300 mb-2">Your secure URL (after Caddy is running):</p>
                    <span className="text-xl font-mono text-orange-400">
                      https://{httpsFixResult.domain}
                    </span>
                  </div>

                  {/* How to Start Instructions - Always show this prominently */}
                  <div className="mt-4 p-4 bg-gradient-to-r from-green-900/50 to-emerald-900/50 border-2 border-green-500 rounded-xl">
                    <h4 className="text-lg font-bold text-white mb-3 text-center">
                      🎉 How to Start FilaOps
                    </h4>

                    {httpsFixResult.shortcut_created ? (
                      <div className="space-y-3">
                        <div className="flex items-center gap-3 bg-gray-900/50 rounded-lg p-3">
                          <span className="text-2xl">1️⃣</span>
                          <div>
                            <p className="text-white font-medium">Find the shortcut on your Desktop</p>
                            <p className="text-gray-400 text-sm">
                              Look for <code className="text-green-400 bg-gray-800 px-2 py-0.5 rounded">Start FilaOps.bat</code>
                            </p>
                            {httpsFixResult.shortcut_path && (
                              <p className="text-xs text-gray-500 mt-1">
                                Location: {httpsFixResult.shortcut_path}
                              </p>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-3 bg-gray-900/50 rounded-lg p-3">
                          <span className="text-2xl">2️⃣</span>
                          <div>
                            <p className="text-white font-medium">Double-click to start everything</p>
                            <p className="text-gray-400 text-sm">
                              {httpsFixResult.needs_caddy_install
                                ? "After installing Caddy, double-click the shortcut"
                                : "This starts the backend + HTTPS server + opens your browser"}
                            </p>
                          </div>
                        </div>

                        <div className="flex items-center gap-3 bg-gray-900/50 rounded-lg p-3">
                          <span className="text-2xl">3️⃣</span>
                          <div>
                            <p className="text-white font-medium">Access FilaOps</p>
                            <p className="text-gray-400 text-sm">
                              Your browser will open to <span className="text-orange-400">https://{httpsFixResult.domain}</span>
                            </p>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="text-center">
                        <p className="text-yellow-300 mb-2">
                          ⚠️ Desktop shortcut couldn't be created automatically
                        </p>
                        <p className="text-gray-400 text-sm">
                          You can start FilaOps manually by running:<br/>
                          <code className="text-green-400 bg-gray-800 px-2 py-1 rounded mt-2 inline-block">
                            start-backend.ps1
                          </code>
                          {" "}then{" "}
                          <code className="text-green-400 bg-gray-800 px-2 py-1 rounded">
                            caddy run
                          </code>
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Auto-Fix Option for Dotfile Blocking */}
              {canAutoFixDotfiles && !autoFixComplete && (
                <div className="bg-gradient-to-r from-red-900/50 to-rose-900/50 border-2 border-red-500 rounded-xl p-6">
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-red-600 rounded-full">
                      <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                      </svg>
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-white mb-2">Block Sensitive Files</h3>
                      <p className="text-gray-300 mb-4">
                        Click the button below and we'll update your Caddy configuration to block access to sensitive files like <code className="bg-gray-800 px-2 py-0.5 rounded text-red-300">.env</code> and <code className="bg-gray-800 px-2 py-0.5 rounded text-red-300">.git</code>.
                      </p>
                      <button
                        onClick={handleFixDotfiles}
                        disabled={fixingDotfiles}
                        className="w-full bg-red-600 hover:bg-red-700 disabled:bg-gray-600 text-white font-semibold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2 text-lg"
                      >
                        {fixingDotfiles ? (
                          <>
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                            Updating Caddyfile...
                          </>
                        ) : (
                          <>
                            <MagicWandIcon />
                            Block Sensitive Files
                          </>
                        )}
                      </button>
                      <p className="text-xs text-gray-400 mt-2 text-center">
                        This adds a security rule to your reverse proxy configuration.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Dotfile Blocking Fix Success Message */}
              {canAutoFixDotfiles && autoFixComplete && dotfileFixResult && (
                <div className="bg-green-900/30 border-2 border-green-500 rounded-xl p-6">
                  <div className="flex justify-center mb-4">
                    <div className="p-4 bg-green-600 rounded-full">
                      <CheckCircleIcon />
                    </div>
                  </div>
                  <h3 className="text-xl font-bold text-green-400 mb-2 text-center">
                    {dotfileFixResult.already_configured ? "Already Protected!" : "Sensitive Files Blocked!"}
                  </h3>
                  <p className="text-gray-300 mb-4 text-center">
                    {dotfileFixResult.message}
                  </p>

                  <div className="bg-gray-900/50 rounded-lg p-4 mb-4 space-y-2">
                    {dotfileFixResult.caddyfile_updated && (
                      <div className="flex items-center gap-2">
                        <span className="flex items-center gap-1 text-green-400 text-sm">
                          <CheckCircleIcon /> Caddyfile updated
                        </span>
                      </div>
                    )}
                    {dotfileFixResult.caddy_reloaded && (
                      <div className="flex items-center gap-2">
                        <span className="flex items-center gap-1 text-green-400 text-sm">
                          <CheckCircleIcon /> Caddy reloaded
                        </span>
                      </div>
                    )}
                    {dotfileFixResult.already_configured && (
                      <div className="flex items-center gap-2">
                        <span className="flex items-center gap-1 text-green-400 text-sm">
                          <CheckCircleIcon /> Protection already in place
                        </span>
                      </div>
                    )}
                  </div>

                  {dotfileFixResult.requires_restart && (
                    <div className="text-center">
                      <p className="text-yellow-400 text-sm mb-2">
                        Restart Caddy to apply the changes.
                      </p>
                    </div>
                  )}
                </div>
              )}

              {/* Auto-Fix Option - Big and obvious for SECRET_KEY issues */}
              {canAutoFixSecretKey && !autoFixComplete && (
                <div className="bg-gradient-to-r from-green-900/50 to-emerald-900/50 border-2 border-green-500 rounded-xl p-6">
                  <div className="flex items-start gap-4">
                    <div className="p-3 bg-green-600 rounded-full">
                      <MagicWandIcon />
                    </div>
                    <div className="flex-1">
                      <h3 className="text-lg font-bold text-white mb-2">Easy Fix (Recommended)</h3>
                      <p className="text-gray-300 mb-4">
                        Click the button below and we'll automatically generate a secure key and update your configuration file.
                      </p>
                      <button
                        onClick={handleAutoFix}
                        disabled={autoFixing}
                        className="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-600 text-white font-semibold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2 text-lg"
                      >
                        {autoFixing ? (
                          <>
                            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                            Fixing...
                          </>
                        ) : (
                          <>
                            <MagicWandIcon />
                            Fix It For Me
                          </>
                        )}
                      </button>
                      <p className="text-xs text-gray-400 mt-2 text-center">
                        You'll need to restart the backend after this completes.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* SECRET_KEY Auto-Fix Success Message */}
              {canAutoFixSecretKey && autoFixComplete && (
                <div className="bg-green-900/30 border-2 border-green-500 rounded-xl p-6 text-center">
                  <div className="flex justify-center mb-4">
                    <div className="p-4 bg-green-600 rounded-full">
                      <CheckCircleIcon />
                    </div>
                  </div>
                  <h3 className="text-xl font-bold text-green-400 mb-2">Configuration Updated!</h3>
                  <p className="text-gray-300 mb-4">
                    Your SECRET_KEY has been updated. Now you just need to restart the backend server.
                  </p>

                  {/* Big Open Terminal Button */}
                  <button
                    onClick={handleOpenTerminal}
                    disabled={openingTerminal}
                    className="w-full bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-600 text-white font-semibold py-3 px-6 rounded-lg transition-colors flex items-center justify-center gap-2 text-lg mb-4"
                  >
                    {openingTerminal ? (
                      <>
                        <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
                        Opening...
                      </>
                    ) : (
                      <>
                        <TerminalIcon />
                        Open Terminal to Restart
                      </>
                    )}
                  </button>

                  <p className="text-sm text-gray-400">
                    A terminal will open with the restart command ready for you.
                  </p>
                </div>
              )}

              {/* Manual Method Divider */}
              {(canAutoFixSecretKey || canAutoFixDependencies || canAutoFixRateLimiting || canAutoFixHTTPS || canAutoFixDotfiles) && !autoFixComplete && (
                <div className="relative">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-gray-700"></div>
                  </div>
                  <div className="relative flex justify-center text-sm">
                    <span className="px-4 bg-gray-900 text-gray-500">or fix manually</span>
                  </div>
                </div>
              )}

              {/* Progress indicator */}
              {!autoFixComplete && (
                <div className="flex items-center gap-2 mb-6">
                  {guide.steps.map((_, index) => (
                    <div
                      key={index}
                      className={`flex-1 h-2 rounded-full transition-colors ${
                        completedSteps.has(index)
                          ? "bg-green-500"
                          : index === currentStep
                          ? "bg-blue-500"
                          : "bg-gray-700"
                      }`}
                    />
                  ))}
                </div>
              )}

              {/* Steps - Hidden when auto-fix is complete */}
              {!autoFixComplete && guide.steps.map((step, index) => (
                <ManualStepCard
                  key={index}
                  step={step}
                  index={index}
                  currentStep={currentStep}
                  completedSteps={completedSteps}
                  generatedKey={generatedKey}
                  generatingKey={generatingKey}
                  openingFile={openingFile}
                  copied={copied}
                  onSetCurrentStep={setCurrentStep}
                  onGenerateKey={handleGenerateKey}
                  onCopyKey={handleCopyKey}
                  onOpenInNotepad={handleOpenInNotepad}
                  onNavigate={handleNavigate}
                  onStepComplete={handleStepComplete}
                />
              ))}
            </div>
          ) : (
            <p className="text-gray-400 text-center py-8">No remediation guide available.</p>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-gray-700 bg-gray-800/50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleFinish}
            className={`px-6 py-2 rounded-lg transition-colors flex items-center gap-2 ${
              allStepsCompleted || autoFixComplete
                ? "bg-green-600 hover:bg-green-700 text-white"
                : "bg-blue-600 hover:bg-blue-700 text-white"
            }`}
          >
            {allStepsCompleted || autoFixComplete ? (
              <>
                <CheckCircleIcon />
                Done - Re-run Audit
              </>
            ) : (
              "Close & Re-run Audit"
            )}
          </button>
        </div>
    </Modal>
  );
};

export default RemediationModal;
