/**
 * Hooks for fetching resources (machines) and checking conflicts
 */
import { useState, useEffect } from 'react';
import { API_URL } from '../config/api';

/**
 * Hook for fetching available resources/machines
 *
 * Resources include both generic resources from the resources table
 * and printers from the printers table. Both are combined for scheduling.
 */
export function useResources(workCenterId = null) {
  const [resources, setResources] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchResources = async () => {
      if (!localStorage.getItem('adminUser')) {
        setError('Not authenticated');
        setLoading(false);
        return;
      }

      try {
        const allResources = [];

        if (workCenterId) {
          // Fetch resources for specific work center
          const [resourcesRes, printersRes] = await Promise.all([
            fetch(
              `${API_URL}/api/v1/work-centers/${workCenterId}/resources`,
              { credentials: 'include' }
            ),
            fetch(
              `${API_URL}/api/v1/work-centers/${workCenterId}/printers`,
              { credentials: 'include' }
            )
          ]);

          // Add resources
          if (resourcesRes.ok) {
            const data = await resourcesRes.json();
            allResources.push(...(Array.isArray(data) ? data : []));
          }

          // Add printers (mapped to resource format for consistency)
          if (printersRes.ok) {
            const printers = await printersRes.json();
            allResources.push(...printers.map(p => ({
              id: p.id,
              code: p.code,
              name: p.name,
              machine_type: p.model,
              status: p.status,
              is_active: p.active,
              is_printer: true  // Flag to distinguish printers
            })));
          }
        } else {
          // Fetch all work centers and extract resources + printers
          const res = await fetch(
            `${API_URL}/api/v1/work-centers/`,
            { credentials: 'include' }
          );

          if (!res.ok) throw new Error('Failed to fetch work centers');

          const workCenters = await res.json();

          // Fetch resources and printers for each work center
          for (const wc of workCenters) {
            try {
              const [wcResources, wcPrinters] = await Promise.all([
                fetch(
                  `${API_URL}/api/v1/work-centers/${wc.id}/resources`,
                  { credentials: 'include' }
                ).then(r => r.ok ? r.json() : []),
                fetch(
                  `${API_URL}/api/v1/work-centers/${wc.id}/printers`,
                  { credentials: 'include' }
                ).then(r => r.ok ? r.json() : [])
              ]);

              // Add resources with work center info
              allResources.push(...wcResources.map(r => ({
                ...r,
                work_center_name: wc.name,
                work_center_code: wc.code
              })));

              // Add printers with work center info
              allResources.push(...wcPrinters.map(p => ({
                id: p.id,
                code: p.code,
                name: p.name,
                machine_type: p.model,
                status: p.status,
                is_active: p.active,
                is_printer: true,
                work_center_name: wc.name,
                work_center_code: wc.code
              })));
            } catch {
              // Skip work centers with fetch errors
            }
          }
        }

        setResources(allResources);
        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchResources();
  }, [workCenterId]);

  return { resources, loading, error };
}

/**
 * Hook for checking resource scheduling conflicts
 *
 * Uses the existing schedule endpoint to check for conflicts without committing.
 * Since we don't have a dedicated conflicts endpoint, this simulates by checking
 * if scheduling would succeed.
 */
export function useResourceConflicts(resourceId, startTime, endTime) {
  const [conflicts, setConflicts] = useState([]);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const checkConflicts = async () => {
      if (!resourceId || !startTime || !endTime) {
        setConflicts([]);
        return;
      }

      setChecking(true);
      try {
        // Check for conflicting operations on this resource in the time range
        // This queries scheduled operations for the resource
        const params = new URLSearchParams({
          resource_id: resourceId,
          start: new Date(startTime).toISOString(),
          end: new Date(endTime).toISOString()
        });

        const res = await fetch(
          `${API_URL}/api/v1/scheduling/resource-conflicts?${params}`,
          { credentials: 'include' }
        );

        if (res.ok) {
          const data = await res.json();
          setConflicts(data.conflicts || []);
        } else if (res.status === 404) {
          // Endpoint might not exist yet, no conflicts
          setConflicts([]);
        } else {
          throw new Error('Failed to check conflicts');
        }
        setError(null);
      } catch {
        // If conflict check fails, assume no conflicts (endpoint may not exist)
        setConflicts([]);
        setError(null);
      } finally {
        setChecking(false);
      }
    };

    // Debounce the conflict check
    const timer = setTimeout(checkConflicts, 300);
    return () => clearTimeout(timer);
  }, [resourceId, startTime, endTime]);

  return { conflicts, checking, error, hasConflicts: conflicts.length > 0 };
}
