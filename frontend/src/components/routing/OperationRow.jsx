import React from "react";

/**
 * OperationRow - A single operation row in the routing operations table.
 *
 * Renders the operation details (sequence, name, work center, times, cost)
 * plus an expandable materials sub-row.
 *
 * Props:
 * - op: object - The operation data
 * - index: number - The index of this operation in the operations array
 * - materials: array - Materials assigned to this operation
 * - isExpanded: boolean - Whether the materials sub-row is visible
 * - loading: boolean - Whether a save/delete is in progress
 * - onToggleExpand: (operationId) => void
 * - onUpdateOperation: (index, field, value) => void
 * - onRemoveOperation: (index) => void
 * - onAddMaterial: (operationId) => void
 * - onEditMaterial: (operationId, material) => void
 * - operations: array - Full operations list (used for sequence reordering)
 */
export default function OperationRow({
  op,
  index,
  materials,
  isExpanded,
  loading,
  onToggleExpand,
  onUpdateOperation,
  onRemoveOperation,
  onAddMaterial,
  onEditMaterial,
  operations,
}) {
  return (
    <React.Fragment>
      <tr className="border-b border-gray-800 hover:bg-gray-800/50">
        <td className="border border-gray-700 p-2">
          <div className="flex items-center gap-2">
            {op.id && (
              <button
                onClick={() => onToggleExpand(op.id)}
                className="text-gray-400 hover:text-white"
                title={isExpanded ? "Collapse materials" : "Expand materials"}
              >
                <svg
                  className={`w-4 h-4 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
              </button>
            )}
            <input
              type="number"
              min="1"
              step="1"
              value={op.sequence || index + 1}
              onChange={(e) => {
                const newSequence = parseInt(e.target.value) || 1;
                onUpdateOperation(index, "sequence", newSequence);
                const currentSeq = op.sequence || index + 1;
                if (newSequence !== currentSeq) {
                  operations.forEach((otherOp, otherIdx) => {
                    if (otherIdx !== index) {
                      const otherSeq = otherOp.sequence || otherIdx + 1;
                      if (otherSeq >= newSequence && otherSeq < currentSeq) {
                        onUpdateOperation(otherIdx, "sequence", otherSeq + 1);
                      } else if (otherSeq <= newSequence && otherSeq > currentSeq) {
                        onUpdateOperation(otherIdx, "sequence", otherSeq - 1);
                      }
                    }
                  });
                }
              }}
              className="w-12 text-center bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white"
            />
          </div>
        </td>
        <td className="border border-gray-700 p-2">
          <div>
            <div className="font-medium text-white">
              {op.operation_name || op.operation_code || `OP${index + 1}`}
            </div>
            {op.operation_code && (
              <div className="text-sm text-gray-400">{op.operation_code}</div>
            )}
            {materials.length > 0 && (
              <div className="text-xs text-blue-400 mt-1">
                {materials.length} material{materials.length !== 1 ? 's' : ''}
              </div>
            )}
          </div>
        </td>
        <td className="border border-gray-700 p-2 text-white">
          {op.work_center_name || op.work_center?.name}
        </td>
        <td className="border border-gray-700 p-2">
          <input
            type="number"
            step="0.1"
            min="0"
            value={op.setup_time_minutes || 0}
            onChange={(e) =>
              onUpdateOperation(index, "setup_time_minutes", parseFloat(e.target.value) || 0)
            }
            className="w-20 text-right bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white"
          />
        </td>
        <td className="border border-gray-700 p-2">
          <input
            type="number"
            step="0.1"
            min="0"
            value={op.run_time_minutes || 0}
            onChange={(e) =>
              onUpdateOperation(index, "run_time_minutes", parseFloat(e.target.value) || 0)
            }
            className="w-20 text-right bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white"
          />
        </td>
        <td className="border border-gray-700 p-2 text-right text-green-400">
          ${op.calculated_cost != null
            ? parseFloat(op.calculated_cost).toFixed(2)
            : (
                (((parseFloat(op.setup_time_minutes) || 0) +
                  (parseFloat(op.run_time_minutes) || 0)) / 60) *
                (parseFloat(op.hourly_rate) || 0)
              ).toFixed(2)}
        </td>
        <td className="border border-gray-700 p-2 text-center">
          <div className="flex items-center justify-center gap-2">
            {op.id && (
              <button
                onClick={() => onAddMaterial(op.id)}
                className="text-blue-400 hover:text-blue-300 text-sm"
                title="Add material"
              >
                +Mat
              </button>
            )}
            <button
              onClick={() => onRemoveOperation(index)}
              className="text-red-400 hover:text-red-300"
              disabled={loading}
            >
              Remove
            </button>
          </div>
        </td>
      </tr>
      {/* Expandable Materials Row */}
      {isExpanded && (
        <tr className="bg-gray-800/30">
          <td colSpan="7" className="border border-gray-700 p-3">
            <div className="ml-6">
              <div className="flex items-center justify-between mb-2">
                <h5 className="text-sm font-medium text-gray-300">Materials</h5>
                <button
                  onClick={() => onAddMaterial(op.id)}
                  className="text-xs px-2 py-1 bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded hover:bg-blue-600/30"
                >
                  + Add Material
                </button>
              </div>
              {materials.length === 0 ? (
                <p className="text-sm text-gray-500 italic">No materials assigned to this operation</p>
              ) : (
                <div className="space-y-1">
                  {materials.map((mat) => (
                    <div
                      key={mat.id}
                      className="flex items-center justify-between text-sm p-2 bg-gray-800/50 rounded cursor-pointer hover:bg-gray-800"
                      onClick={() => onEditMaterial(op.id, mat)}
                    >
                      <div className="flex items-center gap-3">
                        <span className="text-gray-300">{mat.component_sku}</span>
                        <span className="text-gray-500">-</span>
                        <span className="text-gray-400">{mat.component_name}</span>
                      </div>
                      <div className="flex items-center gap-4 text-gray-400">
                        <span>{mat.quantity} {mat.unit}</span>
                        <span className="text-xs text-gray-500">
                          /{mat.quantity_per}
                        </span>
                        {parseFloat(mat.extended_cost || 0) > 0 && (
                          <span className="text-green-400">
                            ${parseFloat(mat.extended_cost).toFixed(4)}
                          </span>
                        )}
                        {mat.is_optional && (
                          <span className="text-xs px-1.5 py-0.5 bg-yellow-500/20 text-yellow-400 rounded">optional</span>
                        )}
                        {mat.is_variable && (
                          <span className="px-1.5 py-0.5 rounded text-xs bg-blue-500/20 text-blue-400 border border-blue-500/30">
                            Variable
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </React.Fragment>
  );
}
