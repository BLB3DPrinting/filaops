/**
 * WorkCenterCard - Expandable card showing work center details, resources, and printers.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";
import {
  getTypeColor,
  getStatusColor,
  TYPE_BADGE_CLASS,
  STATUS_DOT_CLASS,
  STATUS_BADGE_CLASS,
} from "./constants";

export default function WorkCenterCard({
  workCenter,
  onEdit,
  onDelete,
  onAddResource,
  onEditResource,
  onDeleteResource,
}) {
  const toast = useToast();
  const [expanded, setExpanded] = useState(false);
  const [resources, setResources] = useState([]);
  const [printers, setPrinters] = useState([]);
  const [loadingResources, setLoadingResources] = useState(false);
  const resourcesLoaded = useRef(false);
  const printersLoaded = useRef(false);

  const fetchResources = useCallback(async () => {
    if (resourcesLoaded.current) return;
    setLoadingResources(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/work-centers/${workCenter.id}/resources?active_only=false`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        setResources(data);
        resourcesLoaded.current = true;
      }
    } catch {
      // Resources fetch failure is non-critical - resource list will just be empty
    } finally {
      setLoadingResources(false);
    }
  }, [workCenter.id]);

  const fetchPrinters = useCallback(async () => {
    if (printersLoaded.current) return;
    try {
      const res = await fetch(
        `${API_URL}/api/v1/work-centers/${workCenter.id}/printers?active_only=false`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        setPrinters(data);
        printersLoaded.current = true;
      }
    } catch {
      // Printers fetch failure is non-critical
    }
  }, [workCenter.id]);

  useEffect(() => {
    if (expanded) {
      fetchResources();
      if (workCenter.center_type === "machine") {
        fetchPrinters();
      }
    }
  }, [expanded, fetchResources, fetchPrinters, workCenter.center_type]);

  const [addingAll, setAddingAll] = useState(false);

  const handleAddAllPrinters = async (printersToAdd) => {
    setAddingAll(true);
    let successCount = 0;

    for (const printer of printersToAdd) {
      try {
        // Map printer status to resource status
        let resourceStatus = "offline";
        if (printer.status === "idle") {
          resourceStatus = "available";
        } else if (printer.status === "printing") {
          resourceStatus = "busy";
        } else if (printer.status === "error") {
          resourceStatus = "offline";
        } else if (
          ["available", "busy", "maintenance", "offline"].includes(
            printer.status
          )
        ) {
          resourceStatus = printer.status;
        }

        const resourceData = {
          code: printer.code || "",
          name: printer.name || "",
          machine_type: printer.model || "",
          serial_number: printer.serial_number || "",
          bambu_device_id: printer.device_id || "",
          bambu_ip_address: printer.ip_address || "",
          status: resourceStatus,
          is_active: printer.is_active ?? true,
          printer_id: printer.id,
        };

        const res = await fetch(
          `${API_URL}/api/v1/work-centers/${workCenter.id}/resources`,
          {
            method: "POST",
            credentials: "include",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify(resourceData),
          }
        );

        if (res.ok) {
          successCount++;
        }
      } catch {
        // Continue with next printer
      }
    }

    // Refresh resources list
    resourcesLoaded.current = false;
    setResources([]);
    await fetchResources();
    setAddingAll(false);

    // Notify user of results
    if (successCount === printersToAdd.length) {
      toast.success(
        `Successfully added all ${successCount} printer${
          successCount !== 1 ? "s" : ""
        } as resources`
      );
    } else if (successCount > 0) {
      toast.warning(
        `Added ${successCount} of ${printersToAdd.length} printers as resources`
      );
    } else {
      toast.error("Failed to add printers as resources");
    }
  };

  const typeColor = getTypeColor(workCenter.center_type);
  const typeBadgeClass = TYPE_BADGE_CLASS[typeColor] ?? TYPE_BADGE_CLASS.gray;

  return (
    <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
      {/* Header */}
      <div className="p-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-gray-400 hover:text-white"
          >
            {expanded ? "▼" : "▶"}
          </button>

          <div>
            <div className="flex items-center gap-3">
              <span className="font-mono text-blue-400 font-medium">
                {workCenter.code}
              </span>
              <span className="text-white font-medium">{workCenter.name}</span>
              <span
                className={`px-2 py-0.5 rounded text-xs ${typeBadgeClass}`}
              >
                {workCenter.center_type}
              </span>
              {!workCenter.is_active && (
                <span className="px-2 py-0.5 rounded text-xs bg-gray-700 text-gray-400">
                  Inactive
                </span>
              )}
              {workCenter.is_bottleneck && (
                <span className="px-2 py-0.5 rounded text-xs bg-red-900/30 text-red-400">
                  Bottleneck
                </span>
              )}
            </div>
            <div className="text-sm text-gray-400 mt-1 flex gap-4">
              <span>
                Capacity: {workCenter.capacity_hours_per_day || "-"} hrs/day
              </span>
              <span>
                Rate: $
                {parseFloat(workCenter.total_rate_per_hour || 0).toFixed(2)}/hr
              </span>
              <span>Resources: {workCenter.resource_count || 0}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onEdit}
            className="text-blue-400 hover:text-blue-300 text-sm px-3 py-1"
          >
            Edit
          </button>
          <button
            onClick={onDelete}
            className="text-red-400 hover:text-red-300 text-sm px-3 py-1"
          >
            Delete
          </button>
        </div>
      </div>

      {/* Expanded: Resources */}
      {expanded && (
        <div className="border-t border-gray-800 p-4 bg-gray-950">
          <div className="flex justify-between items-center mb-3">
            <h4 className="text-sm font-medium text-gray-400">
              Resources / Machines
            </h4>
            <button
              onClick={onAddResource}
              className="text-sm text-blue-400 hover:text-blue-300"
            >
              + Add Resource
            </button>
          </div>

          {loadingResources ? (
            <div className="text-gray-500 text-sm">Loading...</div>
          ) : resources.length === 0 ? (
            <div className="text-gray-500 text-sm">
              No resources defined. Add individual machines or stations.
            </div>
          ) : (
            <div className="grid gap-2">
              {resources.map((r) => (
                <div
                  key={r.id}
                  className="flex items-center justify-between p-3 bg-gray-900 rounded border border-gray-800"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`w-2 h-2 rounded-full ${STATUS_DOT_CLASS[getStatusColor(r.status)] ?? STATUS_DOT_CLASS.gray}`}
                    />
                    <span className="font-mono text-sm text-gray-300">
                      {r.code}
                    </span>
                    <span className="text-white">{r.name}</span>
                    {r.machine_type && (
                      <span className="text-xs text-gray-500">
                        ({r.machine_type})
                      </span>
                    )}
                    {r.bambu_device_id && (
                      <span className="text-xs text-purple-400">
                        Bambu Connected
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`px-2 py-0.5 rounded text-xs ${STATUS_BADGE_CLASS[getStatusColor(r.status)] ?? STATUS_BADGE_CLASS.gray}`}
                    >
                      {r.status}
                    </span>
                    <button
                      onClick={() => onEditResource(r)}
                      className="text-blue-400 hover:text-blue-300 text-xs"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => onDeleteResource(r)}
                      className="text-red-400 hover:text-red-300 text-xs"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Printers Section - only for machine type work centers */}
          {workCenter.center_type === "machine" &&
            (() => {
              // Filter out printers that are already added as resources (by code)
              const resourceCodes = resources.map((r) => r.code);
              const unaddedPrinters = printers.filter(
                (p) => !resourceCodes.includes(p.code)
              );

              return (
                <div className="mt-4 pt-4 border-t border-gray-800">
                  <div className="flex justify-between items-center mb-3">
                    <h4 className="text-sm font-medium text-gray-400">
                      🖨️ Available Printers
                      {unaddedPrinters.length > 0 && (
                        <span className="ml-2 text-xs text-yellow-500">
                          ({unaddedPrinters.length} not added)
                        </span>
                      )}
                    </h4>
                    <div className="flex items-center gap-3">
                      {unaddedPrinters.length > 0 && (
                        <button
                          onClick={() => handleAddAllPrinters(unaddedPrinters)}
                          disabled={addingAll}
                          className="text-sm px-3 py-1 bg-green-600 hover:bg-green-700 disabled:bg-green-800 disabled:cursor-wait text-white rounded"
                        >
                          {addingAll
                            ? "Adding..."
                            : `Add All (${unaddedPrinters.length})`}
                        </button>
                      )}
                      <a
                        href="/admin/printers"
                        className="text-sm text-blue-400 hover:text-blue-300"
                      >
                        Manage Printers →
                      </a>
                    </div>
                  </div>

                  {printers.length === 0 ? (
                    <div className="text-gray-500 text-sm">
                      No printers assigned to this pool. Assign printers from
                      the Printers page.
                    </div>
                  ) : unaddedPrinters.length === 0 ? (
                    <div className="text-green-500 text-sm">
                      ✓ All assigned printers have been added as resources.
                    </div>
                  ) : (
                    <div className="grid gap-2">
                      {unaddedPrinters.map((p) => (
                        <div
                          key={p.id}
                          className="flex items-center justify-between p-3 bg-gray-900 rounded border border-gray-800"
                        >
                          <div className="flex items-center gap-3">
                            <span
                              className={`w-2 h-2 rounded-full ${
                                p.status === "idle"
                                  ? "bg-green-500"
                                  : p.status === "printing"
                                  ? "bg-blue-500"
                                  : p.status === "error"
                                  ? "bg-red-500"
                                  : "bg-gray-500"
                              }`}
                            />
                            <span className="font-mono text-sm text-gray-300">
                              {p.code}
                            </span>
                            <span className="text-white">{p.name}</span>
                            <span className="text-xs text-gray-500">
                              ({p.model})
                            </span>
                            {p.ip_address && (
                              <span className="text-xs text-purple-400">
                                {p.ip_address}
                              </span>
                            )}
                          </div>
                          <span
                            className={`px-2 py-0.5 rounded text-xs ${
                              p.status === "idle"
                                ? "bg-green-900/30 text-green-400"
                                : p.status === "printing"
                                ? "bg-blue-900/30 text-blue-400"
                                : p.status === "error"
                                ? "bg-red-900/30 text-red-400"
                                : "bg-gray-700 text-gray-400"
                            }`}
                          >
                            {p.status || "offline"}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })()}
        </div>
      )}
    </div>
  );
}
