/**
 * ExplodedBOMView - Displays flattened BOM with all sub-assembly components.
 * Shows summary stats, hierarchical table with level indentation, and stock status.
 */
export default function ExplodedBOMView({ explodedData, onClose }) {
  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-lg font-semibold text-white">
            Exploded BOM View
          </h2>
          <p className="text-sm text-gray-400">
            All components flattened through sub-assemblies
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-white p-1"
          aria-label="Close"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-4 gap-4 mb-4">
        <div className="bg-gray-800 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-white">
            {explodedData.total_components}
          </div>
          <div className="text-xs text-gray-400">Total Components</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-purple-400">
            {explodedData.max_depth}
          </div>
          <div className="text-xs text-gray-400">Max Depth</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-green-400">
            ${parseFloat(explodedData.total_cost || 0).toFixed(2)}
          </div>
          <div className="text-xs text-gray-400">Total Cost</div>
        </div>
        <div className="bg-gray-800 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-blue-400">
            {explodedData.unique_components}
          </div>
          <div className="text-xs text-gray-400">Unique Parts</div>
        </div>
      </div>

      {/* Exploded Lines Table */}
      <div className="max-h-96 overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-800 sticky top-0">
            <tr>
              <th className="text-left py-2 px-3 text-gray-400">Level</th>
              <th className="text-left py-2 px-3 text-gray-400">Component</th>
              <th className="text-left py-2 px-3 text-gray-400">Qty/Unit</th>
              <th className="text-left py-2 px-3 text-gray-400">
                Extended Qty
              </th>
              <th className="text-left py-2 px-3 text-gray-400">Unit Cost</th>
              <th className="text-left py-2 px-3 text-gray-400">Line Cost</th>
              <th className="text-left py-2 px-3 text-gray-400">Stock</th>
            </tr>
          </thead>
          <tbody>
            {explodedData.lines?.map((line, idx) => (
              <tr
                key={idx}
                className={`border-b border-gray-800 ${
                  line.is_sub_assembly ? "bg-purple-500/5" : ""
                }`}
              >
                <td className="py-2 px-3">
                  <div className="flex items-center gap-1">
                    <span
                      style={{ marginLeft: `${line.level * 12}px` }}
                      className="text-gray-500"
                    >
                      {line.level === 0 ? "" : "└─"}
                    </span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-xs ${
                        line.level === 0
                          ? "bg-blue-500/20 text-blue-400"
                          : line.level === 1
                          ? "bg-green-500/20 text-green-400"
                          : line.level === 2
                          ? "bg-yellow-500/20 text-yellow-400"
                          : "bg-gray-500/20 text-gray-400"
                      }`}
                    >
                      L{line.level}
                    </span>
                  </div>
                </td>
                <td className="py-2 px-3">
                  <div className="flex items-center gap-2">
                    <div>
                      <div className="text-white font-medium flex items-center gap-1">
                        {line.component_name}
                        {line.is_sub_assembly && (
                          <span className="text-purple-400 text-xs">
                            (Sub)
                          </span>
                        )}
                      </div>
                      <div className="text-gray-500 text-xs">
                        {line.component_sku}
                      </div>
                    </div>
                  </div>
                </td>
                <td className="py-2 px-3 text-gray-400">
                  {parseFloat(line.quantity_per_unit || 0).toFixed(2)}
                </td>
                <td className="py-2 px-3 text-white font-medium">
                  {parseFloat(line.extended_quantity || 0).toFixed(2)}
                </td>
                <td className="py-2 px-3 text-gray-400">
                  ${parseFloat(line.unit_cost || 0).toFixed(2)}
                </td>
                <td className="py-2 px-3 text-green-400">
                  ${parseFloat(line.line_cost || 0).toFixed(2)}
                </td>
                <td className="py-2 px-3">
                  {line.inventory_available >= line.extended_quantity ? (
                    <span className="text-green-400 text-xs">
                      OK ({line.inventory_available?.toFixed(1)})
                    </span>
                  ) : (
                    <span className="text-red-400 text-xs">
                      Low ({line.inventory_available?.toFixed(1)})
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex justify-end pt-4 border-t border-gray-800 mt-4">
        <button
          onClick={onClose}
          className="px-4 py-2 bg-gray-700 text-white rounded-lg hover:bg-gray-600"
        >
          Close
        </button>
      </div>
    </div>
  );
}
