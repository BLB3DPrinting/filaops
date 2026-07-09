import { useState } from "react";
import {
  CANONICAL_OPERATION_CODE,
  categoryLabel,
  groupOperationTypes,
} from "./operationTypeDisplay";

/**
 * AddOperationForm - Form for adding a new operation to a routing.
 *
 * Props:
 * - workCenters: array - Available work centers
 * - operationTypes: array - Operation-type catalog (GET /operation-types),
 *   fetched once by RoutingEditorContent and passed down.
 * - newOperation: object - The new operation state
 * - onOperationChange: (updatedOperation) => void
 * - onAdd: () => void - Called when the Add button is clicked
 * - onCancel: () => void - Called when the Cancel button is clicked
 */
export default function AddOperationForm({
  workCenters,
  operationTypes = [],
  newOperation,
  onOperationChange,
  onAdd,
  onCancel,
}) {
  // Tracks whether the user has hand-edited the (now secondary) operation
  // code field, so picking/changing a type never clobbers a custom code —
  // same "don't clobber a manual edit" contract as
  // QualityPlanEditor's codeTouched (qualityPlanEditor.utils.js).
  const [codeTouched, setCodeTouched] = useState(
    Boolean(newOperation.operation_code)
  );
  const [showAdvanced, setShowAdvanced] = useState(false);

  function updateField(field, value) {
    onOperationChange({ ...newOperation, [field]: value });
  }

  function handleTypeChange(typeCode) {
    const canonicalCode = CANONICAL_OPERATION_CODE[typeCode] ?? "";
    onOperationChange({
      ...newOperation,
      operation_type: typeCode,
      operation_code: codeTouched ? newOperation.operation_code : canonicalCode,
    });
  }

  function handleCodeChange(value) {
    setCodeTouched(true);
    updateField("operation_code", value);
  }

  const groupedTypes = groupOperationTypes(operationTypes);
  const selectedType = operationTypes.find(
    (t) => t.code === newOperation.operation_type
  );

  return (
    <div className="mb-6 p-4 bg-gray-800 rounded-lg border border-gray-700">
      <h4 className="font-semibold mb-3 text-white">
        Add Operation
      </h4>

      <div className="mb-4">
        <label
          htmlFor="new-operation-type"
          className="block text-sm font-medium mb-1 text-gray-300"
        >
          Operation Type *
        </label>
        <select
          id="new-operation-type"
          value={newOperation.operation_type || ""}
          onChange={(e) => handleTypeChange(e.target.value)}
          className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white"
          required
        >
          <option value="">Select operation type...</option>
          {groupedTypes.map(([category, types]) => (
            <optgroup key={category} label={categoryLabel(category)}>
              {types.map((t) => (
                <option key={t.code} value={t.code}>
                  {t.label}
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        {selectedType?.description && (
          <p className="text-xs text-gray-400 mt-1">
            {selectedType.description}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label
            htmlFor="new-operation-work-center"
            className="block text-sm font-medium mb-1 text-gray-300"
          >
            Work Center
          </label>
          <select
            id="new-operation-work-center"
            value={newOperation.work_center_id}
            onChange={(e) => updateField("work_center_id", e.target.value)}
            className="w-full px-3 py-2 bg-gray-900 border border-gray-700 rounded text-white"
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
          <label htmlFor="new-operation-name" className="block text-sm font-medium mb-1">
            Operation Name
          </label>
          <input
            id="new-operation-name"
            type="text"
            value={newOperation.operation_name}
            onChange={(e) => updateField("operation_name", e.target.value)}
            className="w-full px-3 py-2 border rounded-md"
            placeholder="e.g., 3D Print, Support Removal"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">
            Setup Time (minutes)
          </label>
          <input
            type="number"
            step="0.1"
            min="0"
            value={newOperation.setup_time_minutes}
            onChange={(e) => updateField("setup_time_minutes", parseFloat(e.target.value) || 0)}
            className="w-full px-3 py-2 border rounded-md"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">
            Run Time (minutes)
          </label>
          <input
            type="number"
            step="0.1"
            min="0"
            value={newOperation.run_time_minutes}
            onChange={(e) => updateField("run_time_minutes", parseFloat(e.target.value) || 0)}
            className="w-full px-3 py-2 border rounded-md"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">
            Units per Cycle
          </label>
          <input
            type="number"
            step="1"
            min="1"
            value={newOperation.units_per_cycle}
            onChange={(e) => updateField("units_per_cycle", parseInt(e.target.value) || 1)}
            className="w-full px-3 py-2 border rounded-md"
          />
        </div>
      </div>

      <div className="mt-3">
        <button
          type="button"
          onClick={() => setShowAdvanced((v) => !v)}
          className="text-xs text-blue-400 hover:text-blue-300"
        >
          {showAdvanced ? "Hide" : "Show"} advanced: custom operation code
        </button>
        {showAdvanced && (
          <div className="mt-2">
            <label
              htmlFor="new-operation-code"
              className="block text-sm font-medium mb-1 text-gray-300"
            >
              Operation Code (optional)
            </label>
            <input
              id="new-operation-code"
              type="text"
              value={newOperation.operation_code}
              onChange={(e) => handleCodeChange(e.target.value)}
              className="w-full px-3 py-2 border rounded-md"
              placeholder="Auto-filled from the selected type; edit for a custom code"
            />
          </div>
        )}
      </div>

      <div className="mt-3 flex gap-2">
        <button
          onClick={onAdd}
          disabled={!newOperation.operation_type}
          className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:opacity-50"
        >
          Add
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2 bg-gray-300 rounded-md hover:bg-gray-400"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
