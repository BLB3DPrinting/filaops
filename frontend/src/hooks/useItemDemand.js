/**
 * Hook for fetching item demand summary.
 */
import { useState, useEffect, useCallback } from 'react';
import { API_URL } from '../config/api';

/**
 * Fetch item demand summary from API.
 * @param {number|null} itemId - Item ID to fetch demand for
 * @returns {{
 *   data: import('../types/itemDemand').ItemDemandSummary | null,
 *   loading: boolean,
 *   error: string | null,
 *   refetch: () => void
 * }}
 */
export function useItemDemand(itemId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchDemand = useCallback(async () => {
    if (itemId === null || itemId === undefined) {
      setData(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_URL}/api/v1/items/${itemId}/demand-summary`, {
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
      });

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error(`Item ${itemId} not found`);
        }
        throw new Error(`Failed to fetch demand summary: ${response.statusText}`);
      }

      const result = await response.json();

      // Parse numeric strings to numbers for consistency
      if (result.quantities) {
        result.quantities = {
          on_hand: parseFloat(result.quantities.on_hand) || 0,
          allocated: parseFloat(result.quantities.allocated) || 0,
          available: parseFloat(result.quantities.available) || 0,
          incoming: parseFloat(result.quantities.incoming) || 0,
          projected: parseFloat(result.quantities.projected) || 0,
        };
      }
      if (result.shortage) {
        result.shortage.quantity = parseFloat(result.shortage.quantity) || 0;
      }
      if (result.allocations) {
        result.allocations = result.allocations.map(a => ({
          ...a,
          quantity: parseFloat(a.quantity) || 0,
        }));
      }
      if (result.incoming) {
        result.incoming = result.incoming.map(i => ({
          ...i,
          quantity: parseFloat(i.quantity) || 0,
        }));
      }

      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [itemId]);

  useEffect(() => {
    fetchDemand();
  }, [fetchDemand]);

  return { data, loading, error, refetch: fetchDemand };
}

/**
 * Hook for fetching multiple items' demand summaries.
 * @param {number[]} itemIds - Array of item IDs
 * @returns {{
 *   data: Map<number, import('../types/itemDemand').ItemDemandSummary>,
 *   loading: boolean,
 *   error: string | null
 * }}
 */
export function useMultipleItemDemands(itemIds) {
  const [data, setData] = useState(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Serialize itemIds for stable dependency tracking
  const itemIdsKey = itemIds?.join(',') || '';

  useEffect(() => {
    if (!itemIds || itemIds.length === 0) {
      setData(new Map());
      return;
    }

    const fetchAll = async () => {
      setLoading(true);
      setError(null);

      try {
        const results = await Promise.all(
          itemIds.map(async (id) => {
            try {
              const response = await fetch(`${API_URL}/api/v1/items/${id}/demand-summary`, {
                headers: {
                  'Content-Type': 'application/json',
                },
                credentials: 'include',
              });
              if (!response.ok) return null;
              return response.json();
            } catch {
              return null;
            }
          })
        );

        const newData = new Map();
        results.forEach((result, index) => {
          if (result) {
            newData.set(itemIds[index], result);
          }
        });
        setData(newData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchAll();
  }, [itemIds, itemIdsKey]); // Re-fetch when item list changes

  return { data, loading, error };
}

export default useItemDemand;
