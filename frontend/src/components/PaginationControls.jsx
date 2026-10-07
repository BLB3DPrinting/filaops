/**
 * Reusable Pagination Controls Component
 * Works with the standardized pagination from usePagination hook
 */
import React from "react";

/**
 * @typedef {Object} PaginationControlsProps
 * @property {Object} pagination - Pagination object from usePagination hook
 * @property {number} pagination.currentPage - Current page number
 * @property {number} pagination.totalPages - Total number of pages
 * @property {number} pagination.total - Total number of items
 * @property {number} pagination.offset - Current offset
 * @property {number} pagination.limit - Items per page
 * @property {number} [pagination.returned] - Actual items returned (from API)
 * @property {boolean} pagination.hasNext - Whether there's a next page
 * @property {boolean} pagination.hasPrev - Whether there's a previous page
 * @property {() => void} pagination.nextPage - Go to next page
 * @property {() => void} pagination.prevPage - Go to previous page
 * @property {(page: number) => void} pagination.goToPage - Go to specific page
 * @property {string} [className] - Additional CSS classes
 * @property {boolean} [showPageSize=false] - Show page size selector
 * @property {(limit: number) => void} [onPageSizeChange] - Called when page size changes
 * @property {number[]} [pageSizeOptions] - Available page size options
 */

/**
 * Pagination controls with page info and navigation buttons
 * @param {PaginationControlsProps} props
 */
export function PaginationControls({
  pagination,
  className = "",
  showPageSize = false,
  onPageSizeChange,
  pageSizeOptions = [10, 25, 50, 100, 200],
}) {
  if (!pagination || pagination.totalPages === 0) {
    return null;
  }

  const {
    currentPage,
    totalPages,
    total,
    offset,
    limit,
    returned,
    hasNext,
    hasPrev,
    nextPage,
    prevPage,
    goToPage,
  } = pagination;

  // Calculate range of items being shown
  const startItem = offset + 1;
  const endItem = returned !== undefined ? offset + returned : Math.min(offset + limit, total);

  // Generate page numbers to show (with ellipsis for large page counts)
  const getPageNumbers = () => {
    const pages = [];
    const maxPages = 7; // Show at most 7 page buttons

    if (totalPages <= maxPages) {
      // Show all pages
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      // Show first, last, current, and surrounding pages with ellipsis
      pages.push(1);

      if (currentPage > 3) {
        pages.push("...");
      }

      const startPage = Math.max(2, currentPage - 1);
      const endPage = Math.min(totalPages - 1, currentPage + 1);

      for (let i = startPage; i <= endPage; i++) {
        pages.push(i);
      }

      if (currentPage < totalPages - 2) {
        pages.push("...");
      }

      pages.push(totalPages);
    }

    return pages;
  };

  const pageNumbers = getPageNumbers();

  return (
    <div className={`flex flex-col sm:flex-row items-center justify-between gap-4 ${className}`}>
      {/* Results info */}
      <div className="text-sm text-ink-3">
        {total > 0 ? (
          <>
            Showing <span className="font-medium text-ink">{startItem}</span> to{" "}
            <span className="font-medium text-ink">{endItem}</span> of{" "}
            <span className="font-medium text-ink">{total}</span> results
          </>
        ) : (
          "No results"
        )}
      </div>

      {/* Page size selector */}
      {showPageSize && onPageSizeChange && (
        <div className="flex items-center gap-2">
          <span className="text-sm text-ink-3">Show:</span>
          <select
            value={limit}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="h-8 px-2 bg-paper text-ink border border-hair rounded text-sm"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
          <span className="text-sm text-ink-3">per page</span>
        </div>
      )}

      {/* Navigation */}
      <div className="flex items-center gap-2">
        {/* Previous button */}
        <button
          onClick={prevPage}
          disabled={!hasPrev}
          className="h-8 px-3 bg-paper text-ink rounded border border-hair hover:bg-paper-sunk disabled:bg-paper-sunk disabled:text-ink-4 disabled:cursor-not-allowed transition-colors text-sm"
          aria-label="Previous page"
        >
          Previous
        </button>

        {/* Page numbers */}
        <div className="hidden sm:flex items-center gap-1">
          {pageNumbers.map((page, index) => {
            if (page === "...") {
              return (
                <span key={`ellipsis-${index}`} className="px-2 text-ink-3">
                  ...
                </span>
              );
            }

            const isActive = page === currentPage;

            return (
              <button
                key={page}
                onClick={() => goToPage(page)}
                className={`h-8 min-w-8 px-3 rounded text-sm transition-colors ${
                  isActive
                    ? "bg-ink text-paper border border-ink font-medium font-mono-data"
                    : "bg-paper text-ink hover:bg-paper-sunk border border-hair font-mono-data"
                }`}
                aria-label={`Go to page ${page}`}
                aria-current={isActive ? "page" : undefined}
              >
                {page}
              </button>
            );
          })}
        </div>

        {/* Mobile page indicator */}
        <div className="sm:hidden px-3 py-1 text-sm text-ink-2">
          Page {currentPage} of {totalPages}
        </div>

        {/* Next button */}
        <button
          onClick={nextPage}
          disabled={!hasNext}
          className="h-8 px-3 bg-paper text-ink rounded border border-hair hover:bg-paper-sunk disabled:bg-paper-sunk disabled:text-ink-4 disabled:cursor-not-allowed transition-colors text-sm"
          aria-label="Next page"
        >
          Next
        </button>
      </div>
    </div>
  );
}

/**
 * Simple pagination controls (just prev/next, no page numbers)
 * @param {PaginationControlsProps} props
 */
export function SimplePaginationControls({ pagination, className = "" }) {
  if (!pagination || pagination.totalPages === 0) {
    return null;
  }

  const { currentPage, totalPages, hasNext, hasPrev, nextPage, prevPage } = pagination;

  return (
    <div className={`flex items-center justify-between ${className}`}>
      <button
        onClick={prevPage}
        disabled={!hasPrev}
        className="h-10 px-4 bg-paper text-ink rounded border border-hair hover:bg-paper-sunk disabled:bg-paper-sunk disabled:text-ink-4 disabled:cursor-not-allowed transition-colors"
      >
        Previous
      </button>

      <span className="text-sm text-ink-3">
        Page {currentPage} of {totalPages}
      </span>

      <button
        onClick={nextPage}
        disabled={!hasNext}
        className="h-10 px-4 bg-paper text-ink rounded border border-hair hover:bg-paper-sunk disabled:bg-paper-sunk disabled:text-ink-4 disabled:cursor-not-allowed transition-colors"
      >
        Next
      </button>
    </div>
  );
}
