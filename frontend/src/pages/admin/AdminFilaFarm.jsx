import { useState, useEffect, useRef, useCallback } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";

const STATUS_COLORS = {
  idle: { bg: "bg-gray-700", dot: "bg-gray-400", text: "text-gray-400" },
  printing: {
    bg: "bg-emerald-900/30",
    dot: "bg-emerald-400",
    text: "text-emerald-400",
  },
  paused: {
    bg: "bg-yellow-900/30",
    dot: "bg-yellow-400",
    text: "text-yellow-400",
  },
  error: { bg: "bg-red-900/30", dot: "bg-red-400", text: "text-red-400" },
  offline: { bg: "bg-gray-800", dot: "bg-gray-600", text: "text-gray-600" },
};

const JOB_STATUS_COLORS = {
  queued: "text-blue-400",
  assigned: "text-yellow-400",
  printing: "text-emerald-400",
  completed: "text-green-400",
  failed: "text-red-400",
  cancelled: "text-gray-500",
};

function formatTime(seconds) {
  if (seconds == null) return "--";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function PrinterCard({ printer, onCommand }) {
  const colors = STATUS_COLORS[printer.status] || STATUS_COLORS.offline;
  const isPrinting = printer.status === "printing";

  return (
    <div
      className={`${colors.bg} border border-gray-700 rounded-lg p-4 hover:border-gray-500 transition-colors`}
    >
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-medium text-white truncate">{printer.name}</h3>
        <span className={`flex items-center gap-1.5 text-xs ${colors.text}`}>
          <span
            className={`w-2 h-2 rounded-full ${colors.dot} ${isPrinting ? "animate-pulse" : ""}`}
          />
          {printer.status}
        </span>
      </div>

      <p className="text-xs text-gray-500 mb-3">{printer.model}</p>

      {/* Temps */}
      <div className="flex gap-4 text-xs text-gray-400 mb-2">
        <span>🔥 {printer.nozzle_temp?.toFixed(0) ?? "--"}°C</span>
        <span>🛏️ {printer.bed_temp?.toFixed(0) ?? "--"}°C</span>
      </div>

      {/* Progress bar when printing */}
      {isPrinting && (
        <div className="mt-2">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-gray-400 truncate">
              {printer.current_job || "Printing..."}
            </span>
            <span className="text-emerald-400">
              {(printer.progress ?? 0).toFixed(0)}%
            </span>
          </div>
          <div className="w-full bg-gray-700 rounded-full h-1.5">
            <div
              className="bg-emerald-500 h-1.5 rounded-full transition-all"
              style={{ width: `${printer.progress ?? 0}%` }}
            />
          </div>
        </div>
      )}

      {/* AMS slots */}
      {printer.ams_slots && printer.ams_slots.length > 0 && (
        <div className="mt-3 pt-2 border-t border-gray-700">
          <span className="text-xs text-gray-500">AMS:</span>
          <div className="flex gap-1 mt-1">
            {printer.ams_slots.map((slot, i) => (
              <div
                key={i}
                className="w-4 h-4 rounded-sm border border-gray-600"
                style={{ backgroundColor: slot.color || "#666" }}
                title={`Slot ${i + 1}: ${slot.material || "empty"}`}
              />
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      {(printer.status === "printing" || printer.status === "paused") && (
        <div className="mt-3 pt-2 border-t border-gray-700 flex gap-2">
          {printer.status === "printing" && (
            <button
              onClick={() => onCommand(printer.id, "pause")}
              className="text-xs px-2 py-1 bg-yellow-800/50 text-yellow-300 rounded hover:bg-yellow-800"
            >
              Pause
            </button>
          )}
          {printer.status === "paused" && (
            <button
              onClick={() => onCommand(printer.id, "resume")}
              className="text-xs px-2 py-1 bg-emerald-800/50 text-emerald-300 rounded hover:bg-emerald-800"
            >
              Resume
            </button>
          )}
          <button
            onClick={() => onCommand(printer.id, "cancel")}
            className="text-xs px-2 py-1 bg-red-800/50 text-red-300 rounded hover:bg-red-800"
          >
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

function JobRow({ job }) {
  const statusColor = JOB_STATUS_COLORS[job.status] || "text-gray-400";
  return (
    <tr className="border-b border-gray-800 hover:bg-gray-800/50">
      <td className="py-2 px-3 text-sm text-white">{job.name}</td>
      <td className={`py-2 px-3 text-sm ${statusColor}`}>{job.status}</td>
      <td className="py-2 px-3 text-sm text-gray-400">
        {job.printer_id || "—"}
      </td>
      <td className="py-2 px-3 text-sm text-gray-400">
        {(job.progress ?? 0).toFixed(0)}%
      </td>
      <td className="py-2 px-3 text-sm text-gray-400">
        {formatTime(job.estimated_time)}
      </td>
      <td className="py-2 px-3 text-sm text-gray-400">{job.priority}</td>
    </tr>
  );
}

export default function AdminFilaFarm() {
  const api = useApi();
  const toast = useToast();
  const { isPro, hasFeature, loading: flagsLoading } = useFeatureFlags();
  const hasFilaFarmAccess = isPro && hasFeature("filafarm");
  const [printers, setPrinters] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState("printers");
  const refreshRef = useRef(null);
  const commandTimeoutRef = useRef(null);

  const fetchData = useCallback(async () => {
    try {
      const [printersRes, jobsRes, statsRes] = await Promise.allSettled([
        api.get("/api/v1/pro/filafarm/printers"),
        api.get("/api/v1/pro/filafarm/jobs"),
        api.get("/api/v1/pro/filafarm/stats/today"),
      ]);

      setPrinters(
        printersRes.status === "fulfilled"
          ? printersRes.value?.printers || []
          : [],
      );
      setJobs(jobsRes.status === "fulfilled" ? jobsRes.value?.jobs || [] : []);
      setStats(statsRes.status === "fulfilled" ? statsRes.value : null);

      const anyFailed =
        printersRes.status === "rejected" ||
        jobsRes.status === "rejected" ||
        statsRes.status === "rejected";
      setError(anyFailed ? "Some FilaFarm data could not be loaded." : null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    if (!hasFilaFarmAccess) return;
    fetchData();
    refreshRef.current = setInterval(fetchData, 15000);
    return () => clearInterval(refreshRef.current);
  }, [fetchData, hasFilaFarmAccess]);

  useEffect(() => {
    return () => {
      if (commandTimeoutRef.current) clearTimeout(commandTimeoutRef.current);
    };
  }, []);

  const handleCommand = async (printerId, command) => {
    try {
      await api.post(`/api/v1/pro/filafarm/printers/${printerId}/command`, {
        command,
      });
      toast.success(`Sent "${command}" to printer`);
      if (commandTimeoutRef.current) clearTimeout(commandTimeoutRef.current);
      commandTimeoutRef.current = setTimeout(fetchData, 1000);
    } catch (err) {
      toast.error(err.message);
    }
  };

  if (flagsLoading) {
    return (
      <div className="p-6 flex justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (!hasFilaFarmAccess) {
    return (
      <div className="p-6 text-center">
        <div className="bg-gray-800 rounded-lg p-8 max-w-md mx-auto">
          <svg
            className="w-12 h-12 text-gray-600 mx-auto mb-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
          <h2 className="text-lg font-medium text-white mb-2">PRO Feature</h2>
          <p className="text-gray-400 text-sm">
            FilaFarm printer automation requires a PRO license with the FilaFarm feature enabled.
          </p>
        </div>
      </div>
    );
  }

  const printingCount = printers.filter((p) => p.status === "printing").length;
  const idleCount = printers.filter((p) => p.status === "idle").length;
  const errorCount = printers.filter((p) => p.status === "error").length;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">FilaFarm</h1>
          <p className="text-gray-400 text-sm">
            Printer automation & job management
          </p>
        </div>
        <button
          onClick={fetchData}
          className="px-3 py-1.5 text-sm bg-gray-700 text-gray-300 rounded hover:bg-gray-600"
        >
          ↻ Refresh
        </button>
      </div>

      {/* Stats row */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-white">
              {stats.jobs_completed ?? 0}
            </div>
            <div className="text-xs text-gray-400">Jobs Completed</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-emerald-400">
              {stats.jobs_printing ?? 0}
            </div>
            <div className="text-xs text-gray-400">Currently Printing</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-blue-400">
              {stats.jobs_queued ?? 0}
            </div>
            <div className="text-xs text-gray-400">In Queue</div>
          </div>
          <div className="bg-gray-800 rounded-lg p-4">
            <div className="text-2xl font-bold text-yellow-400">
              {formatTime(stats.total_print_time ?? 0)}
            </div>
            <div className="text-xs text-gray-400">Total Print Time</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-800 rounded-lg p-1 w-fit">
        {[
          { id: "printers", label: `Printers (${printers.length})` },
          { id: "jobs", label: `Jobs (${jobs.length})` },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-1.5 text-sm rounded ${
              activeTab === tab.id
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:text-white"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Error state */}
      {error && (
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-4 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        </div>
      )}

      {/* Printers tab */}
      {!loading && activeTab === "printers" && (
        <div>
          {printers.length === 0 ? (
            <div className="bg-gray-800 rounded-lg p-8 text-center">
              <p className="text-gray-400">No printers connected</p>
              <p className="text-gray-500 text-sm mt-2">
                Configure printers in FilaFarm edge service, then connect via
                MQTT.
              </p>
            </div>
          ) : (
            <>
              <div className="flex gap-4 mb-4 text-sm">
                <span className="text-emerald-400">
                  {printingCount} printing
                </span>
                <span className="text-gray-400">{idleCount} idle</span>
                {errorCount > 0 && (
                  <span className="text-red-400">{errorCount} error</span>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {printers.map((printer) => (
                  <PrinterCard
                    key={printer.id}
                    printer={printer}
                    onCommand={handleCommand}
                  />
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* Jobs tab */}
      {!loading && activeTab === "jobs" && (
        <div>
          {jobs.length === 0 ? (
            <div className="bg-gray-800 rounded-lg p-8 text-center">
              <p className="text-gray-400">No print jobs</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700 text-left">
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Job
                    </th>
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Status
                    </th>
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Printer
                    </th>
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Progress
                    </th>
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Est. Time
                    </th>
                    <th className="py-2 px-3 text-xs font-medium text-gray-500 uppercase">
                      Priority
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((job) => (
                    <JobRow key={job.id} job={job} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
