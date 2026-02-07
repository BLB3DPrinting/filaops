/**
 * Hook for fetching fulfillment status for a sales order.
 * UI-302 - Week 4 UI Refactor
 */
import { useState, useEffect, useCallback } from 'react';
import { API_URL } from '../config/api';

/**
 * Fetch fulfillment status for a sales order.
 * @param {number|null} orderId - Order ID to fetch fulfillment status for
 * @returns {{
 *   data: object | null,
 *   loading: boolean,
 *   error: string | null,
 *   refetch: () => void
 * }}
 */
export function useFulfillmentStatus(orderId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchFulfillmentStatus = useCallback(async () => {
    if (orderId === null || orderId === undefined) {
      setData(null);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${API_URL}/api/v1/sales-orders/${orderId}/fulfillment-status`,
        {
          headers: {
            'Content-Type': 'application/json',
          },
          credentials: 'include',
        }
      );

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error(`Order ${orderId} not found`);
        }
        throw new Error(`Failed to fetch fulfillment status: ${response.statusText}`);
      }

      const result = await response.json();

      // Parse numeric strings to numbers for consistency
      if (result.summary) {
        result.summary.lines_total = parseInt(result.summary.lines_total) || 0;
        result.summary.lines_ready = parseInt(result.summary.lines_ready) || 0;
        result.summary.fulfillment_percent = parseFloat(result.summary.fulfillment_percent) || 0;
      }

      // Parse line data
      if (result.lines) {
        result.lines = result.lines.map(line => ({
          ...line,
          line_number: parseInt(line.line_number) || 0,
          quantity_remaining: parseFloat(line.quantity_remaining) || 0,
          shortage: parseFloat(line.shortage) || 0,
        }));
      }

      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [orderId]);

  useEffect(() => {
    fetchFulfillmentStatus();
  }, [fetchFulfillmentStatus]);

  return { data, loading, error, refetch: fetchFulfillmentStatus };
}

export default useFulfillmentStatus;
