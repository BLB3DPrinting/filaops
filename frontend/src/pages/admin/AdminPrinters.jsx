/**
 * AdminPrinters - Printer fleet management orchestrator.
 *
 * Sub-components extracted per ARCHITECT-002:
 *   PrinterModal, IPProbeSection, MaintenanceModal, constants
 */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../../components/Toast";
import { statusColors, brandLabels, MAINTENANCE_TYPE_CLASS } from "../../components/printers/constants";
import PrinterModal from "../../components/printers/PrinterModal";
import IPProbeSection from "../../components/printers/IPProbeSection";
import MaintenanceModal from "../../components/printers/MaintenanceModal";

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
        credentials: "include",
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
        credentials: "include",
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
        credentials: "include",
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
        credentials: "include",
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
        credentials: "include",
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
        credentials: "include",
        headers: {
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
        credentials: "include",
        headers: {
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
        credentials: "include",
        headers: {
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
          credentials: "include",
          headers: {
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
        credentials: "include",
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
        credentials: "include",
        headers: {
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
                            MAINTENANCE_TYPE_CLASS[log.maintenance_type] || "bg-purple-500/20 text-purple-400"
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

