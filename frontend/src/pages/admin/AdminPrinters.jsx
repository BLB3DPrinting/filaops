import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import Modal from "../../components/Modal";

const statusColors = {
  offline: "bg-gray-500/20 text-gray-400",
  idle: "bg-green-500/20 text-green-400",
  printing: "bg-blue-500/20 text-blue-400",
  paused: "bg-yellow-500/20 text-yellow-400",
  error: "bg-red-500/20 text-red-400",
  maintenance: "bg-orange-500/20 text-orange-400",
};

const brandLabels = {
  bambulab: "BambuLab",
  klipper: "Klipper/Moonraker",
  octoprint: "OctoPrint",
  prusa: "Prusa",
  creality: "Creality",
  generic: "Generic/Manual",
};

export default function AdminPrinters() {
  const toast = useToast();
  const [activeTab, setActiveTab] = useState("list"); // list | discovery | import
  const [printers, setPrinters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filters, setFilters] = useState({ brand: "all", status: "all", search: "" });

  // Modal states
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showMaintenanceModal, setShowMaintenanceModal] = useState(false);
  const [selectedPrinter, setSelectedPrinter] = useState(null);

  // Maintenance state
  const [maintenanceLogs, setMaintenanceLogs] = useState([]);
  const [maintenanceDue, setMaintenanceDue] = useState({ printers: [], total_overdue: 0, total_due_soon: 0 });
  const [maintenanceLoading, setMaintenanceLoading] = useState(false);

  // Discovery state
  const [discovering, setDiscovering] = useState(false);
  const [discoveredPrinters, setDiscoveredPrinters] = useState([]);
  const [discoveryError, setDiscoveryError] = useState(null);

  // Brand info (models, connection fields)
  const [brandInfo, setBrandInfo] = useState([]);

  // CSV Import state
  const [csvData, setCsvData] = useState("");
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);

  // Connection testing state
  const [testingConnection, setTestingConnection] = useState(null); // printer id being tested

  // Active work tracking
  const [activeWork, setActiveWork] = useState({}); // printer_id -> work info

  const token = localStorage.getItem("adminToken");

  useEffect(() => {
    fetchPrinters();
    fetchBrandInfo();
    fetchActiveWork();
    fetchMaintenanceDue();

    // Poll for active work every 30 seconds
    const interval = setInterval(fetchActiveWork, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (activeTab === "list") {
      fetchPrinters();
    } else if (activeTab === "maintenance") {
      fetchMaintenanceLogs();
      fetchMaintenanceDue();
    }
  }, [activeTab, filters.brand, filters.status]);

  // ============================================================================
  // Data Fetching
  // ============================================================================

  const fetchPrinters = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.brand !== "all") params.set("brand", filters.brand);
      if (filters.status !== "all") params.set("status", filters.status);
      if (filters.search) params.set("search", filters.search);
      params.set("page", "1");
      params.set("page_size", "100");

      const res = await fetch(`${API_URL}/api/v1/printers?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to fetch printers");
      const data = await res.json();
      setPrinters(data.items || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchBrandInfo = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/printers/brands/info`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setBrandInfo(data);
      }
    } catch {
      // Non-critical
    }
  };

  const fetchActiveWork = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/printers/active-work`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setActiveWork(data.printers || {});
      }
    } catch {
      // Non-critical - polling will retry
    }
  };

  const fetchMaintenanceLogs = async () => {
    setMaintenanceLoading(true);
    try {
      const res = await fetch(`${API_URL}/api/v1/maintenance/?page_size=50`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMaintenanceLogs(data.items || []);
      }
    } catch (err) {
      console.error("Error fetching maintenance logs:", err);
    } finally {
      setMaintenanceLoading(false);
    }
  };

  const fetchMaintenanceDue = async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/maintenance/due?days_ahead=14`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setMaintenanceDue(data);
      }
    } catch {
      // Non-critical
    }
  };

  // ============================================================================
  // Actions
  // ============================================================================

  const handleDiscover = async () => {
    setDiscovering(true);
    setDiscoveryError(null);
    setDiscoveredPrinters([]);

    try {
      const res = await fetch(`${API_URL}/api/v1/printers/discover`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ timeout_seconds: 10 }),
      });

      if (!res.ok) throw new Error("Discovery failed");

      const data = await res.json();
      setDiscoveredPrinters(data.printers || []);

      if (data.printers?.length === 0) {
        toast.info("No printers found on the network");
      } else {
        toast.success(`Found ${data.printers.length} printer(s)`);
      }
    } catch (err) {
      setDiscoveryError(err.message);
      toast.error("Discovery failed: " + err.message);
    } finally {
      setDiscovering(false);
    }
  };

  const handleAddDiscovered = async (discovered) => {
    try {
      const res = await fetch(`${API_URL}/api/v1/printers`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          code: discovered.suggested_code,
          name: discovered.name,
          model: discovered.model,
          brand: discovered.brand,
          ip_address: discovered.ip_address,
          serial_number: discovered.serial_number,
          capabilities: discovered.capabilities,
        }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to add printer");
      }

      toast.success(`Printer "${discovered.name}" added successfully`);
      fetchPrinters();

      // Mark as registered in discovered list
      setDiscoveredPrinters((prev) =>
        prev.map((p) =>
          p.ip_address === discovered.ip_address
            ? { ...p, already_registered: true }
            : p
        )
      );
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleTestConnection = async (printer) => {
    if (!printer.ip_address) {
      toast.error("No IP address configured for this printer");
      return;
    }

    setTestingConnection(printer.id);

    try {
      const res = await fetch(`${API_URL}/api/v1/printers/test-connection`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          brand: printer.brand,
          ip_address: printer.ip_address,
          connection_config: printer.connection_config || {},
        }),
      });

      if (!res.ok) throw new Error("Connection test failed");

      const result = await res.json();

      if (result.success) {
        toast.success(`${printer.name}: Connected! (${Math.round(result.response_time_ms)}ms)`);
        // Update printer status to idle
        await fetch(`${API_URL}/api/v1/printers/${printer.id}/status`, {
          method: "PATCH",
          headers: {
            Authorization: `Bearer ${token}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ status: "idle" }),
        });
        fetchPrinters();
      } else {
        toast.error(`${printer.name}: ${result.message || "Connection failed"}`);
      }
    } catch (err) {
      toast.error(`${printer.name}: ${err.message}`);
    } finally {
      setTestingConnection(null);
    }
  };

  const handleDelete = async (printer) => {
    if (!confirm(`Delete printer "${printer.name}"? This cannot be undone.`)) {
      return;
    }

    try {
      const res = await fetch(`${API_URL}/api/v1/printers/${printer.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      });

      if (!res.ok) throw new Error("Failed to delete printer");

      toast.success(`Printer "${printer.name}" deleted`);
      fetchPrinters();
    } catch (err) {
      toast.error(err.message);
    }
  };

  const handleImportCSV = async () => {
    if (!csvData.trim()) {
      toast.error("Please enter CSV data");
      return;
    }

    setImporting(true);
    setImportResult(null);

    try {
      const res = await fetch(`${API_URL}/api/v1/printers/import-csv`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ csv_data: csvData, skip_duplicates: true }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Import failed");
      }

      const result = await res.json();
      setImportResult(result);

      if (result.imported > 0) {
        toast.success(`Imported ${result.imported} printer(s)`);
        fetchPrinters();
      } else if (result.skipped > 0) {
        toast.info(`Skipped ${result.skipped} duplicate(s)`);
      }
    } catch (err) {
      toast.error(err.message);
    } finally {
      setImporting(false);
    }
  };

  // ============================================================================
  // Render
  // ============================================================================

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-white">Printers</h1>
          <p className="text-gray-400 mt-1">
            Manage your 3D printer fleet
          </p>
        </div>
        <div className="flex gap-3">
          {printers.filter(p => p.ip_address).length > 0 && (
            <button
              onClick={async () => {
                const printersWithIP = printers.filter(p => p.ip_address);
                toast.info(`Testing ${printersWithIP.length} printer(s)...`);
                for (const printer of printersWithIP) {
                  await handleTestConnection(printer);
                }
              }}
              className="text-gray-300 hover:text-white border border-gray-700 px-4 py-2 rounded-lg transition-colors flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h.01M12 12h.01M19 12h.01M6 12a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0zm7 0a1 1 0 11-2 0 1 1 0 012 0z" />
              </svg>
              Test All
            </button>
          )}
          <button
            onClick={() => setShowAddModal(true)}
            className="bg-gradient-to-r from-blue-600 to-purple-600 text-white px-4 py-2 rounded-lg hover:from-blue-500 hover:to-purple-500 transition-all flex items-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            Add Printer
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-700">
        <nav className="flex gap-8">
          {[
            { id: "list", label: "All Printers", count: printers.length },
            { id: "maintenance", label: "Maintenance", badge: maintenanceDue.total_overdue > 0 ? maintenanceDue.total_overdue : null, badgeColor: "bg-orange-500" },
            { id: "discovery", label: "Network Discovery" },
            { id: "import", label: "CSV Import" },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-4 px-1 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? "border-blue-500 text-blue-400"
                  : "border-transparent text-gray-400 hover:text-white"
              }`}
            >
              {tab.label}
              {tab.count !== undefined && (
                <span className="ml-2 px-2 py-0.5 text-xs bg-gray-700 rounded-full">
                  {tab.count}
                </span>
              )}
              {tab.badge && (
                <span className={`ml-2 px-2 py-0.5 text-xs ${tab.badgeColor} text-white rounded-full`}>
                  {tab.badge}
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === "list" && (
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex gap-4 flex-wrap">
            <input
              type="text"
              placeholder="Search printers..."
              value={filters.search}
              onChange={(e) => setFilters({ ...filters, search: e.target.value })}
              onKeyDown={(e) => e.key === "Enter" && fetchPrinters()}
              className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-64"
            />
            <select
              value={filters.brand}
              onChange={(e) => setFilters({ ...filters, brand: e.target.value })}
              className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Brands</option>
              {Object.entries(brandLabels).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <select
              value={filters.status}
              onChange={(e) => setFilters({ ...filters, status: e.target.value })}
              className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Status</option>
              <option value="offline">Offline</option>
              <option value="idle">Idle</option>
              <option value="printing">Printing</option>
              <option value="error">Error</option>
            </select>
          </div>

          {/* Printer List */}
          {loading ? (
            <div className="text-center py-12 text-gray-400">Loading printers...</div>
          ) : error ? (
            <div className="text-center py-12 text-red-400">{error}</div>
          ) : printers.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-gray-400 mb-4">No printers found</div>
              <button
                onClick={() => setActiveTab("discovery")}
                className="text-blue-400 hover:text-blue-300"
              >
                Try network discovery to find printers
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {printers.map((printer) => (
                <div
                  key={printer.id}
                  className="bg-gray-800 border border-gray-700 rounded-xl p-4 hover:border-gray-600 transition-colors"
                >
                  <div className="flex justify-between items-start mb-3">
                    <div>
                      <h3 className="text-white font-medium">{printer.name}</h3>
                      <p className="text-gray-500 text-sm">{printer.code}</p>
                    </div>
                    <span className={`px-2 py-1 rounded-full text-xs ${statusColors[printer.status] || statusColors.offline}`}>
                      {printer.status}
                    </span>
                  </div>

                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="text-gray-400">Brand</span>
                      <span className="text-white">{brandLabels[printer.brand] || printer.brand}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-400">Model</span>
                      <span className="text-white">{printer.model}</span>
                    </div>
                    {printer.ip_address && (
                      <div className="flex justify-between">
                        <span className="text-gray-400">IP</span>
                        <span className="text-gray-300 font-mono text-xs">{printer.ip_address}</span>
                      </div>
                    )}
                    {printer.location && (
                      <div className="flex justify-between">
                        <span className="text-gray-400">Location</span>
                        <span className="text-white">{printer.location}</span>
                      </div>
                    )}
                  </div>

                  {/* Capabilities badges */}
                  <div className="flex gap-2 mt-3 flex-wrap">
                    {printer.has_ams && (
                      <span className="px-2 py-0.5 bg-purple-500/20 text-purple-400 rounded text-xs">AMS</span>
                    )}
                    {printer.has_camera && (
                      <span className="px-2 py-0.5 bg-cyan-500/20 text-cyan-400 rounded text-xs">Camera</span>
                    )}
                    {printer.capabilities?.enclosure && (
                      <span className="px-2 py-0.5 bg-orange-500/20 text-orange-400 rounded text-xs">Enclosure</span>
                    )}
                  </div>

                  {/* Active Work Display */}
                  {activeWork[printer.id] && (
                    <div className="mt-3 p-2 bg-blue-500/10 border border-blue-500/30 rounded-lg">
                      <div className="flex items-center gap-2 mb-1">
                        {activeWork[printer.id].operation_status === "running" ? (
                          <span className="flex h-2 w-2">
                            <span className="animate-ping absolute inline-flex h-2 w-2 rounded-full bg-blue-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                          </span>
                        ) : (
                          <span className="h-2 w-2 rounded-full bg-yellow-500"></span>
                        )}
                        <span className="text-xs font-medium text-blue-400">
                          {activeWork[printer.id].operation_status === "running" ? "Running" : "Queued"}
                        </span>
                      </div>
                      <div className="text-sm text-white font-medium">
                        {activeWork[printer.id].production_order_code}
                      </div>
                      <div className="text-xs text-gray-400 truncate">
                        {activeWork[printer.id].product_name || activeWork[printer.id].product_sku}
                      </div>
                      {activeWork[printer.id].quantity_ordered && (
                        <div className="text-xs text-gray-500 mt-1">
                          {activeWork[printer.id].quantity_completed || 0} / {activeWork[printer.id].quantity_ordered} completed
                        </div>
                      )}
                      {activeWork[printer.id].queue_depth > 0 && (
                        <div className="text-xs text-gray-500 mt-1">
                          +{activeWork[printer.id].queue_depth} in queue
                        </div>
                      )}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex gap-2 mt-4 pt-3 border-t border-gray-700">
                    <button
                      onClick={() => handleTestConnection(printer)}
                      disabled={testingConnection === printer.id || !printer.ip_address}
                      className={`flex-1 text-sm py-1 ${
                        printer.ip_address
                          ? "text-green-400 hover:text-green-300"
                          : "text-gray-600 cursor-not-allowed"
                      }`}
                      title={printer.ip_address ? "Test connection" : "No IP configured"}
                    >
                      {testingConnection === printer.id ? (
                        <span className="flex items-center justify-center gap-1">
                          <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                          </svg>
                          Testing
                        </span>
                      ) : (
                        "Test"
                      )}
                    </button>
                    <button
                      onClick={() => {
                        setSelectedPrinter(printer);
                        setShowEditModal(true);
                      }}
                      className="flex-1 text-gray-400 hover:text-white text-sm py-1"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => handleDelete(printer)}
                      className="flex-1 text-red-400 hover:text-red-300 text-sm py-1"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === "discovery" && (
        <div className="space-y-6">
          {/* IP Probe - works from Docker */}
          <IPProbeSection
            token={token}
            onPrinterFound={(printer) => {
              setDiscoveredPrinters((prev) => {
                // Don't add duplicates
                if (prev.some((p) => p.ip_address === printer.ip_address)) {
                  return prev;
                }
                return [...prev, printer];
              });
            }}
          />

          {/* Network Scan - may not work from Docker */}
          <div className="bg-gray-800 border border-gray-700 rounded-xl p-6">
            <h2 className="text-lg font-medium text-white mb-2">Network Scan</h2>
            <p className="text-gray-400 text-sm mb-4">
              Automatic network discovery via SSDP/mDNS.
              <span className="text-yellow-500 ml-1">
                Note: May not work when running in Docker.
              </span>
            </p>

            <button
              onClick={handleDiscover}
              disabled={discovering}
              className="bg-gray-700 hover:bg-gray-600 disabled:bg-gray-700/50 text-white px-6 py-2 rounded-lg transition-colors flex items-center gap-2"
            >
              {discovering ? (
                <>
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Scanning...
                </>
              ) : (
                <>
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  Try Network Scan
                </>
              )}
            </button>

            {discoveryError && (
              <div className="mt-4 text-red-400 text-sm">{discoveryError}</div>
            )}
          </div>

          {/* Discovered Printers */}
          {discoveredPrinters.length > 0 && (
            <div className="space-y-4">
              <h3 className="text-white font-medium">Discovered Printers ({discoveredPrinters.length})</h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {discoveredPrinters.map((printer, idx) => (
                  <div
                    key={idx}
                    className={`bg-gray-800 border rounded-xl p-4 ${
                      printer.already_registered ? "border-green-500/30" : "border-gray-700"
                    }`}
                  >
                    <div className="flex justify-between items-start mb-3">
                      <div>
                        <h4 className="text-white font-medium">{printer.name}</h4>
                        <p className="text-gray-500 text-sm">{printer.model}</p>
                      </div>
                      <span className="px-2 py-1 bg-blue-500/20 text-blue-400 rounded text-xs">
                        {brandLabels[printer.brand] || printer.brand}
                      </span>
                    </div>

                    <div className="space-y-1 text-sm mb-4">
                      <div className="flex justify-between">
                        <span className="text-gray-400">IP Address</span>
                        <span className="text-gray-300 font-mono">{printer.ip_address}</span>
                      </div>
                      {printer.serial_number && (
                        <div className="flex justify-between">
                          <span className="text-gray-400">Serial</span>
                          <span className="text-gray-300 font-mono text-xs">{printer.serial_number}</span>
                        </div>
                      )}
                    </div>

                    {printer.already_registered ? (
                      <div className="text-green-400 text-sm flex items-center gap-2">
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                        </svg>
                        Already registered
                      </div>
                    ) : (
                      <button
                        onClick={() => handleAddDiscovered(printer)}
                        className="w-full bg-green-600 hover:bg-green-500 text-white py-2 rounded-lg text-sm transition-colors"
                      >
                        Add to Fleet
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === "import" && (
        <div className="space-y-6">
          <div className="bg-gray-800 border border-gray-700 rounded-xl p-6">
            <h2 className="text-lg font-medium text-white mb-2">CSV Import</h2>
            <p className="text-gray-400 text-sm mb-4">
              Import multiple printers at once using CSV format. Great for large print farms.
            </p>

            <div className="mb-4">
              <label className="block text-sm text-gray-300 mb-2">CSV Format</label>
              <div className="bg-gray-900 p-3 rounded-lg font-mono text-xs text-gray-400 overflow-x-auto">
                code,name,model,brand,serial_number,ip_address,location,notes
              </div>
            </div>

            <div className="mb-4">
              <label className="block text-sm text-gray-300 mb-2">Example</label>
              <div className="bg-gray-900 p-3 rounded-lg font-mono text-xs text-gray-400 overflow-x-auto">
                PRT-001,X1C-Bay1,X1 Carbon,bambulab,ABC123,192.168.1.100,Farm A,Bay 1<br />
                PRT-002,P1S-Bay2,P1S,bambulab,DEF456,192.168.1.101,Farm A,Bay 2
              </div>
            </div>

            <textarea
              value={csvData}
              onChange={(e) => setCsvData(e.target.value)}
              placeholder="Paste your CSV data here (include header row)..."
              className="w-full bg-gray-900 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono text-sm h-48"
            />

            <div className="mt-4 flex gap-4">
              <button
                onClick={handleImportCSV}
                disabled={importing || !csvData.trim()}
                className="bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 text-white px-6 py-2 rounded-lg transition-colors"
              >
                {importing ? "Importing..." : "Import Printers"}
              </button>
              <button
                onClick={() => {
                  setCsvData("code,name,model,brand,serial_number,ip_address,location,notes\n");
                }}
                className="text-gray-400 hover:text-white px-4 py-2"
              >
                Add Header Row
              </button>
            </div>

            {importResult && (
              <div className="mt-4 p-4 bg-gray-900 rounded-lg">
                <div className="grid grid-cols-3 gap-4 text-center mb-4">
                  <div>
                    <div className="text-2xl font-bold text-green-400">{importResult.imported}</div>
                    <div className="text-gray-400 text-sm">Imported</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-yellow-400">{importResult.skipped}</div>
                    <div className="text-gray-400 text-sm">Skipped</div>
                  </div>
                  <div>
                    <div className="text-2xl font-bold text-red-400">{importResult.errors?.length || 0}</div>
                    <div className="text-gray-400 text-sm">Errors</div>
                  </div>
                </div>

                {importResult.errors?.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-red-400 text-sm font-medium">Errors:</div>
                    {importResult.errors.map((err, idx) => (
                      <div key={idx} className="text-red-400/70 text-xs">
                        Row {err.row}: {err.error}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Maintenance Tab */}
      {activeTab === "maintenance" && (
        <div className="space-y-6">
          {/* Maintenance Due Summary */}
          {(maintenanceDue.total_overdue > 0 || maintenanceDue.total_due_soon > 0) && (
            <div className="bg-orange-500/10 border border-orange-500/30 rounded-xl p-4">
              <div className="flex items-center gap-3 mb-3">
                <svg className="w-6 h-6 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <h3 className="text-orange-400 font-medium">Maintenance Due</h3>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-2xl font-bold text-red-400">{maintenanceDue.total_overdue}</div>
                  <div className="text-gray-400 text-sm">Overdue</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-yellow-400">{maintenanceDue.total_due_soon}</div>
                  <div className="text-gray-400 text-sm">Due in 14 days</div>
                </div>
              </div>
              {maintenanceDue.printers.length > 0 && (
                <div className="mt-4 space-y-2">
                  {maintenanceDue.printers.slice(0, 5).map((p) => (
                    <div key={p.printer_id} className="flex justify-between items-center text-sm">
                      <span className="text-white">{p.printer_name} ({p.printer_code})</span>
                      <span className={p.days_overdue > 0 ? "text-red-400" : "text-yellow-400"}>
                        {p.days_overdue > 0 ? `${p.days_overdue} days overdue` : `Due in ${Math.abs(p.days_overdue)} days`}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Log Maintenance Button */}
          <div className="flex justify-between items-center">
            <h2 className="text-lg font-medium text-white">Maintenance History</h2>
            <button
              onClick={() => {
                setSelectedPrinter(null);
                setShowMaintenanceModal(true);
              }}
              className="bg-orange-600 hover:bg-orange-500 text-white px-4 py-2 rounded-lg flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Log Maintenance
            </button>
          </div>

          {/* Maintenance Logs Table */}
          {maintenanceLoading ? (
            <div className="text-center py-12 text-gray-400">Loading maintenance logs...</div>
          ) : maintenanceLogs.length === 0 ? (
            <div className="text-center py-12">
              <div className="text-gray-400 mb-2">No maintenance logs yet</div>
              <p className="text-gray-500 text-sm">Log your first maintenance activity to start tracking printer health.</p>
            </div>
          ) : (
            <div className="bg-gray-800 border border-gray-700 rounded-xl overflow-hidden">
              <table className="w-full">
                <thead className="bg-gray-900/50">
                  <tr>
                    <th className="py-3 px-4 text-left text-xs font-medium text-gray-400 uppercase">Date</th>
                    <th className="py-3 px-4 text-left text-xs font-medium text-gray-400 uppercase">Printer</th>
                    <th className="py-3 px-4 text-left text-xs font-medium text-gray-400 uppercase">Type</th>
                    <th className="py-3 px-4 text-left text-xs font-medium text-gray-400 uppercase">Description</th>
                    <th className="py-3 px-4 text-right text-xs font-medium text-gray-400 uppercase">Cost</th>
                    <th className="py-3 px-4 text-right text-xs font-medium text-gray-400 uppercase">Downtime</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-700">
                  {maintenanceLogs.map((log) => {
                    const printer = printers.find((p) => p.id === log.printer_id);
                    return (
                      <tr key={log.id} className="hover:bg-gray-700/30">
                        <td className="py-3 px-4 text-gray-300 text-sm">
                          {new Date(log.performed_at).toLocaleDateString()}
                        </td>
                        <td className="py-3 px-4 text-white font-medium">
                          {printer?.name || `Printer #${log.printer_id}`}
                        </td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-1 rounded-full text-xs capitalize ${
                            log.maintenance_type === "repair" ? "bg-red-500/20 text-red-400" :
                            log.maintenance_type === "routine" ? "bg-green-500/20 text-green-400" :
                            log.maintenance_type === "calibration" ? "bg-blue-500/20 text-blue-400" :
                            "bg-purple-500/20 text-purple-400"
                          }`}>
                            {log.maintenance_type}
                          </span>
                        </td>
                        <td className="py-3 px-4 text-gray-400 text-sm max-w-xs truncate">
                          {log.description || "-"}
                        </td>
                        <td className="py-3 px-4 text-right text-gray-300">
                          {log.cost ? `$${parseFloat(log.cost).toFixed(2)}` : "-"}
                        </td>
                        <td className="py-3 px-4 text-right text-gray-300">
                          {log.downtime_minutes ? `${log.downtime_minutes} min` : "-"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Add Printer Modal */}
      {showAddModal && (
        <PrinterModal
          onClose={() => setShowAddModal(false)}
          onSave={() => {
            setShowAddModal(false);
            fetchPrinters();
          }}
          brandInfo={brandInfo}
        />
      )}

      {/* Edit Printer Modal */}
      {showEditModal && selectedPrinter && (
        <PrinterModal
          printer={selectedPrinter}
          onClose={() => {
            setShowEditModal(false);
            setSelectedPrinter(null);
          }}
          onSave={() => {
            setShowEditModal(false);
            setSelectedPrinter(null);
            fetchPrinters();
          }}
          brandInfo={brandInfo}
        />
      )}

      {/* Log Maintenance Modal */}
      {showMaintenanceModal && (
        <MaintenanceModal
          printers={printers}
          selectedPrinterId={selectedPrinter?.id}
          onClose={() => {
            setShowMaintenanceModal(false);
            setSelectedPrinter(null);
          }}
          onSave={() => {
            setShowMaintenanceModal(false);
            setSelectedPrinter(null);
            fetchMaintenanceLogs();
            fetchMaintenanceDue();
          }}
        />
      )}
    </div>
  );
}

// ============================================================================
// Printer Modal Component
// ============================================================================

function PrinterModal({ printer, onClose, onSave, brandInfo }) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [workCenters, setWorkCenters] = useState([]);
  const [form, setForm] = useState({
    code: printer?.code || "",
    name: printer?.name || "",
    model: printer?.model || "",
    brand: printer?.brand || "generic",
    serial_number: printer?.serial_number || "",
    ip_address: printer?.ip_address || "",
    access_code: printer?.connection_config?.access_code || "",
    location: printer?.location || "",
    work_center_id: printer?.work_center_id || "",
    notes: printer?.notes || "",
    active: printer?.active !== false,
  });

  const token = localStorage.getItem("adminToken");
  const isEdit = !!printer;

  // Fetch machine-type work centers on mount
  useEffect(() => {
    const fetchWorkCenters = async () => {
      try {
        const res = await fetch(`${API_URL}/api/v1/work-centers/?center_type=machine`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const data = await res.json();
          setWorkCenters(data);
        }
      } catch {
        // Non-critical - work center selection is optional
      }
    };
    fetchWorkCenters();
  }, [token]);

  // Get models for selected brand
  const selectedBrand = brandInfo.find((b) => b.code === form.brand);
  const models = selectedBrand?.models || [];

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const url = isEdit
        ? `${API_URL}/api/v1/printers/${printer.id}`
        : `${API_URL}/api/v1/printers`;

      // Build payload with connection_config for brand-specific settings
      const { access_code, ...rest } = form;
      const payload = {
        ...rest,
        connection_config: access_code ? { access_code } : {},
      };

      const res = await fetch(url, {
        method: isEdit ? "PUT" : "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to save printer");
      }

      toast.success(isEdit ? "Printer updated" : "Printer added");
      onSave();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const generateCode = async () => {
    try {
      const prefix = form.brand === "generic" ? "PRT" : form.brand.toUpperCase().slice(0, 3);
      const res = await fetch(`${API_URL}/api/v1/printers/generate-code?prefix=${prefix}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const data = await res.json();
        setForm({ ...form, code: data.code });
      }
    } catch {
      // Non-critical
    }
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={isEdit ? "Edit Printer" : "Add Printer"}
      className="w-full max-w-lg max-h-[90vh] overflow-y-auto"
      disableClose={loading}
    >
      <div className="p-6 border-b border-gray-700">
        <h2 className="text-xl font-bold text-white">
          {isEdit ? "Edit Printer" : "Add Printer"}
        </h2>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Brand */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Brand</label>
            <select
              value={form.brand}
              onChange={(e) => setForm({ ...form, brand: e.target.value, model: "" })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {Object.entries(brandLabels).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          {/* Model */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Model *</label>
            {models.length > 0 ? (
              <select
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
                required
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select model...</option>
                {models.map((m) => (
                  <option key={m.value} value={m.value}>{m.label}</option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={form.model}
                onChange={(e) => setForm({ ...form, model: e.target.value })}
                required
                placeholder="e.g., Ender 3 V2"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            )}
          </div>

          {/* Code */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Code *</label>
            <div className="flex gap-2">
              <input
                type="text"
                value={form.code}
                onChange={(e) => setForm({ ...form, code: e.target.value })}
                required
                placeholder="PRT-001"
                className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              {!isEdit && (
                <button
                  type="button"
                  onClick={generateCode}
                  className="px-3 py-2 text-gray-400 hover:text-white border border-gray-700 rounded-lg"
                >
                  Auto
                </button>
              )}
            </div>
          </div>

          {/* Name */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Name *</label>
            <input
              type="text"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
              placeholder="e.g., X1C Bay 1"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* IP Address */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">IP Address</label>
            <input
              type="text"
              value={form.ip_address}
              onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
              placeholder="192.168.1.100"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Access Code - BambuLab only */}
          {form.brand === "bambulab" && (
            <div>
              <label className="block text-sm text-gray-300 mb-1">LAN Access Code</label>
              <input
                type="text"
                value={form.access_code}
                onChange={(e) => setForm({ ...form, access_code: e.target.value })}
                placeholder="8-digit code from printer"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="text-xs text-gray-500 mt-1">
                Find this in your printer's network settings
              </p>
            </div>
          )}

          {/* Serial Number */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Serial Number</label>
            <input
              type="text"
              value={form.serial_number}
              onChange={(e) => setForm({ ...form, serial_number: e.target.value })}
              placeholder="Optional"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Location */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Location</label>
            <input
              type="text"
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
              placeholder="e.g., Farm A, Bay 1"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Work Center (Machine Pool) */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Machine Pool</label>
            <select
              value={form.work_center_id}
              onChange={(e) => setForm({ ...form, work_center_id: e.target.value ? parseInt(e.target.value) : "" })}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="">None</option>
              {workCenters.map((wc) => (
                <option key={wc.id} value={wc.id}>{wc.name}</option>
              ))}
            </select>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Notes</label>
            <textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Optional notes..."
              rows={2}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Active toggle */}
          <div className="flex items-center gap-3">
            <input
              type="checkbox"
              id="active"
              checked={form.active}
              onChange={(e) => setForm({ ...form, active: e.target.checked })}
              className="w-4 h-4 rounded bg-gray-800 border-gray-700 text-blue-500 focus:ring-blue-500"
            />
            <label htmlFor="active" className="text-gray-300">Active</label>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4 border-t border-gray-700">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 text-gray-400 hover:text-white border border-gray-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 text-white px-4 py-2 rounded-lg transition-colors"
            >
              {loading ? "Saving..." : isEdit ? "Update" : "Add Printer"}
            </button>
          </div>
      </form>
    </Modal>
  );
}

// ============================================================================
// IP Probe Component - For discovering printers by IP address
// ============================================================================

function IPProbeSection({ token, onPrinterFound }) {
  const toast = useToast();
  const [ipAddress, setIpAddress] = useState("");
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState(null);

  const handleProbe = async () => {
    if (!ipAddress.trim()) {
      toast.error("Please enter an IP address");
      return;
    }

    // Basic IP validation
    const ipRegex = /^(\d{1,3}\.){3}\d{1,3}$/;
    if (!ipRegex.test(ipAddress.trim())) {
      toast.error("Please enter a valid IP address");
      return;
    }

    setProbing(true);
    setProbeResult(null);

    try {
      const res = await fetch(
        `${API_URL}/api/v1/printers/probe-ip?ip_address=${encodeURIComponent(ipAddress.trim())}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        }
      );

      if (!res.ok) throw new Error("Probe failed");

      const result = await res.json();
      setProbeResult(result);

      if (result.reachable) {
        toast.success(`Found ${result.brand || "printer"} at ${ipAddress}`);
        if (!result.already_registered) {
          // Add to discovered list
          onPrinterFound({
            ip_address: result.ip_address,
            brand: result.brand || "generic",
            model: result.model,
            name: result.suggested_name,
            suggested_code: result.suggested_code,
            already_registered: false,
          });
        }
      } else {
        toast.error(`No printer found at ${ipAddress}`);
      }
    } catch (err) {
      toast.error("Failed to probe IP: " + err.message);
    } finally {
      setProbing(false);
    }
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-6">
      <h2 className="text-lg font-medium text-white mb-2">Find Printer by IP</h2>
      <p className="text-gray-400 text-sm mb-4">
        Enter a printer's IP address to detect it. Works with BambuLab, Klipper, and OctoPrint.
      </p>

      <div className="flex gap-3">
        <input
          type="text"
          value={ipAddress}
          onChange={(e) => setIpAddress(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleProbe()}
          placeholder="192.168.1.100"
          className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
        />
        <button
          onClick={handleProbe}
          disabled={probing}
          className="bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 text-white px-6 py-2 rounded-lg transition-colors flex items-center gap-2"
        >
          {probing ? (
            <>
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Probing...
            </>
          ) : (
            <>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
              </svg>
              Probe
            </>
          )}
        </button>
      </div>

      {/* Probe Result */}
      {probeResult && (
        <div className={`mt-4 p-3 rounded-lg ${probeResult.reachable ? "bg-green-500/10 border border-green-500/30" : "bg-red-500/10 border border-red-500/30"}`}>
          {probeResult.reachable ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-green-400 font-medium">Printer Found!</span>
              </div>
              <div className="text-sm text-gray-300 space-y-1">
                <div>Brand: <span className="text-white">{probeResult.brand || "Unknown"}</span></div>
                <div>Open ports: <span className="text-white font-mono text-xs">{probeResult.ports_open?.map(p => `${p.port} (${p.service})`).join(", ") || "None"}</span></div>
                {probeResult.already_registered && (
                  <div className="text-yellow-400">
                    Already registered as: {probeResult.existing_printer?.name} ({probeResult.existing_printer?.code})
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-red-400">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              <span>No printer detected at this IP</span>
            </div>
          )}
        </div>
      )}

      {/* Quick tip */}
      <div className="mt-4 text-xs text-gray-500">
        Tip: Check your router's DHCP client list to find printer IPs, or look in your printer's network settings.
      </div>
    </div>
  );
}

// ============================================================================
// Maintenance Modal Component
// ============================================================================

function MaintenanceModal({ printers, selectedPrinterId, onClose, onSave }) {
  const toast = useToast();
  const [loading, setLoading] = useState(false);
  const [form, setForm] = useState({
    printer_id: selectedPrinterId || "",
    maintenance_type: "routine",
    description: "",
    performed_by: "",
    performed_at: new Date().toISOString().slice(0, 16),
    next_due_at: "",
    cost: "",
    downtime_minutes: "",
    parts_used: "",
    notes: "",
  });

  const token = localStorage.getItem("adminToken");

  const maintenanceTypes = [
    { value: "routine", label: "Routine Maintenance", description: "Regular scheduled maintenance" },
    { value: "repair", label: "Repair", description: "Fixing a broken component" },
    { value: "calibration", label: "Calibration", description: "Bed leveling, extrusion tuning" },
    { value: "cleaning", label: "Cleaning", description: "Nozzle, bed, or general cleaning" },
  ];

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!form.printer_id) {
      toast.error("Please select a printer");
      return;
    }

    setLoading(true);

    try {
      const payload = {
        maintenance_type: form.maintenance_type,
        description: form.description || null,
        performed_by: form.performed_by || null,
        performed_at: form.performed_at ? new Date(form.performed_at).toISOString() : new Date().toISOString(),
        next_due_at: form.next_due_at ? new Date(form.next_due_at).toISOString() : null,
        cost: form.cost ? parseFloat(form.cost) : null,
        downtime_minutes: form.downtime_minutes ? parseInt(form.downtime_minutes) : null,
        parts_used: form.parts_used || null,
        notes: form.notes || null,
      };

      const res = await fetch(`${API_URL}/api/v1/maintenance/printers/${form.printer_id}/maintenance`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Failed to log maintenance");
      }

      toast.success("Maintenance logged successfully");
      onSave();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title="Log Maintenance"
      className="w-full max-w-lg max-h-[90vh] overflow-y-auto"
      disableClose={loading}
    >
      <div className="p-6 border-b border-gray-700">
        <h2 className="text-xl font-bold text-white">Log Maintenance</h2>
        <p className="text-gray-400 text-sm mt-1">Track maintenance activities, costs, and downtime</p>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Printer Selection */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Printer *</label>
            <select
              value={form.printer_id}
              onChange={(e) => setForm({ ...form, printer_id: e.target.value })}
              required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
            >
              <option value="">Select printer...</option>
              {printers.map((p) => (
                <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
              ))}
            </select>
          </div>

          {/* Maintenance Type */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Type *</label>
            <select
              value={form.maintenance_type}
              onChange={(e) => setForm({ ...form, maintenance_type: e.target.value })}
              required
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
            >
              {maintenanceTypes.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Description</label>
            <input
              type="text"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
              placeholder="e.g., Replaced nozzle, cleaned bed"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
            />
          </div>

          {/* Performed By */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Performed By</label>
            <input
              type="text"
              value={form.performed_by}
              onChange={(e) => setForm({ ...form, performed_by: e.target.value })}
              placeholder="Your name"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
            />
          </div>

          {/* Date/Time Row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-300 mb-1">Performed At *</label>
              <input
                type="datetime-local"
                value={form.performed_at}
                onChange={(e) => setForm({ ...form, performed_at: e.target.value })}
                required
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Next Due</label>
              <input
                type="datetime-local"
                value={form.next_due_at}
                onChange={(e) => setForm({ ...form, next_due_at: e.target.value })}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white focus:outline-none focus:ring-2 focus:ring-orange-500"
              />
            </div>
          </div>

          {/* Cost and Downtime Row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-gray-300 mb-1">Cost ($)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={form.cost}
                onChange={(e) => setForm({ ...form, cost: e.target.value })}
                placeholder="0.00"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">Downtime (minutes)</label>
              <input
                type="number"
                min="0"
                value={form.downtime_minutes}
                onChange={(e) => setForm({ ...form, downtime_minutes: e.target.value })}
                placeholder="0"
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
              />
            </div>
          </div>

          {/* Parts Used */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Parts Used</label>
            <input
              type="text"
              value={form.parts_used}
              onChange={(e) => setForm({ ...form, parts_used: e.target.value })}
              placeholder="e.g., Hardened nozzle 0.4mm, PTFE tube"
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
            />
            <p className="text-xs text-gray-500 mt-1">Comma-separated list of parts used</p>
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm text-gray-300 mb-1">Notes</label>
            <textarea
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              placeholder="Additional notes..."
              rows={2}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-orange-500"
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4 border-t border-gray-700">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 text-gray-400 hover:text-white border border-gray-700 rounded-lg transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 bg-orange-600 hover:bg-orange-500 disabled:bg-orange-600/50 text-white px-4 py-2 rounded-lg transition-colors"
            >
              {loading ? "Saving..." : "Log Maintenance"}
            </button>
          </div>
      </form>
    </Modal>
  );
}
