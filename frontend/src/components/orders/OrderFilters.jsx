/**
 * OrderFilters - Filter and sort controls for sales orders list
 * UI-303 - Week 4 UI Refactor
 */

// Fulfillment state filter options
const FILTER_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'pending_review', label: 'Pending Review', color: 'purple' },
  { value: 'ready_to_ship', label: 'Ready to Ship', color: 'green' },
  { value: 'partially_ready', label: 'Partially Ready', color: 'yellow' },
  { value: 'blocked', label: 'Blocked', color: 'red' },
  { value: 'shipped', label: 'Shipped', color: 'gray' },
];

// Sort options with field:order format
const SORT_OPTIONS = [
  { value: 'fulfillment_priority:asc', label: 'Most Actionable First' },
  { value: 'order_date:desc', label: 'Newest First' },
  { value: 'order_date:asc', label: 'Oldest First' },
  { value: 'fulfillment_percent:desc', label: 'Most Complete First' },
  { value: 'fulfillment_percent:asc', label: 'Least Complete First' },
  { value: 'customer_name:asc', label: 'Customer A-Z' },
  { value: 'total:desc', label: 'Highest Value First' },
];

// Color classes for filter buttons
const FILTER_COLORS = {
  purple: {
    active: 'bg-purple-600 text-white border-purple-600',
    inactive: 'bg-purple-500/10 text-purple-400 border-purple-500/30 hover:bg-purple-500/20',
  },
  green: {
    active: 'bg-green-600 text-white border-green-600',
    inactive: 'bg-green-500/10 text-green-400 border-green-500/30 hover:bg-green-500/20',
  },
  yellow: {
    active: 'bg-yellow-600 text-white border-yellow-600',
    inactive: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30 hover:bg-yellow-500/20',
  },
  red: {
    active: 'bg-red-600 text-white border-red-600',
    inactive: 'bg-red-500/10 text-red-400 border-red-500/30 hover:bg-red-500/20',
  },
  gray: {
    active: 'bg-gray-600 text-white border-gray-600',
    inactive: 'bg-gray-500/10 text-gray-400 border-gray-500/30 hover:bg-gray-500/20',
  },
  default: {
    active: 'bg-blue-600 text-white border-blue-600',
    inactive: 'bg-gray-800 text-gray-300 border-gray-700 hover:bg-gray-700',
  },
};

/**
 * OrderFilters component
 *
 * @param {Object} props
 * @param {string} props.selectedFilter - Current fulfillment state filter (empty string for 'all')
 * @param {Function} props.onFilterChange - Called with new filter value
 * @param {string} props.selectedSort - Current sort value (format: 'field:order')
 * @param {Function} props.onSortChange - Called with new sort value
 * @param {string} [props.search] - Current search query
 * @param {Function} [props.onSearchChange] - Called with new search value
 */
export default function OrderFilters({
  selectedFilter,
  onFilterChange,
  selectedSort,
  onSortChange,
  search,
  onSearchChange,
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 mb-6">
      {/* Search and Sort Row */}
      <div className="flex flex-col sm:flex-row gap-4 mb-4">
        {/* Search Input */}
        {onSearchChange && (
          <div className="flex-1">
            <div className="relative">
              <svg
                className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              <input
                type="text"
                placeholder="Search orders..."
                value={search || ''}
                onChange={(e) => onSearchChange(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-10 pr-4 py-2 text-white placeholder-gray-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
            </div>
          </div>
        )}

        {/* Sort Dropdown */}
        <div className="flex items-center gap-2">
          <label htmlFor="order-sort" className="text-sm text-gray-400 whitespace-nowrap">
            Sort by:
          </label>
          <select
            id="order-sort"
            value={selectedSort}
            onChange={(e) => onSortChange(e.target.value)}
            className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          >
            {SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Filter Buttons Row */}
      <div className="flex flex-wrap gap-2">
        <span className="text-sm text-gray-400 py-1.5 mr-1">Filter:</span>
        {FILTER_OPTIONS.map((option) => {
          const isActive = selectedFilter === option.value;
          const colorConfig = FILTER_COLORS[option.color] || FILTER_COLORS.default;
          const colorClass = isActive ? colorConfig.active : colorConfig.inactive;

          return (
            <button
              key={option.value}
              onClick={() => onFilterChange(option.value)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${colorClass}`}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
