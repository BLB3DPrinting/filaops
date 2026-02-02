/**
 * MaterialRequirementsSection - Material requirements table with shortage indicators.
 *
 * Extracted from OrderDetail.jsx (ARCHITECT-002)
 */

export default function MaterialRequirementsSection({
  materialRequirements,
  materialAvailability,
  expandedSections,
  onToggle,
  exploding,
  order,
  onCreateWorkOrder,
  onCreatePurchaseOrder,
}) {
  const totalMaterialCost = materialRequirements.reduce(
    (sum, req) => sum + req.gross_quantity * (req.unit_cost || 0),
    0
  );
  const hasShortages = materialRequirements.some((req) => req.net_shortage > 0);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <div className="flex justify-between items-center mb-4">
        <button
          onClick={() => onToggle("materialRequirements")}
          className="flex items-center gap-2 text-lg font-semibold text-white hover:text-gray-300"
        >
          <svg
            className={`w-5 h-5 transition-transform ${expandedSections.materialRequirements ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          Material Requirements
          {hasShortages && (
            <span className="px-2 py-0.5 bg-red-500/20 text-red-400 text-xs rounded-full">
              {materialRequirements.filter((r) => r.net_shortage > 0).length} Shortage{materialRequirements.filter((r) => r.net_shortage > 0).length !== 1 ? "s" : ""}
            </span>
          )}
        </button>
        {exploding && (
          <span className="text-gray-400 text-sm">Calculating...</span>
        )}
      </div>
      {expandedSections.materialRequirements && (
        <>
          {materialRequirements.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              {order.product_id || (order.lines && order.lines.length > 0)
                ? "No BOM found for this product. Add a BOM to see material requirements."
                : "No product assigned to this order"}
            </div>
          ) : (
            <>
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-700">
                    <th className="text-left p-2 text-gray-400">Component</th>
                    <th className="text-left p-2 text-gray-400">Operation</th>
                    <th className="text-right p-2 text-gray-400">Required</th>
                    <th className="text-right p-2 text-gray-400">Available</th>
                    <th className="text-right p-2 text-gray-400">Shortage</th>
                    <th className="text-center p-2 text-gray-400">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {materialRequirements.map((req, idx) => (
                    <tr
                      key={idx}
                      className={`border-b border-gray-800 ${
                        req.net_shortage > 0 ? "bg-red-900/20" : ""
                      }`}
                    >
                      <td className="p-2">
                        <div className="text-white">{req.product_sku} - {req.product_name}</div>
                        {req.material_source === "routing" && (
                          <span className="text-xs text-blue-400">via routing</span>
                        )}
                        {req.has_incoming_supply && (
                          <span className="text-xs text-amber-400 ml-2" title={req.incoming_supply_details?.expected_date ? `Expected: ${req.incoming_supply_details.expected_date}` : ""}>
                            PO pending
                          </span>
                        )}
                      </td>
                      <td className="p-2 text-left">
                        {req.operation_code ? (
                          <span className="px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded-full">
                            {req.operation_code}
                          </span>
                        ) : (
                          <span className="text-gray-500 text-xs">-</span>
                        )}
                      </td>
                      <td className="p-2 text-right text-white">
                        {req.gross_quantity?.toFixed(2) || "0.00"}
                      </td>
                      <td className="p-2 text-right text-gray-300">
                        {req.available_quantity?.toFixed(2) || "0.00"}
                      </td>
                      <td className="p-2 text-right">
                        <span
                          className={
                            req.net_shortage > 0
                              ? "text-red-400 font-semibold"
                              : "text-green-400"
                          }
                        >
                          {req.net_shortage?.toFixed(2) || "0.00"}
                        </span>
                      </td>
                      <td className="p-2 text-center">
                        {req.net_shortage > 0 &&
                          (req.has_bom ? (
                            <button
                              onClick={() => onCreateWorkOrder(req)}
                              className="text-purple-400 hover:text-purple-300 text-sm"
                            >
                              Create WO
                            </button>
                          ) : (
                            <button
                              onClick={() => onCreatePurchaseOrder(req)}
                              className="text-blue-400 hover:text-blue-300 text-sm"
                            >
                              Create PO
                            </button>
                          ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-gray-800 font-semibold">
                    <td colSpan="4" className="p-2 text-right text-white">
                      {materialAvailability?.has_shortages ? (
                        <span className="text-red-400">
                          {materialAvailability.materials_short} of {materialAvailability.total_materials} materials short
                        </span>
                      ) : (
                        <span className="text-green-400">All materials available</span>
                      )}
                    </td>
                    <td className="p-2 text-right text-white">
                      Est: ${totalMaterialCost.toFixed(2)}
                    </td>
                    <td className="p-2"></td>
                  </tr>
                </tfoot>
              </table>

              {hasShortages && (
                <div className="mt-4 p-3 bg-red-900/20 border border-red-500/30 rounded-lg">
                  <p className="text-red-400 text-sm">
                    Material shortages detected. Create{" "}
                    <span className="text-purple-400">Work Orders</span> for
                    sub-assemblies or{" "}
                    <span className="text-blue-400">Purchase Orders</span> for raw
                    materials.
                  </p>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
