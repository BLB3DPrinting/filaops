import { Fragment } from "react";
import { API_URL } from "../../config/api";

export default function BOMRoutingSection({
  showProcessPath,
  productRouting,
  operationMaterials,
  expandedOperations,
  setExpandedOperations,
  timeOverrides,
  showAddOperation,
  setShowAddOperation,
  showAddOperationToExisting,
  setShowAddOperationToExisting,
  pendingOperations,
  newOperation,
  setNewOperation,
  workCenters,
  routingTemplates,
  selectedTemplateId,
  setSelectedTemplateId,
  applyingTemplate,
  savingRouting,
  addingOperation,
  setShowAddMaterialModal,
  handleAddPendingOperation,
  handleRemovePendingOperation,
  handleSaveRouting,
  handleApplyTemplate,
  updateOperationTime,
  saveOperationTime,
  handleDeleteOperation,
  handleDeleteMaterial,
  handleAddOperationToExisting,
  formatTime,
  fetchProductRouting,
  toast,
}) {
  return (
    <>
      {/* Process Path / Routing Section */}
      {showProcessPath && (
        <div className="bg-gradient-to-r from-amber-600/10 to-orange-600/10 border border-amber-500/30 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <svg
                className="w-5 h-5 text-amber-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"
                />
              </svg>
              <span className="text-amber-300 font-medium">Process Path</span>
            </div>
            {productRouting && (
              <span className="text-xs bg-amber-500/20 text-amber-300 px-2 py-1 rounded-full">
                {productRouting.operations?.length || 0} Operations
              </span>
            )}
          </div>

          {/* No routing yet - allow creating operations */}
          {!productRouting && (
            <div className="space-y-3">
              {/* Pending operations list */}
              {pendingOperations.length > 0 && (
                <div className="space-y-2">
                  <div className="text-sm text-gray-400">
                    Operations to create:
                  </div>
                  {pendingOperations.map((op, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between bg-gray-800 rounded-lg px-3 py-2"
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-gray-500 font-mono text-sm w-6">
                          {op.sequence}
                        </span>
                        <span className="text-white">
                          {op.operation_name || op.work_center_name}
                        </span>
                        <span className="text-gray-500 text-sm">
                          @ {op.work_center_code}
                        </span>
                        <span className="text-amber-400 text-sm">
                          {op.run_time_minutes}m
                        </span>
                      </div>
                      <button
                        onClick={() => handleRemovePendingOperation(idx)}
                        className="text-red-400 hover:text-red-300 text-sm px-2"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}

              {/* Add operation form */}
              {showAddOperation ? (
                <div className="bg-gray-800 rounded-lg p-3 space-y-3">
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">
                        Work Center *
                      </label>
                      <select
                        value={newOperation.work_center_id}
                        onChange={(e) =>
                          setNewOperation({
                            ...newOperation,
                            work_center_id: e.target.value,
                          })
                        }
                        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                      >
                        <option value="">Select work center...</option>
                        {workCenters.map((wc) => (
                          <option key={wc.id} value={wc.id}>
                            {wc.code} - {wc.name}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">
                        Operation Name
                      </label>
                      <input
                        type="text"
                        value={newOperation.operation_name}
                        onChange={(e) =>
                          setNewOperation({
                            ...newOperation,
                            operation_name: e.target.value,
                          })
                        }
                        placeholder="e.g., Print Part"
                        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">
                        Run Time (min)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        value={newOperation.run_time_minutes}
                        onChange={(e) =>
                          setNewOperation({
                            ...newOperation,
                            run_time_minutes: e.target.value,
                          })
                        }
                        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-400 mb-1">
                        Setup Time (min)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        value={newOperation.setup_time_minutes}
                        onChange={(e) =>
                          setNewOperation({
                            ...newOperation,
                            setup_time_minutes: e.target.value,
                          })
                        }
                        className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                      />
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={handleAddPendingOperation}
                      disabled={!newOperation.work_center_id}
                      className="px-3 py-1.5 bg-amber-600 text-white rounded text-sm hover:bg-amber-700 disabled:opacity-50"
                    >
                      Add Operation
                    </button>
                    <button
                      onClick={() => setShowAddOperation(false)}
                      className="px-3 py-1.5 bg-gray-700 text-white rounded text-sm hover:bg-gray-600"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2">
                  <button
                    onClick={() => setShowAddOperation(true)}
                    className="px-3 py-1.5 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 flex items-center gap-1"
                  >
                    <span>+</span> Add Operation
                  </button>
                  {pendingOperations.length > 0 && (
                    <button
                      onClick={handleSaveRouting}
                      disabled={savingRouting}
                      className="px-3 py-1.5 bg-green-600 text-white rounded-lg text-sm hover:bg-green-700 disabled:opacity-50"
                    >
                      {savingRouting ? "Saving..." : "Save Routing"}
                    </button>
                  )}
                </div>
              )}

              {/* Template option - show only if templates exist and no pending ops */}
              {routingTemplates.length > 0 &&
                pendingOperations.length === 0 &&
                !showAddOperation && (
                  <div className="pt-2 border-t border-gray-700">
                    <p className="text-xs text-gray-500 mb-2">
                      Or apply a template:
                    </p>
                    <div className="flex gap-2">
                      <select
                        value={selectedTemplateId}
                        onChange={(e) => setSelectedTemplateId(e.target.value)}
                        className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-sm"
                      >
                        <option value="">Select template...</option>
                        {routingTemplates.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.code} - {t.name || "Unnamed"}
                          </option>
                        ))}
                      </select>
                      <button
                        onClick={handleApplyTemplate}
                        disabled={!selectedTemplateId || applyingTemplate}
                        className="px-3 py-1.5 bg-gray-700 text-white rounded-lg text-sm hover:bg-gray-600 disabled:opacity-50"
                      >
                        {applyingTemplate ? "..." : "Apply"}
                      </button>
                    </div>
                  </div>
                )}
            </div>
          )}

          {/* Existing routing - show operations */}
          {productRouting && (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-sm">
                <span className="text-gray-400">
                  Routing:{" "}
                  <span className="text-white">
                    {productRouting.code || productRouting.routing_code}
                  </span>
                </span>
                <span className="text-gray-400">
                  Total Time:{" "}
                  <span className="text-amber-400 font-medium">
                    {formatTime(productRouting.total_run_time_minutes)}
                  </span>
                </span>
              </div>

              {/* Operations table */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-800/50">
                    <tr>
                      <th className="text-left py-2 px-3 text-gray-400">#</th>
                      <th className="text-left py-2 px-3 text-gray-400">
                        Operation
                      </th>
                      <th className="text-left py-2 px-3 text-gray-400">
                        Work Center
                      </th>
                      <th className="text-left py-2 px-3 text-gray-400">
                        Run Time
                      </th>
                      <th className="text-left py-2 px-3 text-gray-400">
                        Setup
                      </th>
                      <th className="text-left py-2 px-3 text-gray-400">
                        Cost
                      </th>
                      <th className="text-center py-2 px-3 text-gray-400">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {(productRouting.operations || []).map((op, idx) => (
                      <Fragment key={op.id || idx}>
                        {/* Main operation row */}
                        <tr className="border-b border-gray-800">
                          <td className="py-2 px-3">
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() =>
                                  setExpandedOperations((prev) => ({
                                    ...prev,
                                    [op.id]: !prev[op.id],
                                  }))
                                }
                                className="text-gray-400 hover:text-white p-1 rounded hover:bg-gray-700 transition-colors"
                                title="Show materials"
                              >
                                <svg
                                  className={`w-4 h-4 transition-transform ${
                                    expandedOperations[op.id] ? "rotate-90" : ""
                                  }`}
                                  fill="none"
                                  stroke="currentColor"
                                  viewBox="0 0 24 24"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    strokeWidth={2}
                                    d="M9 5l7 7-7 7"
                                  />
                                </svg>
                              </button>
                              <input
                                type="number"
                                min="1"
                                step="1"
                                defaultValue={op.sequence}
                                onBlur={async (e) => {
                                  const newSequence =
                                    parseInt(e.target.value) || 1;
                                  if (newSequence === op.sequence) return;
                                  try {
                                    const res = await fetch(
                                      `${API_URL}/api/v1/routings/operations/${op.id}`,
                                      {
                                        method: "PUT",
                                        headers: { "Content-Type": "application/json" },
                                        credentials: "include",
                                        body: JSON.stringify({
                                          sequence: newSequence,
                                        }),
                                      }
                                    );
                                    if (res.ok) {
                                      await fetchProductRouting();
                                    } else {
                                      toast.error("Failed to update sequence");
                                    }
                                  } catch (err) {
                                    toast.error(`Error: ${err.message}`);
                                  }
                                }}
                                className="w-12 text-center bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white"
                              />
                            </div>
                          </td>
                          <td className="py-2 px-3">
                            <div className="text-white font-medium">
                              {op.operation_name || op.operation_code}
                            </div>
                            {op.operation_code && op.operation_name && (
                              <div className="text-gray-500 text-xs">
                                {op.operation_code}
                              </div>
                            )}
                          </td>
                          <td className="py-2 px-3 text-gray-400">
                            {op.work_center_name || op.work_center_code}
                          </td>
                          <td className="py-2 px-3">
                            <input
                              type="number"
                              step="0.1"
                              value={
                                timeOverrides[op.operation_code]
                                  ?.run_time_minutes ??
                                parseFloat(op.run_time_minutes || 0)
                              }
                              onChange={(e) =>
                                updateOperationTime(
                                  op.operation_code,
                                  "run_time_minutes",
                                  e.target.value
                                )
                              }
                              onBlur={(e) =>
                                saveOperationTime(
                                  op.id,
                                  "run_time_minutes",
                                  e.target.value
                                )
                              }
                              className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
                            />
                            <span className="text-gray-500 text-xs ml-1">
                              min
                            </span>
                          </td>
                          <td className="py-2 px-3">
                            <input
                              type="number"
                              step="0.1"
                              value={
                                timeOverrides[op.operation_code]
                                  ?.setup_time_minutes ??
                                parseFloat(op.setup_time_minutes || 0)
                              }
                              onChange={(e) =>
                                updateOperationTime(
                                  op.operation_code,
                                  "setup_time_minutes",
                                  e.target.value
                                )
                              }
                              onBlur={(e) =>
                                saveOperationTime(
                                  op.id,
                                  "setup_time_minutes",
                                  e.target.value
                                )
                              }
                              className="w-16 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
                            />
                            <span className="text-gray-500 text-xs ml-1">
                              min
                            </span>
                          </td>
                          <td className="py-2 px-3 text-green-400">
                            ${parseFloat(op.calculated_cost || 0).toFixed(2)}
                          </td>
                          <td className="py-2 px-3 text-center">
                            <button
                              onClick={() =>
                                handleDeleteOperation(
                                  op.id,
                                  op.operation_name || op.operation_code
                                )
                              }
                              className="text-red-400 hover:text-red-300 text-sm px-2 py-1 rounded hover:bg-red-400/10 transition-colors"
                              title="Remove operation"
                            >
                              Remove
                            </button>
                          </td>
                        </tr>

                        {/* Expanded materials section */}
                        {expandedOperations[op.id] && (
                          <tr className="bg-gray-800/30">
                            <td colSpan={7} className="py-3 px-6">
                              <div className="ml-6 border-l-2 border-blue-500/30 pl-4">
                                <div className="flex items-center justify-between mb-2">
                                  <span className="text-sm text-blue-400 font-medium flex items-center gap-2">
                                    <svg
                                      className="w-4 h-4"
                                      fill="none"
                                      stroke="currentColor"
                                      viewBox="0 0 24 24"
                                    >
                                      <path
                                        strokeLinecap="round"
                                        strokeLinejoin="round"
                                        strokeWidth={2}
                                        d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                                      />
                                    </svg>
                                    Materials Consumed at this Operation
                                  </span>
                                  <button
                                    onClick={() =>
                                      setShowAddMaterialModal(op.id)
                                    }
                                    className="px-2 py-1 bg-blue-600 text-white rounded text-xs hover:bg-blue-700 flex items-center gap-1"
                                  >
                                    <span>+</span> Add Material
                                  </button>
                                </div>

                                {/* Materials list */}
                                {operationMaterials[op.id] &&
                                operationMaterials[op.id].length > 0 ? (
                                  <table className="w-full text-xs">
                                    <thead className="bg-gray-900/50">
                                      <tr>
                                        <th className="text-left py-1.5 px-2 text-gray-500">
                                          Component
                                        </th>
                                        <th className="text-left py-1.5 px-2 text-gray-500">
                                          Qty/Unit
                                        </th>
                                        <th className="text-left py-1.5 px-2 text-gray-500">
                                          Scrap %
                                        </th>
                                        <th className="text-left py-1.5 px-2 text-gray-500">
                                          Unit Cost
                                        </th>
                                        <th className="text-left py-1.5 px-2 text-gray-500">
                                          Ext. Cost
                                        </th>
                                        <th className="text-right py-1.5 px-2 text-gray-500">
                                          Actions
                                        </th>
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {operationMaterials[op.id].map((mat) => (
                                        <tr
                                          key={mat.id}
                                          className="border-b border-gray-700/50"
                                        >
                                          <td className="py-1.5 px-2">
                                            <div className="text-white">
                                              {mat.component_name}
                                            </div>
                                            <div className="text-gray-500 text-xs">
                                              {mat.component_sku}
                                            </div>
                                          </td>
                                          <td className="py-1.5 px-2 text-gray-300">
                                            {parseFloat(
                                              mat.quantity || 0
                                            ).toFixed(3)}{" "}
                                            {mat.unit ||
                                              mat.component_unit ||
                                              "EA"}
                                            {mat.quantity_per !== "unit" && (
                                              <span className="text-gray-500 text-xs ml-1">/{mat.quantity_per}</span>
                                            )}
                                          </td>
                                          <td className="py-1.5 px-2 text-gray-400">
                                            {parseFloat(
                                              mat.scrap_factor || 0
                                            ).toFixed(1)}
                                            %
                                          </td>
                                          <td className="py-1.5 px-2 text-gray-400">
                                            $
                                            {parseFloat(
                                              mat.unit_cost || 0
                                            ).toFixed(4)}
                                          </td>
                                          <td className="py-1.5 px-2 text-green-400">
                                            $
                                            {parseFloat(
                                              mat.extended_cost || 0
                                            ).toFixed(4)}
                                          </td>
                                          <td className="py-1.5 px-2 text-right">
                                            <button
                                              onClick={() =>
                                                handleDeleteMaterial(
                                                  op.id,
                                                  mat.id
                                                )
                                              }
                                              className="text-red-400 hover:text-red-300"
                                            >
                                              ×
                                            </button>
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                ) : (
                                  <div className="text-gray-500 text-xs py-2 italic">
                                    No materials assigned to this operation.
                                    Click "+ Add Material" to assign components.
                                  </div>
                                )}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Actions for existing routing */}
              <div className="pt-2 border-t border-gray-700 space-y-3">
                {/* Add Operation Form */}
                {showAddOperationToExisting ? (
                  <div className="bg-gray-800 rounded-lg p-3 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">
                          Work Center *
                        </label>
                        <select
                          value={newOperation.work_center_id}
                          onChange={(e) =>
                            setNewOperation({
                              ...newOperation,
                              work_center_id: e.target.value,
                            })
                          }
                          className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                        >
                          <option value="">Select work center...</option>
                          {workCenters.map((wc) => (
                            <option key={wc.id} value={wc.id}>
                              {wc.code} - {wc.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">
                          Operation Name
                        </label>
                        <input
                          type="text"
                          value={newOperation.operation_name}
                          onChange={(e) =>
                            setNewOperation({
                              ...newOperation,
                              operation_name: e.target.value,
                            })
                          }
                          placeholder="e.g., Print, QC, Pack"
                          className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                        />
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">
                          Run Time (min)
                        </label>
                        <input
                          type="number"
                          value={newOperation.run_time_minutes}
                          onChange={(e) =>
                            setNewOperation({
                              ...newOperation,
                              run_time_minutes: e.target.value,
                            })
                          }
                          className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                        />
                      </div>
                      <div>
                        <label className="block text-xs text-gray-400 mb-1">
                          Setup Time (min)
                        </label>
                        <input
                          type="number"
                          value={newOperation.setup_time_minutes}
                          onChange={(e) =>
                            setNewOperation({
                              ...newOperation,
                              setup_time_minutes: e.target.value,
                            })
                          }
                          className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white text-sm"
                        />
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={handleAddOperationToExisting}
                        disabled={!newOperation.work_center_id || addingOperation}
                        className="px-3 py-1.5 bg-green-600 text-white rounded text-sm hover:bg-green-700 disabled:opacity-50"
                      >
                        {addingOperation ? "Adding..." : "Add Operation"}
                      </button>
                      <button
                        onClick={() => setShowAddOperationToExisting(false)}
                        className="px-3 py-1.5 bg-gray-700 text-white rounded text-sm hover:bg-gray-600"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex gap-2">
                    <button
                      onClick={() => setShowAddOperationToExisting(true)}
                      className="px-3 py-1.5 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 flex items-center gap-1"
                    >
                      <span>+</span> Add Operation
                    </button>
                  </div>
                )}

                {/* Template selector */}
                <div className="flex gap-2">
                  <select
                    value={selectedTemplateId}
                    onChange={(e) => setSelectedTemplateId(e.target.value)}
                    className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-white text-sm"
                  >
                    <option value="">Change template...</option>
                    {routingTemplates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.code} - {t.name || "Unnamed"}
                      </option>
                    ))}
                  </select>
                  <button
                    onClick={handleApplyTemplate}
                    disabled={!selectedTemplateId || applyingTemplate}
                    className="px-3 py-1.5 bg-amber-600 text-white rounded-lg text-sm hover:bg-amber-700 disabled:opacity-50"
                  >
                    {applyingTemplate ? "Applying..." : "Apply"}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
