import { useState, useEffect, useRef } from "react";

export default function SearchableSelect({
  options,
  value,
  onChange,
  placeholder = "Search...",
  displayKey = "name",
  valueKey = "id",
  formatOption = null,
  className = "",
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef(null);
  const inputRef = useRef(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Sort options alphabetically by display key
  const sortedOptions = [...options].sort((a, b) =>
    (a[displayKey] || "").localeCompare(b[displayKey] || "")
  );

  // Filter options based on search
  const filteredOptions = sortedOptions.filter((opt) => {
    const searchLower = search.toLowerCase();
    const name = (opt[displayKey] || "").toLowerCase();
    const sku = (opt.sku || "").toLowerCase();
    return name.includes(searchLower) || sku.includes(searchLower);
  });

  // Get selected option display text
  const selectedOption = options.find(
    (opt) => String(opt[valueKey]) === String(value)
  );
  const displayText = selectedOption
    ? formatOption
      ? formatOption(selectedOption)
      : `${selectedOption[displayKey]} (${selectedOption.sku})`
    : "";

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <div
        onClick={() => {
          setIsOpen(true);
          setTimeout(() => inputRef.current?.focus(), 0);
        }}
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white cursor-pointer flex items-center justify-between"
      >
        <span className={selectedOption ? "text-white" : "text-gray-500"}>
          {displayText || placeholder}
        </span>
        <svg
          className="w-4 h-4 text-gray-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M19 9l-7 7-7-7"
          />
        </svg>
      </div>

      {isOpen && (
        <div className="absolute z-50 w-full mt-1 bg-gray-800 border border-gray-700 rounded-lg shadow-xl max-h-64 overflow-hidden">
          <div className="p-2 border-b border-gray-700">
            <input
              ref={inputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Type to search..."
              className="w-full bg-gray-900 border border-gray-600 rounded px-3 py-2 text-white text-sm focus:outline-none focus:border-blue-500"
              autoFocus
            />
          </div>
          <div className="max-h-48 overflow-y-auto">
            {filteredOptions.length === 0 ? (
              <div className="px-3 py-2 text-gray-500 text-sm">
                No results found
              </div>
            ) : (
              filteredOptions.map((opt) => (
                <div
                  key={opt[valueKey]}
                  onClick={() => {
                    onChange(String(opt[valueKey]));
                    setIsOpen(false);
                    setSearch("");
                  }}
                  className={`px-3 py-2 cursor-pointer hover:bg-gray-700 text-sm ${
                    String(opt[valueKey]) === String(value)
                      ? "bg-blue-600/30 text-blue-300"
                      : "text-white"
                  }`}
                >
                  {formatOption
                    ? formatOption(opt)
                    : `${opt[displayKey]} (${opt.sku})`}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
