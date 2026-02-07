import React, { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import RemediationModal from "../../components/RemediationModal";

// Status icons as components
const CheckIcon = () => (
  <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
  </svg>
);

const XIcon = () => (
  <svg className="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
  </svg>
);

const WarnIcon = () => (
  <svg className="w-5 h-5 text-yellow-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
  </svg>
);

const InfoIcon = () => (
  <svg className="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);

const ShieldIcon = ({ className = "" }) => (
  <svg className={`w-6 h-6 ${className}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
  </svg>
);

const WrenchIcon = () => (
  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
  </svg>
);

// Checks that have remediation guides
const REMEDIABLE_CHECKS = [
  "secret_key_not_default",
  "secret_key_entropy",
  "https_enabled",
  "cors_not_wildcard",
  "admin_password_changed",
  "dependencies_secure",
  "rate_limiting_enabled",
  "backup_configured",
  "env_file_not_exposed",
];

const getStatusIcon = (status) => {
  switch (status) {
    case "pass":
      return <CheckIcon />;
    case "fail":
      return <XIcon />;
    case "warn":
      return <WarnIcon />;
    case "info":
    default:
      return <InfoIcon />;
  }
};

const getStatusBadge = (status) => {
  switch (status) {
    case "pass":
      return "bg-green-900/50 text-green-400 border-green-600";
    case "fail":
      return "bg-red-900/50 text-red-400 border-red-600";
    case "warn":
      return "bg-yellow-900/50 text-yellow-400 border-yellow-600";
    case "info":
    default:
      return "bg-blue-900/50 text-blue-400 border-blue-600";
  }
};

const AdminSecurity = () => {
  const toast = useToast();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [auditData, setAuditData] = useState(null);
  const [error, setError] = useState(null);
  const [selectedCheck, setSelectedCheck] = useState(null);
  const [showRemediationModal, setShowRemediationModal] = useState(false);

  useEffect(() => {
    fetchSecurityAudit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFixClick = (check) => {
    setSelectedCheck(check);
    setShowRemediationModal(true);
  };

  const handleRemediationComplete = () => {
    // Re-run the audit after remediation
    fetchSecurityAudit(true);
  };

  const fetchSecurityAudit = async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/security/audit`, {
        credentials: "include",
      });

      if (response.ok) {
        const data = await response.json();
        setAuditData(data);
        if (isRefresh) {
          toast.success("Security audit refreshed");
        }
      } else {
        const errData = await response.json().catch(() => ({}));
        setError(errData.detail || `Error ${response.status}: Failed to load security audit`);
        toast.error(errData.detail || "Failed to load security audit");
      }
    } catch (err) {
      setError("Failed to load security audit: " + err.message);
      toast.error("Failed to load security audit: " + err.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const handleExport = async () => {
    setExporting(true);
    try {
      const response = await fetch(`${API_URL}/api/v1/security/audit/export?format=json`, {
        credentials: "include",
      });

      if (response.ok) {
        const data = await response.json();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `filaops_security_audit_${new Date().toISOString().split("T")[0]}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success("Security report exported");
      } else {
        toast.error("Failed to export report");
      }
    } catch (err) {
      toast.error("Failed to export: " + err.message);
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="p-6 text-white flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-gray-400">Running security audit...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-900/50 border border-red-600 rounded-lg p-6 text-center">
          <XIcon />
          <h2 className="text-xl font-semibold text-red-400 mt-4">Security Audit Failed</h2>
          <p className="text-gray-300 mt-2">{error}</p>
          <button
            onClick={() => fetchSecurityAudit()}
            className="mt-4 bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded-lg"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const { summary, checks, system_info, generated_at, filaops_version, environment, audit_version } = auditData || {};

  // Group checks by category
  const criticalChecks = checks?.filter((c) => c.category === "critical") || [];
  const warningChecks = checks?.filter((c) => c.category === "warning") || [];
  const infoChecks = checks?.filter((c) => c.category === "info") || [];

  // Get overall status styling
  const getOverallStatusStyle = (status) => {
    switch (status) {
      case "PASS":
        return { bg: "bg-green-900/30", border: "border-green-600", text: "text-green-400", icon: <ShieldIcon className="text-green-400" /> };
      case "WARN":
        return { bg: "bg-yellow-900/30", border: "border-yellow-600", text: "text-yellow-400", icon: <WarnIcon /> };
      case "FAIL":
      default:
        return { bg: "bg-red-900/30", border: "border-red-600", text: "text-red-400", icon: <XIcon /> };
    }
  };

  const overallStyle = getOverallStatusStyle(summary?.overall_status);

  return (
    <div className="p-6 space-y-6 max-w-5xl">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white mb-2 flex items-center gap-3">
            <ShieldIcon className="text-blue-400" />
            Security Audit
          </h1>
          <p className="text-gray-400">
            Verify your FilaOps installation security configuration
          </p>
        </div>
        <div className="flex gap-3">
          <button
            onClick={() => fetchSecurityAudit(true)}
            disabled={refreshing}
            className="bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
          >
            {refreshing ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                Refreshing...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Refresh
              </>
            )}
          </button>
          <button
            onClick={handleExport}
            disabled={exporting}
            className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
          >
            {exporting ? (
              <>
                <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                Exporting...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                Export Report
              </>
            )}
          </button>
        </div>
      </div>

      {/* Overall Status Card */}
      <div className={`${overallStyle.bg} border ${overallStyle.border} rounded-lg p-6`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-3 rounded-full bg-gray-800">
              {overallStyle.icon}
            </div>
            <div>
              <h2 className={`text-2xl font-bold ${overallStyle.text}`}>
                {summary?.overall_status === "PASS" && "All Clear"}
                {summary?.overall_status === "WARN" && "Warnings Found"}
                {summary?.overall_status === "FAIL" && "Action Required"}
              </h2>
              <p className="text-gray-300">
                {summary?.passed || 0} passed, {summary?.warnings || 0} warnings, {summary?.failed || 0} failed
              </p>
            </div>
          </div>
          <div className="text-right text-sm text-gray-400">
            <p>Audit v{audit_version}</p>
            <p>FilaOps v{filaops_version}</p>
            <p>{environment}</p>
          </div>
        </div>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-white">{summary?.total_checks || 0}</div>
          <div className="text-sm text-gray-400">Total Checks</div>
        </div>
        <div className="bg-green-900/30 border border-green-600 rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-green-400">{summary?.passed || 0}</div>
          <div className="text-sm text-gray-400">Passed</div>
        </div>
        <div className="bg-yellow-900/30 border border-yellow-600 rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-yellow-400">{summary?.warnings || 0}</div>
          <div className="text-sm text-gray-400">Warnings</div>
        </div>
        <div className="bg-red-900/30 border border-red-600 rounded-lg p-4 text-center">
          <div className="text-3xl font-bold text-red-400">{summary?.failed || 0}</div>
          <div className="text-sm text-gray-400">Failed</div>
        </div>
      </div>

      {/* Critical Checks */}
      {criticalChecks.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-red-500"></span>
            Critical Security Checks
          </h2>
          <div className="space-y-3">
            {criticalChecks.map((check) => (
              <div
                key={check.id}
                className={`border rounded-lg p-4 ${getStatusBadge(check.status)}`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 mt-0.5">
                    {getStatusIcon(check.status)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-white">{check.name}</h3>
                      <span className={`text-xs px-2 py-0.5 rounded uppercase ${
                        check.status === "pass" ? "bg-green-800 text-green-300" :
                        check.status === "fail" ? "bg-red-800 text-red-300" :
                        check.status === "warn" ? "bg-yellow-800 text-yellow-300" :
                        "bg-blue-800 text-blue-300"
                      }`}>
                        {check.status}
                      </span>
                    </div>
                    <p className="text-gray-300 mt-1">{check.message}</p>
                    {check.details && (
                      <p className="text-gray-400 text-sm mt-1">{check.details}</p>
                    )}
                    {check.remediation && check.status !== "pass" && (
                      <div className="mt-3 p-3 bg-gray-900/50 rounded-lg border border-gray-700 flex items-center justify-between">
                        <p className="text-sm text-gray-400">
                          <span className="font-medium text-gray-300">Fix: </span>
                          {check.remediation}
                        </p>
                        {REMEDIABLE_CHECKS.includes(check.id) && (
                          <button
                            onClick={() => handleFixClick(check)}
                            className="ml-4 flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-1.5 rounded-lg transition-colors flex-shrink-0"
                          >
                            <WrenchIcon />
                            Fix This
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Warning Checks */}
      {warningChecks.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-yellow-500"></span>
            Warning Checks
          </h2>
          <div className="space-y-3">
            {warningChecks.map((check) => (
              <div
                key={check.id}
                className={`border rounded-lg p-4 ${getStatusBadge(check.status)}`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 mt-0.5">
                    {getStatusIcon(check.status)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-white">{check.name}</h3>
                      <span className={`text-xs px-2 py-0.5 rounded uppercase ${
                        check.status === "pass" ? "bg-green-800 text-green-300" :
                        check.status === "fail" ? "bg-red-800 text-red-300" :
                        check.status === "warn" ? "bg-yellow-800 text-yellow-300" :
                        "bg-blue-800 text-blue-300"
                      }`}>
                        {check.status}
                      </span>
                    </div>
                    <p className="text-gray-300 mt-1">{check.message}</p>
                    {check.details && (
                      <p className="text-gray-400 text-sm mt-1">{check.details}</p>
                    )}
                    {check.remediation && check.status !== "pass" && (
                      <div className="mt-3 p-3 bg-gray-900/50 rounded-lg border border-gray-700 flex items-center justify-between">
                        <p className="text-sm text-gray-400">
                          <span className="font-medium text-gray-300">Recommendation: </span>
                          {check.remediation}
                        </p>
                        {REMEDIABLE_CHECKS.includes(check.id) && (
                          <button
                            onClick={() => handleFixClick(check)}
                            className="ml-4 flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white text-sm px-3 py-1.5 rounded-lg transition-colors flex-shrink-0"
                          >
                            <WrenchIcon />
                            Fix This
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Informational Checks */}
      {infoChecks.length > 0 && (
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4 flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-blue-500"></span>
            Informational
          </h2>
          <div className="space-y-3">
            {infoChecks.map((check) => (
              <div
                key={check.id}
                className={`border rounded-lg p-4 ${getStatusBadge(check.status)}`}
              >
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 mt-0.5">
                    {getStatusIcon(check.status)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-white">{check.name}</h3>
                    </div>
                    <p className="text-gray-300 mt-1">{check.message}</p>
                    {check.details && (
                      <p className="text-gray-400 text-sm mt-1">{check.details}</p>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* System Information */}
      {system_info && (
        <div className="bg-gray-800 rounded-lg p-6">
          <h2 className="text-xl font-semibold text-white mb-4">System Information</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <p className="text-sm text-gray-400">Operating System</p>
              <p className="text-white font-medium">{system_info.os}</p>
            </div>
            <div>
              <p className="text-sm text-gray-400">Python Version</p>
              <p className="text-white font-medium">{system_info.python_version}</p>
            </div>
            <div>
              <p className="text-sm text-gray-400">Database</p>
              <p className="text-white font-medium truncate" title={system_info.database}>
                {system_info.database}
              </p>
            </div>
            <div>
              <p className="text-sm text-gray-400">Reverse Proxy</p>
              <p className="text-white font-medium">{system_info.reverse_proxy}</p>
            </div>
          </div>
          <div className="mt-4 pt-4 border-t border-gray-700">
            <p className="text-sm text-gray-400">
              Last checked: {generated_at ? new Date(generated_at).toLocaleString() : "Unknown"}
            </p>
          </div>
        </div>
      )}

      {/* Remediation Modal */}
      <RemediationModal
        isOpen={showRemediationModal}
        onClose={() => {
          setShowRemediationModal(false);
          setSelectedCheck(null);
        }}
        check={selectedCheck}
        onComplete={handleRemediationComplete}
      />
    </div>
  );
};

export default AdminSecurity;
