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
  // LEGACY-1: the backend flags terminal/short-closed orders as historical —
  // requirements are still shown for reference, but stock is not re-checked,
  // so live shortage alerts would be phantom noise.
  const isHistorical = Boolean(materialAvailability?.historical);
  const showShortageAlerts = hasShortages && !isHistorical;

  return (
    <div className="bg-[var(--paper)] border border-[var(--rule-hair)] rounded-xl p-6 shadow-[var(--shadow-pop)]">
      <div className="flex justify-between items-center mb-4">
        <button
          onClick={() => onToggle("materialRequirements")}
          className="flex items-center gap-2 text-lg font-semibold text-[var(--ink)] hover:text-[var(--ink-2)]"
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
          {showShortageAlerts && (
            <span className="px-2 py-0.5 bg-[var(--status-red-tint)] text-[var(--status-red)] text-xs rounded-full">
              {materialRequirements.filter((r) => r.net_shortage > 0).length} Shortage{materialRequirements.filter((r) => r.net_shortage > 0).length !== 1 ? "s" : ""}
            </span>
          )}
          {isHistorical && (
            <span className="px-2 py-0.5 bg-[var(--paper-sunk)] text-[var(--ink-3)] text-xs rounded-full">
              Reference only
            </span>
          )}
        </button>
        {exploding && (
          <span className="text-[var(--ink-3)] text-sm">Calculating...</span>
        )}
      </div>
      {expandedSections.materialRequirements && (
        <>
          {materialRequirements.length === 0 ? (
            <div className="text-center py-8 text-[var(--ink-4)]">
              {order.product_id || (order.lines && order.lines.length > 0)
                ? "No BOM found for this product. Add a BOM to see material requirements."
                : "No product assigned to this order"}
            </div>
          ) : (
            <>
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[var(--rule-hair)]">
                    <th className="text-left p-2 text-[var(--ink-3)]">Component</th>
                    <th className="text-left p-2 text-[var(--ink-3)]">Operation</th>
                    <th className="text-right p-2 text-[var(--ink-3)]">Required</th>
                    <th className="text-right p-2 text-[var(--ink-3)]">Available</th>
                    <th className="text-right p-2 text-[var(--ink-3)]">Shortage</th>
                    <th className="text-center p-2 text-[var(--ink-3)]">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {materialRequirements.map((req, idx) => (
                    <tr
                      key={idx}
                      className={`border-b border-[var(--rule-hair)] ${
                        req.net_shortage > 0 && !isHistorical ? "bg-[var(--status-red-tint)]" : ""
                      }`}
                    >
                      <td className="p-2">
                        <div className="text-[var(--ink)]">{req.product_sku} - {req.product_name}</div>
                        {req.material_source === "routing" && (
                          <span className="text-xs text-[var(--ink-3)]">via routing</span>
                        )}
                        {req.has_incoming_supply && (
                          <span className="text-xs text-[var(--status-amber)] ml-2" title={req.incoming_supply_details?.expected_date ? `Expected: ${req.incoming_supply_details.expected_date}` : ""}>
                            PO pending
                          </span>
                        )}
                      </td>
                      <td className="p-2 text-left">
                        {req.operation_code ? (
                          <span className="px-2 py-0.5 bg-[var(--paper-sunk)] text-[var(--ink-2)] text-xs rounded-full">
                            {req.operation_code}
                          </span>
                        ) : (
                          <span className="text-[var(--ink-4)] text-xs">-</span>
                        )}
                      </td>
                      <td className="p-2 text-right text-[var(--ink)]">
                        {req.gross_quantity?.toFixed(2) || "0.00"}
                      </td>
                      <td className="p-2 text-right text-[var(--ink-2)]">
                        {req.available_quantity?.toFixed(2) || "0.00"}
                      </td>
                      <td className="p-2 text-right">
                        <span
                          className={
                            req.net_shortage > 0
                              ? isHistorical
                                ? "text-[var(--ink-3)]"
                                : "text-[var(--status-red)] font-semibold"
                              : "text-[var(--status-green)]"
                          }
                        >
                          {req.net_shortage?.toFixed(2) || "0.00"}
                        </span>
                      </td>
                      <td className="p-2 text-center">
                        {req.net_shortage > 0 &&
                          !isHistorical &&
                          (req.has_bom ? (
                            <button
                              onClick={() => onCreateWorkOrder(req)}
                              className="text-[var(--ink)] hover:text-[var(--orange)] text-sm"
                            >
                              Create WO
                            </button>
                          ) : (
                            <button
                              onClick={() => onCreatePurchaseOrder(req)}
                              className="text-[var(--ink)] hover:text-[var(--orange)] text-sm"
                            >
                              Create PO
                            </button>
                          ))}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-[var(--paper-sunk)] font-semibold">
                    <td colSpan="4" className="p-2 text-right text-[var(--ink)]">
                      {isHistorical ? (
                        <span className="text-[var(--ink-3)]">Shown for reference</span>
                      ) : materialAvailability?.has_shortages ? (
                        <span className="text-[var(--status-red)]">
                          {materialAvailability.materials_short} of {materialAvailability.total_materials} materials short
                        </span>
                      ) : (
                        <span className="text-[var(--status-green)]">All materials available</span>
                      )}
                    </td>
                    <td className="p-2 text-right text-[var(--ink)]">
                      Est: ${totalMaterialCost.toFixed(2)}
                    </td>
                    <td className="p-2"></td>
                  </tr>
                </tfoot>
              </table>

              {showShortageAlerts && (
                <div className="mt-4 p-3 bg-[var(--status-red-tint)] border border-[var(--status-red)]/30 rounded-lg">
                  <p className="text-[var(--status-red)] text-sm">
                    Material shortages detected. Create{" "}
                    <span className="text-[var(--ink)]">Work Orders</span> for
                    sub-assemblies or{" "}
                    <span className="text-[var(--ink)]">Purchase Orders</span> for raw
                    materials.
                  </p>
                </div>
              )}
              {isHistorical && (
                <div className="mt-4 p-3 bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg">
                  <p className="text-[var(--ink-3)] text-sm">
                    Order is {(order?.status || "").replace(/_/g, " ")} —
                    requirements shown for reference; stock is not re-checked.
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
