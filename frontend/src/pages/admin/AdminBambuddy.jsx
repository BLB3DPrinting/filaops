import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";
import { useApi } from "../../hooks/useApi";

const DEFAULT_BAMBUDDY_URL = "http://127.0.0.1:8080";

export default function AdminBambuddy() {
  const api = useApi();
  const toast = useToast();
  const { isPro, loading: featuresLoading } = useFeatureFlags();
  const [status, setStatus] = useState(null);
  const [machines, setMachines] = useState([]);
  const [form, setForm] = useState({
    base_url: DEFAULT_BAMBUDDY_URL,
    api_key: "",
  });
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [printers, setPrinters] = useState([]);
  const [selectedMachine, setSelectedMachine] = useState(null);
  const [selectedPrinterId, setSelectedPrinterId] = useState("");
  const [linking, setLinking] = useState(false);
  const [machineError, setMachineError] = useState("");

  const connected = Boolean(status?.connected);
  const openUrl = useMemo(
    () => status?.base_url || form.base_url || DEFAULT_BAMBUDDY_URL,
    [form.base_url, status?.base_url],
  );

  const loadMachines = useCallback(async () => {
    if (!connected) {
      setMachines([]);
      return;
    }
    try {
      setMachineError("");
      const data = await api.get("/api/v1/pro/printer-providers/bambuddy/machines");
      setMachines(Array.isArray(data) ? data : []);
    } catch (err) {
      setMachines([]);
      setMachineError(err.message);
    }
  }, [api, connected]);

  const loadStatus = useCallback(async () => {
    try {
      const data = await api.get("/api/v1/pro/integrations/bambuddy/status");
      setStatus(data);
      if (data?.base_url) {
        setForm((prev) => ({ ...prev, base_url: data.base_url }));
      }
    } catch (err) {
      setStatus({ connected: false, health: "error" });
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [api, toast]);

  const loadPrinters = useCallback(async () => {
    try {
      const data = await api.get("/api/v1/printers?active_only=true&page_size=200");
      setPrinters(Array.isArray(data?.items) ? data.items : []);
    } catch (err) {
      setPrinters([]);
      toast.error(err.message);
    }
  }, [api, toast]);

  useEffect(() => {
    if (featuresLoading || !isPro) return;
    loadStatus();
    loadPrinters();
  }, [featuresLoading, isPro, loadPrinters, loadStatus]);

  useEffect(() => {
    loadMachines();
  }, [loadMachines]);

  const handleConnect = async (event) => {
    event.preventDefault();
    setConnecting(true);
    try {
      const data = await api.post("/api/v1/pro/integrations/bambuddy/connect", {
        base_url: form.base_url.trim(),
        api_key: form.api_key.trim(),
      });
      setStatus(data);
      setForm((prev) => ({ ...prev, api_key: "" }));
      toast.success("Bambuddy connected");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setConnecting(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await api.post("/api/v1/pro/integrations/bambuddy/sync", {});
      await loadStatus();
      await loadMachines();
      toast.success(`Synced ${result.synced || 0} Bambuddy records`);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSyncing(false);
    }
  };

  const openLinkDialog = (machine) => {
    setSelectedMachine(machine);
    setSelectedPrinterId("");
  };

  const closeLinkDialog = () => {
    if (linking) return;
    setSelectedMachine(null);
    setSelectedPrinterId("");
  };

  const handleLink = async (event) => {
    event.preventDefault();
    if (!selectedMachine || !selectedPrinterId) return;
    setLinking(true);
    try {
      await api.post(
        `/api/v1/pro/printer-providers/bambuddy/printers/${encodeURIComponent(
          selectedMachine.external_id,
        )}/link`,
        { filaops_printer_id: Number(selectedPrinterId) },
      );
      await loadMachines();
      setSelectedMachine(null);
      setSelectedPrinterId("");
      toast.success("Bambuddy machine linked");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLinking(false);
    }
  };

  const handleUnlink = async (machine) => {
    setLinking(true);
    try {
      await api.del(
        `/api/v1/pro/printer-providers/bambuddy/printers/${encodeURIComponent(
          machine.external_id,
        )}/link`,
      );
      await loadMachines();
      toast.success("Bambuddy machine unlinked");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLinking(false);
    }
  };

  if (featuresLoading || loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (!isPro) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold text-white">Bambuddy</h1>
        <div className="bg-gray-800/40 border border-gray-700 rounded-lg p-6">
          <h2 className="text-lg font-semibold text-white">PRO required</h2>
          <p className="text-sm text-gray-400 mt-2">
            Bambuddy printer orchestration is available with FilaOps PRO.
          </p>
          <Link
            to="/admin/license"
            className="inline-flex mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium"
          >
            Open License
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Bambuddy</h1>
          <p className="text-gray-400 mt-1">
            Connect FilaOps PRO to the managed Bambuddy service for Bambu printer operations.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => window.open(openUrl, "_blank", "noopener,noreferrer")}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md text-sm font-medium"
          >
            Open Bambuddy
          </button>
          <button
            type="button"
            onClick={loadStatus}
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md text-sm font-medium"
          >
            Refresh
          </button>
        </div>
      </div>

      <section className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-6">
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
              onClick={handleSync}
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

        <form
          onSubmit={handleConnect}
          className="bg-gray-800/40 border border-gray-700 rounded-lg p-6 space-y-4"
        >
          <div>
            <h2 className="text-lg font-semibold text-white">Connection</h2>
            <p className="text-sm text-gray-400 mt-1">
              Use the API key generated in Bambuddy.
            </p>
          </div>
          <label className="block">
            <span className="text-sm font-medium text-gray-300">Bambuddy URL</span>
            <input
              type="url"
              value={form.base_url}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, base_url: event.target.value }))
              }
              className="mt-1 w-full bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder={DEFAULT_BAMBUDDY_URL}
              required
            />
          </label>
          <label className="block">
            <span className="text-sm font-medium text-gray-300">API Key</span>
            <input
              type="password"
              value={form.api_key}
              onChange={(event) =>
                setForm((prev) => ({ ...prev, api_key: event.target.value }))
              }
              className="mt-1 w-full bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              autoComplete="off"
              required
            />
          </label>
          <button
            type="submit"
            disabled={connecting}
            className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-400 text-white rounded-md text-sm font-medium"
          >
            {connecting ? "Connecting..." : connected ? "Update Connection" : "Connect"}
          </button>
        </form>
      </section>

      <section className="bg-gray-800/40 border border-gray-700 rounded-lg overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-700 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">Bambuddy Machines</h2>
            <p className="text-sm text-gray-400">
              Synced printers appear here before they are dispatched through FilaOps jobs.
            </p>
          </div>
          <span className="text-sm text-gray-400">{machines.length} machine(s)</span>
        </div>

        {machineError ? (
          <div className="p-6 text-sm text-red-300 bg-red-500/10 border-t border-red-500/20">
            {machineError}
          </div>
        ) : machines.length === 0 ? (
          <div className="p-8 text-center text-gray-400">
            {connected
              ? "No Bambuddy printers returned yet."
              : "Connect Bambuddy to list managed printers."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-900/60 text-gray-400">
                <tr>
                  <th className="py-3 px-4 text-left font-medium">Machine</th>
                  <th className="py-3 px-4 text-left font-medium">Model</th>
                  <th className="py-3 px-4 text-left font-medium">IP Address</th>
                  <th className="py-3 px-4 text-left font-medium">Status</th>
                  <th className="py-3 px-4 text-left font-medium">FilaOps Printer</th>
                  <th className="py-3 px-4 text-right font-medium">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-700">
                {machines.map((machine) => (
                  <tr key={machine.external_id} className="hover:bg-gray-700/30">
                    <td className="py-3 px-4 text-white font-medium">
                      {machine.name}
                      <div className="text-xs text-gray-500">{machine.external_id}</div>
                    </td>
                    <td className="py-3 px-4 text-gray-300">{machine.model || "-"}</td>
                    <td className="py-3 px-4 text-gray-300">{machine.ip_address || "-"}</td>
                    <td className="py-3 px-4">
                      <span className="inline-flex px-2 py-1 rounded-full border border-gray-600 text-gray-300 text-xs">
                        {machine.status || "unknown"}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-gray-300">
                      {machine.linked_printer ? (
                        <div>
                          <div className="text-white font-medium">
                            {machine.linked_printer.name}
                          </div>
                          <div className="text-xs text-gray-500">
                            {machine.linked_printer.code || `Printer #${machine.linked_printer_id}`}
                          </div>
                        </div>
                      ) : (
                        <span className="text-gray-500">Not linked</span>
                      )}
                    </td>
                    <td className="py-3 px-4 text-right">
                      {machine.linked_printer_id ? (
                        <button
                          type="button"
                          onClick={() => handleUnlink(machine)}
                          disabled={linking}
                          className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-500 text-white rounded-md text-xs font-medium"
                        >
                          Unlink
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => openLinkDialog(machine)}
                          disabled={linking}
                          className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-800 disabled:text-gray-500 text-white rounded-md text-xs font-medium"
                        >
                          Link Printer
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="bg-gray-900/40 border border-gray-700/70 rounded-lg p-5">
        <h2 className="text-sm font-semibold text-gray-200">AGPL Service Notice</h2>
        <p className="text-sm text-gray-400 mt-2">
          Bambuddy runs as a separate AGPL service. FilaOps PRO communicates with it through HTTP APIs.
        </p>
        <a
          href="https://github.com/maziggy/bambuddy"
          target="_blank"
          rel="noreferrer"
          className="inline-flex mt-3 text-sm text-blue-400 hover:text-blue-300"
        >
          Bambuddy source and license
        </a>
      </section>

      {selectedMachine && (
        <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
          <form
            onSubmit={handleLink}
            className="w-full max-w-lg bg-gray-900 border border-gray-700 rounded-lg p-6 space-y-5 shadow-xl"
          >
            <div>
              <h2 className="text-lg font-semibold text-white">Link Printer</h2>
              <p className="text-sm text-gray-400 mt-1">
                Link {selectedMachine.name} to one existing FilaOps printer.
              </p>
            </div>

            {printers.length === 0 ? (
              <div className="bg-gray-800/60 border border-gray-700 rounded-md p-4">
                <p className="text-sm text-gray-300">
                  Create a FilaOps printer before linking Bambuddy machines.
                </p>
                <Link
                  to="/admin/printers"
                  className="inline-flex mt-3 text-sm text-blue-400 hover:text-blue-300"
                >
                  Create printer first
                </Link>
              </div>
            ) : (
              <label className="block">
                <span className="text-sm font-medium text-gray-300">
                  FilaOps printer
                </span>
                <select
                  value={selectedPrinterId}
                  onChange={(event) => setSelectedPrinterId(event.target.value)}
                  className="mt-1 w-full bg-gray-950 border border-gray-700 rounded-md px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                >
                  <option value="">Select a printer</option>
                  {printers.map((printer) => (
                    <option key={printer.id} value={printer.id}>
                      {printer.name} {printer.code ? `(${printer.code})` : ""}
                    </option>
                  ))}
                </select>
              </label>
            )}

            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={closeLinkDialog}
                disabled={linking}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-500 text-white rounded-md text-sm font-medium"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={linking || printers.length === 0 || !selectedPrinterId}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-400 text-white rounded-md text-sm font-medium"
              >
                {linking ? "Linking..." : "Link Printer"}
              </button>
            </div>
          </form>
        </div>
      )}
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

function formatDate(value) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}
