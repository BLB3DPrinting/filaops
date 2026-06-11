import EmptyState from "../EmptyState";

export default function VendorsTab({
  filteredVendors,
  hasActiveFilters,
  onClearFilters,
  onCreateVendor,
  onViewVendor,
  onEditVendor,
  onDeleteVendor,
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
      <table className="w-full">
        <thead className="bg-gray-800/50">
          <tr>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Code
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Name
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Contact
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Email
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Phone
            </th>
            <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Location
            </th>
            <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              POs
            </th>
            <th className="text-center py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Active
            </th>
            <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">
              Actions
            </th>
          </tr>
        </thead>
        <tbody>
          {filteredVendors.map((vendor) => (
            <tr
              key={vendor.id}
              className="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer"
              onClick={() => onViewVendor(vendor)}
            >
              <td className="py-3 px-4 text-white font-medium">
                {vendor.code}
              </td>
              <td className="py-3 px-4 text-blue-400 hover:text-blue-300">
                {vendor.name}
              </td>
              <td className="py-3 px-4 text-gray-400">
                {vendor.contact_name || "-"}
              </td>
              <td className="py-3 px-4 text-gray-400">
                {vendor.email || "-"}
              </td>
              <td className="py-3 px-4 text-gray-400">
                {vendor.phone || "-"}
              </td>
              <td className="py-3 px-4 text-gray-400">
                {vendor.city && vendor.state
                  ? `${vendor.city}, ${vendor.state}`
                  : "-"}
              </td>
              <td className="py-3 px-4 text-center text-gray-400">
                {vendor.po_count}
              </td>
              <td className="py-3 px-4 text-center">
                <span
                  className={`px-2 py-1 rounded-full text-xs ${
                    vendor.is_active
                      ? "bg-green-500/20 text-green-400"
                      : "bg-red-500/20 text-red-400"
                  }`}
                >
                  {vendor.is_active ? "Yes" : "No"}
                </span>
              </td>
              <td className="py-3 px-4 text-right space-x-2" onClick={(e) => e.stopPropagation()}>
                <button
                  onClick={() => onViewVendor(vendor)}
                  className="text-gray-400 hover:text-white text-sm"
                >
                  View
                </button>
                <button
                  onClick={() => onEditVendor(vendor)}
                  className="text-blue-400 hover:text-blue-300 text-sm"
                >
                  Edit
                </button>
                <button
                  onClick={() => onDeleteVendor(vendor.id)}
                  className="text-red-400 hover:text-red-300 text-sm"
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
          {filteredVendors.length === 0 && (
            <tr>
              <td colSpan={9} className="py-4">
                {hasActiveFilters ? (
                  <EmptyState
                    icon="filter"
                    title="No vendors match your filters"
                    onClearFilters={onClearFilters}
                  />
                ) : (
                  <EmptyState
                    icon="customers"
                    title="No vendors yet"
                    description="Add your first vendor to start creating purchase orders."
                    actionLabel="Add Vendor"
                    onAction={onCreateVendor}
                  />
                )}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
