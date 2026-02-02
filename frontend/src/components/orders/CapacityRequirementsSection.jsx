/**
 * CapacityRequirementsSection - Routing capacity requirements table.
 *
 * Extracted from OrderDetail.jsx (ARCHITECT-002)
 */

export default function CapacityRequirementsSection({
  capacityRequirements,
  expandedSections,
  onToggle,
  orderQuantity,
}) {
  const totalCapacityHours = capacityRequirements.reduce(
    (sum, op) => sum + (op.total_time_minutes || 0) / 60,
    0
  );

  if (capacityRequirements.length === 0) return null;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <button
        onClick={() => onToggle("capacityRequirements")}
        className="flex items-center gap-2 text-lg font-semibold text-white hover:text-gray-300 mb-4"
      >
        <svg
          className={`w-5 h-5 transition-transform ${expandedSections.capacityRequirements ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
        Capacity Requirements
      </button>
      {expandedSections.capacityRequirements && (
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-700">
              <th className="text-left p-2 text-gray-400">Operation</th>
              <th className="text-left p-2 text-gray-400">Work Center</th>
              <th className="text-right p-2 text-gray-400">Setup (min)</th>
              <th className="text-right p-2 text-gray-400">Run (min)</th>
              <th className="text-right p-2 text-gray-400">Total (hrs)</th>
            </tr>
          </thead>
          <tbody>
            {capacityRequirements.map((op, idx) => (
              <tr key={idx} className="border-b border-gray-800">
                <td className="p-2 text-white">
                  {op.operation_name || op.operation_code || `OP${idx + 1}`}
                </td>
                <td className="p-2 text-gray-300">{op.work_center_name}</td>
                <td className="p-2 text-right text-gray-300">
                  {op.setup_time_minutes?.toFixed(1) || "0.0"}
                </td>
                <td className="p-2 text-right text-gray-300">
                  {((op.run_time_minutes || 0) * orderQuantity).toFixed(1)}
                </td>
                <td className="p-2 text-right text-white">
                  {(op.total_time_minutes / 60).toFixed(2)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="bg-gray-800 font-semibold">
              <td colSpan="4" className="p-2 text-right text-white">
                Total Time:
              </td>
              <td className="p-2 text-right text-white">
                {totalCapacityHours.toFixed(2)} hrs
              </td>
            </tr>
          </tfoot>
        </table>
      )}
    </div>
  );
}
