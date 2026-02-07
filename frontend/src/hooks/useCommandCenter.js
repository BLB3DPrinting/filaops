/**
 * useCommandCenter - Hook for fetching Command Center data
 *
 * Provides action items, summary stats, and resource statuses
 * with auto-refresh capability.
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import { API_URL } from '../config/api';

/**
 * Fetch action items requiring attention
 */
export function useActionItems(autoRefresh = false, refreshInterval = 60000) {
  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const fetchData = useCallback(async () => {
    if (!localStorage.getItem('adminUser')) {
      setError('Not authenticated');
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_URL}/api/v1/command-center/action-items`, {
        credentials: 'include',
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      setItems(data.items || []);
      setCounts(data.counts_by_type || {});
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();

    if (autoRefresh && refreshInterval > 0) {
      intervalRef.current = setInterval(fetchData, refreshInterval);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchData, autoRefresh, refreshInterval]);

  return { items, counts, loading, error, refetch: fetchData };
}

/**
 * Fetch today's summary statistics
 */
export function useSummary(autoRefresh = false, refreshInterval = 60000) {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const fetchData = useCallback(async () => {
    if (!localStorage.getItem('adminUser')) {
      setError('Not authenticated');
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_URL}/api/v1/command-center/summary`, {
        credentials: 'include',
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      setSummary(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();

    if (autoRefresh && refreshInterval > 0) {
      intervalRef.current = setInterval(fetchData, refreshInterval);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchData, autoRefresh, refreshInterval]);

  return { summary, loading, error, refetch: fetchData };
}

/**
 * Fetch resource/machine statuses
 */
export function useResourceStatuses(autoRefresh = false, refreshInterval = 30000) {
  const [resources, setResources] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const intervalRef = useRef(null);

  const fetchData = useCallback(async () => {
    if (!localStorage.getItem('adminUser')) {
      setError('Not authenticated');
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_URL}/api/v1/command-center/resources`, {
        credentials: 'include',
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const data = await res.json();
      setResources(data.resources || []);
      setSummary(data.summary || {});
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();

    if (autoRefresh && refreshInterval > 0) {
      intervalRef.current = setInterval(fetchData, refreshInterval);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [fetchData, autoRefresh, refreshInterval]);

  return { resources, summary, loading, error, refetch: fetchData };
}

/**
 * Combined hook for all Command Center data
 */
export function useCommandCenter(autoRefresh = true, refreshInterval = 60000) {
  const actionItems = useActionItems(autoRefresh, refreshInterval);
  const todaySummary = useSummary(autoRefresh, refreshInterval);
  const resourceStatuses = useResourceStatuses(autoRefresh, refreshInterval / 2); // Resources refresh faster

  const refetchAll = useCallback(() => {
    actionItems.refetch();
    todaySummary.refetch();
    resourceStatuses.refetch();
  }, [actionItems, todaySummary, resourceStatuses]);

  const loading = actionItems.loading || todaySummary.loading || resourceStatuses.loading;
  const error = actionItems.error || todaySummary.error || resourceStatuses.error;

  return {
    actionItems: actionItems.items,
    actionCounts: actionItems.counts,
    summary: todaySummary.summary,
    resources: resourceStatuses.resources,
    resourceSummary: resourceStatuses.summary,
    loading,
    error,
    refetch: refetchAll
  };
}

export default useCommandCenter;
