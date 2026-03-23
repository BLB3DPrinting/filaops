import StatCard from "../StatCard";

// Item type options used in the filter dropdown
const ITEM_TYPES = [
  { value: "finished_good", label: "Finished Good", color: "blue" },
  { value: "component", label: "Component", color: "purple" },
  { value: "material", label: "Material", color: "orange" },
  { value: "filament", label: "Filament (Legacy)", color: "orange" },
  { value: "supply", label: "Supply", color: "yellow" },
  { value: "service", label: "Service", color: "green" },
];

/**
 * Filter controls and stat cards for the Items page.
 * Contains search input, type dropdown, active-only toggle, and clickable stat cards.
 */
export default function ItemsFilterBar({
  filters,
  onFiltersChange,
  quickFilter,
  onQuickFilterChange,
  stats,
}) {
  function handleStatClick(filterKey) {
    if (filterKey === "all") {
      onQuickFilterChange(quickFilter === "all" ? null : "all");
      onFiltersChange({ ...filters, itemType: "all" });
      return;
    }

    if (filterKey === "needs_reorder") {
      onQuickFilterChange(quickFilter === "needs_reorder" ? null : "needs_reorder");
      return;
    }

    const isActive = quickFilter === filterKey;
    onQuickFilterChange(isActive ? null : filterKey);
    onFiltersChange({ ...filters, itemType: isActive ? "all" : filterKey });
  }

  return (
    <>
      {/* Filters */}
      <div className="flex gap-4 bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div className="flex-1">
          <input
            type="text"
            placeholder="Search by SKU, name, or UPC..."
            value={filters.search}
            onChange={(e) =>
              onFiltersChange({ ...filters, search: e.target.value })
            }
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500"
          />
        </div>
        <select
          value={filters.itemType}
          onChange={(e) => {
            onFiltersChange({ ...filters, itemType: e.target.value });
            onQuickFilterChange(null);
          }}
          className="bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
        >
          <option value="all">All Types</option>
          {ITEM_TYPES.map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-2 text-gray-400">
          <input
            type="checkbox"
            checked={filters.activeOnly}
            onChange={(e) =>
              onFiltersChange({ ...filters, activeOnly: e.target.checked })
            }
            className="rounded"
          />
          Active only
        </label>
        <label className="flex items-center gap-2 text-gray-400">
          <input
            type="checkbox"
            checked={filters.includeVariants}
            onChange={(e) =>
              onFiltersChange({ ...filters, includeVariants: e.target.checked })
            }
            className="rounded"
          />
          Show variants
        </label>
      </div>

      {/* Stats - Clickable filters */}
      <div className="grid grid-cols-6 gap-4">
        <StatCard
          variant="simple"
          title="Total Items"
          value={stats.total}
          color="neutral"
          onClick={() => handleStatClick("all")}
          active={quickFilter === "all"}
        />
        <StatCard
          variant="simple"
          title="Finished Goods"
          value={stats.finishedGoods}
          color="primary"
          onClick={() => handleStatClick("finished_good")}
          active={quickFilter === "finished_good"}
        />
        <StatCard
          variant="simple"
          title="Components"
          value={stats.components}
          color="secondary"
          onClick={() => handleStatClick("component")}
          active={quickFilter === "component"}
        />
        <StatCard
          variant="simple"
          title="Materials"
          value={stats.materials}
          color="primary"
          onClick={() => handleStatClick("material")}
          active={quickFilter === "material"}
        />
        <StatCard
          variant="simple"
          title="Supplies"
          value={stats.supplies}
          color="warning"
          onClick={() => handleStatClick("supply")}
          active={quickFilter === "supply"}
        />
        <StatCard
          variant="simple"
          title="Needs Reorder"
          value={stats.needsReorder}
          color="danger"
          onClick={() => handleStatClick("needs_reorder")}
          active={quickFilter === "needs_reorder"}
        />
      </div>
    </>
  );
}
