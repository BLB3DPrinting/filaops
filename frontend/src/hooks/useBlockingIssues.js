/**
 * Hook for fetching blocking issues for sales or production orders.
 */
import { useState, useEffect, useCallback } from 'react';
import { API_URL } from '../config/api';

/**
 * Fetch blocking issues for an order.
 * @param {'sales' | 'production'} orderType - Type of order
 * @param {number|null} orderId - Order ID to fetch blocking issues for
 * @returns {{
 *   data: object | null,
 *   loading: boolean,
 *   error: string | null,
 *   refetch: () => void
 * }}
 */
export function useBlockingIssues(orderType, orderId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchBlockingIssues = useCallback(async () => {
    if (orderId === null || orderId === undefined) {
      setData(null);
      return;
    }

    if (!orderType || !['sales', 'production'].includes(orderType)) {
      setError('Invalid order type');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const endpoint = orderType === 'sales'
        ? `${API_URL}/api/v1/sales-orders/${orderId}/blocking-issues`
        : `${API_URL}/api/v1/production-orders/${orderId}/blocking-issues`;

      const response = await fetch(endpoint, {
        headers: {
          'Content-Type': 'application/json',
        },
        credentials: 'include',
      });

      if (!response.ok) {
        if (response.status === 404) {
          throw new Error(`Order ${orderId} not found`);
        }
        throw new Error(`Failed to fetch blocking issues: ${response.statusText}`);
      }

      const result = await response.json();

      // Parse numeric strings to numbers for consistency
      if (result.status_summary) {
        result.status_summary.blocking_count = parseInt(result.status_summary.blocking_count) || 0;
      }

      // Parse line_issues for sales orders
      if (result.line_issues) {
        result.line_issues = result.line_issues.map(line => ({
          ...line,
          quantity_ordered: parseFloat(line.quantity_ordered) || 0,
          quantity_available: parseFloat(line.quantity_available) || 0,
          quantity_short: parseFloat(line.quantity_short) || 0,
        }));
      }

      // Parse material_issues for production orders
      if (result.material_issues) {
        result.material_issues = result.material_issues.map(mat => ({
          ...mat,
          quantity_required: parseFloat(mat.quantity_required) || 0,
          quantity_available: parseFloat(mat.quantity_available) || 0,
          quantity_short: parseFloat(mat.quantity_short) || 0,
        }));
      }

      // Parse quantity fields for production orders
      if (result.quantity_ordered !== undefined) {
        result.quantity_ordered = parseFloat(result.quantity_ordered) || 0;
        result.quantity_completed = parseFloat(result.quantity_completed) || 0;
        result.quantity_remaining = parseFloat(result.quantity_remaining) || 0;
      }

      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [orderType, orderId]);

  useEffect(() => {
    fetchBlockingIssues();
  }, [fetchBlockingIssues]);

  return { data, loading, error, refetch: fetchBlockingIssues };
}

export default useBlockingIssues;
