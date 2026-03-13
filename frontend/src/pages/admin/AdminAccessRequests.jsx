import { useState, useEffect, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";

const STATUS_COLORS = {
  pending: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  approved: "bg-green-500/20 text-green-400 border-green-500/30",
  denied: "bg-red-500/20 text-red-400 border-red-500/30",
  revoked: "bg-orange-500/20 text-orange-400 border-orange-500/30",
};

const STATUS_LABELS = {
  pending: "Pending",
  approved: "Approved",
  denied: "Denied",
  revoked: "Revoked",
};

export default function AdminAccessRequests() {
  const toast = useToast();
  const api = useApi();
  const { isPro, loading: flagsLoading } = useFeatureFlags();

  const [requests, setRequests] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState("pending");
  const [actionLoading, setActionLoading] = useState(null);
  const [setupLink, setSetupLink] = useState(null);

  const fetchRequests = useCallback(async () => {
    setLoading(true);
    try {
      const params = filter ? `?status=${filter}` : "";
      const data = await api.get(`/api/v1/pro/portal/admin/access-requests${params}`);
      setRequests(data);
    } catch (err) {
      toast.error("Failed to load access requests");
    } finally {
      setLoading(false);
    }
  }, [api, filter, toast]);

  // Clear setup link banner when filter changes (approved request may not be visible)
  useEffect(() => setSetupLink(null), [filter]);

  useEffect(() => {
    if (isPro && !flagsLoading) {
      fetchRequests();
    }
  }, [isPro, flagsLoading, fetchRequests]);

  const handleApprove = async (id) => {
    setActionLoading(id);
    try {
      const result = await api.post(`/api/v1/pro/portal/admin/access-requests/${id}/approve`, {});
      toast.success(`Approved — setup link generated`);
      setSetupLink({ id, url: result.setup_url, email: result.message, token: result.setup_token });
      await fetchRequests();
    } catch (err) {
      toast.error(err?.message || "Failed to approve request");
    } finally {
      setActionLoading(null);
    }
  };

  const handleDeny = async (id) => {
    if (!window.confirm("Deny this access request?")) return;
    setActionLoading(id);
    try {
      await api.post(`/api/v1/pro/portal/admin/access-requests/${id}/deny`, {});
      toast.success("Request denied");
      await fetchRequests();
    } catch (err) {
      toast.error(err?.message || "Failed to deny request");
    } finally {
      setActionLoading(null);
    }
  };

  const handleResend = async (id) => {
    setActionLoading(id);
    try {
      const result = await api.post(`/api/v1/pro/portal/admin/access-requests/${id}/resend`, {});
      toast.success("New invite link generated");
      setSetupLink({ id, url: result.setup_url, token: result.setup_token });
      await fetchRequests();
    } catch (err) {
      toast.error(err?.message || "Failed to resend invite");
    } finally {
      setActionLoading(null);
    }
  };

  const handleRevoke = async (id) => {
    if (!window.confirm("Revoke this user's portal access? Their account will be deactivated.")) return;
    setActionLoading(id);
    try {
      await api.post(`/api/v1/pro/portal/admin/access-requests/${id}/revoke`, {});
      toast.success("Access revoked");
      setSetupLink(null);
      await fetchRequests();
    } catch (err) {
      toast.error(err?.message || "Failed to revoke access");
    } finally {
      setActionLoading(null);
    }
  };

  const copySetupLink = async () => {
    if (!setupLink) return;
    // Use the full URL from the API if PORTAL_PUBLIC_URL is configured,
    // otherwise fall back to constructing from window.location.origin
    const fullUrl = setupLink.url.startsWith("http")
      ? setupLink.url
      : `${window.location.origin}${setupLink.url}`;
    try {
      await navigator.clipboard.writeText(fullUrl);
      toast.success("Setup link copied to clipboard");
    } catch {
      toast.error("Failed to copy — clipboard access denied");
    }
  };

  // -- PRO gate --
  if (flagsLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (!isPro) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-white">Access Requests</h1>
          <p className="text-gray-400 mt-1">
            Review and approve B2B portal access applications
          </p>
        </div>
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-6 text-center">
          <svg className="w-12 h-12 text-blue-400 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          <h3 className="text-lg font-semibold text-white mb-2">PRO Feature</h3>
          <p className="text-gray-400 mb-4">
            Access Requests let you review, approve, and manage B2B portal
            registration applications. Resend setup links or revoke access
            for any customer.
          </p>
          <a href="/pricing" className="inline-block bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition-colors">
            Upgrade to PRO
          </a>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">Access Requests</h1>
        <p className="text-sm text-gray-400 mt-1">
          Review and approve B2B portal access applications
        </p>
      </div>

      {/* Setup Link Banner */}
      {setupLink && (
        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-green-400">Setup Link Generated</p>
              <p className="text-xs text-green-400/80 mt-1">
                Send this link to the applicant so they can set their password:
              </p>
              <code className="text-xs text-green-300 mt-1 block bg-green-500/10 px-2 py-1 rounded break-all">
                {setupLink.url.startsWith("http") ? setupLink.url : `${window.location.origin}${setupLink.url}`}
              </code>
            </div>
            <div className="flex gap-2">
              <button
                onClick={copySetupLink}
                className="px-3 py-1.5 text-xs bg-green-600 hover:bg-green-700 text-white rounded transition-colors"
              >
                Copy Link
              </button>
              <button
                onClick={() => setSetupLink(null)}
                className="px-3 py-1.5 text-xs bg-gray-600 hover:bg-gray-700 text-white rounded transition-colors"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-2">
        {["pending", "approved", "denied", "revoked", ""].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-3 py-1.5 text-xs rounded-md border transition-colors ${
              filter === f
                ? "bg-blue-600 border-blue-500 text-white"
                : "bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-500"
            }`}
          >
            {f === "" ? "All" : STATUS_LABELS[f]}
          </button>
        ))}
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        </div>
      )}

      {/* Empty state */}
      {!loading && requests.length === 0 && (
        <div className="bg-gray-800 rounded-lg p-8 text-center">
          <p className="text-gray-400">
            {filter ? `No ${filter} access requests` : "No access requests yet"}
          </p>
        </div>
      )}

      {/* Request cards */}
      {!loading && requests.length > 0 && (
        <div className="space-y-3">
          {requests.map((req) => (
            <div
              key={req.id}
              className="bg-gray-800 border border-gray-700 rounded-lg p-4"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-sm font-semibold text-white truncate">
                      {req.business_name}
                    </h3>
                    <span
                      className={`px-2 py-0.5 text-xs rounded-full border ${
                        STATUS_COLORS[req.status] || "bg-gray-700 text-gray-400"
                      }`}
                    >
                      {STATUS_LABELS[req.status] || req.status}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1 text-xs text-gray-400">
                    <div>
                      <span className="text-gray-500">Contact:</span>{" "}
                      <span className="text-gray-300">{req.contact_name}</span>
                    </div>
                    <div>
                      <span className="text-gray-500">Email:</span>{" "}
                      <span className="text-gray-300">{req.contact_email}</span>
                    </div>
                    {req.contact_phone && (
                      <div>
                        <span className="text-gray-500">Phone:</span>{" "}
                        <span className="text-gray-300">{req.contact_phone}</span>
                      </div>
                    )}
                    {(req.city || req.state) && (
                      <div>
                        <span className="text-gray-500">Location:</span>{" "}
                        <span className="text-gray-300">
                          {[req.city, req.state, req.zip_code].filter(Boolean).join(", ")}
                        </span>
                      </div>
                    )}
                  </div>

                  {req.message && (
                    <div className="mt-2 text-xs text-gray-400 bg-gray-900 rounded p-2">
                      <span className="text-gray-500">Message: </span>
                      {req.message}
                    </div>
                  )}

                  {req.admin_notes && (
                    <div className="mt-2 text-xs text-blue-400 bg-blue-500/10 rounded p-2">
                      <span className="text-blue-500">Admin: </span>
                      {req.admin_notes}
                    </div>
                  )}

                  <div className="mt-2 text-xs text-gray-500">
                    Submitted {new Date(req.created_at).toLocaleDateString()}{" "}
                    {new Date(req.created_at).toLocaleTimeString()}
                    {req.setup_token_used && (
                      <span className="ml-2 text-green-500">Account created</span>
                    )}
                  </div>
                </div>

                {/* Actions */}
                {req.status === "pending" && (
                  <div className="flex gap-2 ml-4 flex-shrink-0">
                    <button
                      onClick={() => handleApprove(req.id)}
                      disabled={actionLoading === req.id}
                      className="px-3 py-1.5 text-xs bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white rounded transition-colors"
                    >
                      {actionLoading === req.id ? "..." : "Approve"}
                    </button>
                    <button
                      onClick={() => handleDeny(req.id)}
                      disabled={actionLoading === req.id}
                      className="px-3 py-1.5 text-xs bg-red-600/20 hover:bg-red-600/40 disabled:opacity-50 text-red-400 border border-red-600/30 rounded transition-colors"
                    >
                      Deny
                    </button>
                  </div>
                )}
                {req.status === "approved" && (
                  <div className="flex gap-2 ml-4 flex-shrink-0">
                    {!req.setup_token_used && (
                      <button
                        onClick={() => handleResend(req.id)}
                        disabled={actionLoading === req.id}
                        className="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white rounded transition-colors"
                      >
                        {actionLoading === req.id ? "..." : "Resend Invite"}
                      </button>
                    )}
                    <button
                      onClick={() => handleRevoke(req.id)}
                      disabled={actionLoading === req.id}
                      className="px-3 py-1.5 text-xs bg-orange-600/20 hover:bg-orange-600/40 disabled:opacity-50 text-orange-400 border border-orange-600/30 rounded transition-colors"
                    >
                      {actionLoading === req.id ? "..." : "Revoke Access"}
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
