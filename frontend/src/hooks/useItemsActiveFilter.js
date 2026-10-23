/**
 * useItemsActiveFilter - Active / Inactive / All filter for the Items list,
 * persisted in the URL as ?active= (same convention as AdminBOM).
 *
 * "active" is the default and is omitted from the URL to keep links clean.
 */
import { useCallback } from "react";
import { useSearchParams } from "react-router-dom";

export const ACTIVE_FILTER_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "all", label: "All" },
];

const VALID = new Set(ACTIVE_FILTER_OPTIONS.map((o) => o.value));

/** Map the filter to list-endpoint query params. */
export function activeFilterToQuery(value) {
  if (value === "inactive") return { active: "false" };
  if (value === "all") return { active_only: "false" };
  return { active_only: "true" };
}

export default function useItemsActiveFilter() {
  const [searchParams, setSearchParams] = useSearchParams();
  const raw = searchParams.get("active");
  const value = VALID.has(raw) ? raw : "active";

  const setValue = useCallback(
    (next) => {
      setSearchParams(
        (prev) => {
          const params = new URLSearchParams(prev);
          if (next === "active" || !VALID.has(next)) params.delete("active");
          else params.set("active", next);
          return params;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  return [value, setValue];
}
