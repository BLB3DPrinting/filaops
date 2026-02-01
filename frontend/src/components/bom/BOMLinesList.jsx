/**
 * BOMLinesList - Displays BOM component lines with inline editing.
 * Shows component name, quantity, unit cost, line cost, and edit/delete actions.
 */
export default function BOMLinesList({
  lines,
  editingLine,
  setEditingLine,
  uoms,
  onUpdateLine,
  onDeleteLine,
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-800">
          <tr>
            <th className="text-left py-2 px-3 text-gray-400">#</th>
            <th className="text-left py-2 px-3 text-gray-400">Component</th>
            <th className="text-left py-2 px-3 text-gray-400">Qty Needed</th>
            <th className="text-left py-2 px-3 text-gray-400">Unit Cost</th>
            <th className="text-left py-2 px-3 text-gray-400">Line Cost</th>
            <th className="text-right py-2 px-3 text-gray-400">Actions</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => (
            <tr key={line.id} className="border-b border-gray-800">
              <td className="py-2 px-3 text-gray-500">{line.sequence}</td>
              <td className="py-2 px-3">
                <div className="flex items-center gap-2">
                  <div>
                    <div className="text-white font-medium flex items-center gap-1.5">
                      {line.component_name || `Product #${line.component_id}`}
                      {line.has_bom && (
                        <span
                          className="inline-flex items-center gap-0.5 px-1.5 py-0.5 bg-purple-500/20 text-purple-400 rounded text-xs"
                          title="Sub-assembly - has its own BOM"
                        >
                          <svg
                            className="w-3 h-3"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"
                            />
                          </svg>
                          Sub
                        </span>
                      )}
                    </div>
                    <div className="text-gray-500 text-xs">
                      {line.component_sku}
                    </div>
                  </div>
                </div>
              </td>
              <td className="py-2 px-3 text-gray-300">
                {editingLine === line.id ? (
                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      defaultValue={line.quantity}
                      step="0.01"
                      className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white"
                      onBlur={(e) => {
                        const nextQty = Number(e.target.value);
                        if (!Number.isFinite(nextQty) || nextQty <= 0) {
                          e.target.value = line.quantity ?? "";
                          return;
                        }
                        onUpdateLine(line.id, { quantity: nextQty });
                      }}
                    />
                    <select
                      defaultValue={line.unit || ""}
                      className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-sm"
                      onChange={(e) =>
                        onUpdateLine(line.id, {
                          unit: e.target.value || null,
                        })
                      }
                    >
                      <option value="">Default</option>
                      {uoms.map((u) => (
                        <option key={u.code} value={u.code}>
                          {u.code}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <span>
                    {parseFloat(line.quantity || 0).toFixed(2)}{" "}
                    {line.unit || line.component_unit || "EA"}
                  </span>
                )}
              </td>
              <td className="py-2 px-3 text-gray-400">
                ${parseFloat(line.component_cost || 0).toFixed(2)}/
                {(() => {
                  const isMaterial =
                    line.is_material ||
                    line.component_cost_unit === "KG" ||
                    (line.component_unit === "G" &&
                      line.component_cost &&
                      parseFloat(line.component_cost) > 0.01);

                  if (isMaterial) {
                    return "KG";
                  }
                  return line.unit || line.component_unit || "EA";
                })()}
              </td>
              <td className="py-2 px-3 text-green-400 font-medium">
                ${parseFloat(line.line_cost || 0).toFixed(2)}
              </td>
              <td className="py-2 px-3 text-right">
                <button
                  type="button"
                  onClick={() =>
                    setEditingLine(editingLine === line.id ? null : line.id)
                  }
                  className="text-blue-400 hover:text-blue-300 px-2"
                >
                  {editingLine === line.id ? "Done" : "Edit"}
                </button>
                <button
                  type="button"
                  onClick={() => onDeleteLine(line.id)}
                  className="text-red-400 hover:text-red-300 px-2"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
          {lines.length === 0 && (
            <tr>
              <td colSpan={6} className="py-8 text-center text-gray-500">
                No components added yet
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
