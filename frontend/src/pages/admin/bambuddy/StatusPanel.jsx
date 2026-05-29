import { Link } from "react-router-dom";
import { formatDate } from "./utils";

export function BambuddyStatusPanel({ connected, status, syncing, onSync }) {
  return (
    <div className="bg-gray-800/40 border border-gray-700 rounded-lg p-6 space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Connector Status</h2>
          <p className="text-sm text-gray-400 mt-1">
            {connected
              ? "FilaOps is connected to Bambuddy."
              : "FilaOps is not connected to Bambuddy."}
          </p>
        </div>
        <StatusBadge health={status?.health} connected={connected} />
      </div>

      <dl className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
        <InfoItem label="Service URL" value={status?.base_url || "Not set"} />
        <InfoItem label="Health" value={status?.health || "Disconnected"} />
        <InfoItem label="Version" value={status?.version || "Unknown"} />
        <InfoItem label="Last Sync" value={formatDate(status?.last_sync)} />
      </dl>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={onSync}
          disabled={!connected || syncing}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-400 text-white rounded-md text-sm font-medium"
        >
          {syncing ? "Syncing..." : "Sync Printers"}
        </button>
        <Link
          to="/admin/printers"
          className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md text-sm font-medium"
        >
          View FilaOps Printers
        </Link>
      </div>
    </div>
  );
}

function StatusBadge({ health, connected }) {
  const normalized = connected ? health || "unknown" : "disconnected";
  const variants = {
    healthy: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    ok: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    disconnected: "bg-gray-500/15 text-gray-300 border-gray-500/30",
    error: "bg-red-500/15 text-red-300 border-red-500/30",
    unhealthy: "bg-red-500/15 text-red-300 border-red-500/30",
  };
  return (
    <span
      role="status"
      className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold border whitespace-nowrap ${
        variants[normalized] || "bg-amber-500/15 text-amber-300 border-amber-500/30"
      }`}
    >
      {connected ? normalized : "not connected"}
    </span>
  );
}

function InfoItem({ label, value }) {
  return (
    <div className="bg-gray-900/40 border border-gray-700/60 rounded-md p-3">
      <dt className="text-xs uppercase tracking-wide text-gray-500">{label}</dt>
      <dd className="mt-1 text-gray-200 break-words">{value}</dd>
    </div>
  );
}
