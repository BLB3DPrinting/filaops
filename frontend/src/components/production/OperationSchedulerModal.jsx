/**
 * OperationSchedulerModal - Schedule an operation on a resource
 *
 * Allows selecting resource and time slot with conflict detection.
 */
import { useState, useEffect } from 'react';
import { API_URL } from '../../config/api';
import { useResources, useResourceConflicts } from '../../hooks/useResources';
import { formatDuration, formatTime } from '../../utils/formatting';
import Modal from '../Modal';

/**
 * Conflict alert banner with next-available slot suggestion
 */
function ConflictAlert({ conflicts, nextAvailableStart, nextAvailableEnd, onUseSlot }) {
  if (!conflicts || conflicts.length === 0) return null;

  return (
    <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <svg className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <div className="flex-1">
          <h4 className="text-red-400 font-medium">Conflict Detected</h4>
          <p className="text-sm text-red-400/70 mt-1">
            This time slot overlaps with:
          </p>
          <ul className="mt-2 space-y-1">
            {conflicts.map((conflict, idx) => (
              <li key={idx} className="text-sm text-red-300">
                - {conflict.production_order_code || conflict.po_code} - {conflict.operation_code || 'Operation'}
                {conflict.scheduled_start && (
                  <span className="text-red-400/50">
                    {' '}({formatTime(conflict.scheduled_start)} - {formatTime(conflict.scheduled_end)})
                  </span>
                )}
              </li>
            ))}
          </ul>
          {nextAvailableStart ? (
            <div className="mt-3 p-2 bg-blue-500/10 border border-blue-500/30 rounded">
              <p className="text-sm text-blue-300">
                Next available slot: {formatTime(nextAvailableStart)} - {formatTime(nextAvailableEnd)}
              </p>
              <button
                type="button"
                onClick={() => onUseSlot(nextAvailableStart, nextAvailableEnd)}
                className="mt-1 text-sm text-blue-400 hover:text-blue-300 underline"
              >
                Use suggested time
              </button>
            </div>
          ) : (
            <p className="text-xs text-red-400/50 mt-2">
              Adjust the start time or select a different resource.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Compatibility warning banner
 */
function CompatibilityWarning({ reason }) {
  if (!reason) return null;

  return (
    <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-lg p-3">
      <div className="flex items-start gap-2">
        <svg className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
        <div>
          <h4 className="text-yellow-400 font-medium text-sm">Incompatible Resource</h4>
          <p className="text-sm text-yellow-400/70 mt-1">{reason}</p>
        </div>
      </div>
    </div>
  );
}

/**
 * Main modal component
 */
export default function OperationSchedulerModal({
  isOpen,
  onClose,
  operation,
  productionOrder,
  onScheduled
}) {
  const [resourceId, setResourceId] = useState('');
  const [startTime, setStartTime] = useState('');
  const [endTime, setEndTime] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [compatWarning, setCompatWarning] = useState(null);
  const [nextAvailableStart, setNextAvailableStart] = useState(null);
  const [nextAvailableEnd, setNextAvailableEnd] = useState(null);
  const [serverConflicts, setServerConflicts] = useState([]);

  // Get available resources for the operation's work center
  const { resources, loading: loadingResources } = useResources(operation?.work_center_id);

  // Get the selected resource object to check if it's a printer
  const selectedResource = resources.find(r => String(r.id) === resourceId);

  // Check for conflicts
  const { conflicts, checking, hasConflicts } = useResourceConflicts(
    resourceId ? parseInt(resourceId) : null,
    startTime,
    endTime
  );

  // Calculate estimated duration
  const estimatedMinutes = operation
    ? (operation.planned_setup_minutes || 0) + (operation.planned_run_minutes || 0)
    : 0;

  // Auto-calculate end time when start time changes
  useEffect(() => {
    if (startTime && estimatedMinutes > 0) {
      const start = new Date(startTime);
      const end = new Date(start.getTime() + estimatedMinutes * 60000);
      setEndTime(end.toISOString().slice(0, 16)); // Format for datetime-local input
    }
  }, [startTime, estimatedMinutes]);

  // Set default start time to now (rounded to next 15 min)
  useEffect(() => {
    if (isOpen && !startTime) {
      const now = new Date();
      now.setMinutes(Math.ceil(now.getMinutes() / 15) * 15, 0, 0);
      setStartTime(now.toISOString().slice(0, 16));
    }
  }, [isOpen, startTime]);

  // Pre-select resource if operation already has one
  useEffect(() => {
    if (isOpen && operation?.resource_id) {
      setResourceId(String(operation.resource_id));
    }
  }, [isOpen, operation]);

  // Check compatibility when resource changes
  useEffect(() => {
    setCompatWarning(null);
    if (!resourceId || !productionOrder?.id) return;

    const selectedRes = resources.find(r => String(r.id) === resourceId);
    if (!selectedRes) return;

    const checkCompat = async () => {
      try {
        const params = new URLSearchParams({
          resource_id: resourceId,
          is_printer: selectedRes.is_printer ? 'true' : 'false',
        });
        const res = await fetch(
          `${API_URL}/api/v1/production-orders/${productionOrder.id}/check-resource-compatibility?${params}`,
          { credentials: 'include' }
        );
        if (res.ok) {
          const data = await res.json();
          if (!data.compatible) {
            setCompatWarning(data.reason);
          }
        }
      } catch {
        // Silently ignore - backend will still reject on submit
      }
    };

    checkCompat();
  }, [resourceId, productionOrder?.id, resources]);

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!resourceId || !startTime || !endTime) {
      setError('Please fill in all required fields');
      return;
    }

    if (hasConflicts) {
      setError('Cannot schedule with conflicts. Please resolve conflicts first.');
      return;
    }

    if (compatWarning) {
      setError(`Cannot schedule: ${compatWarning}`);
      return;
    }

    setSubmitting(true);
    setError(null);
    setServerConflicts([]);
    setNextAvailableStart(null);
    setNextAvailableEnd(null);

    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/operations/${operation.id}/schedule`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            resource_id: parseInt(resourceId),
            scheduled_start: new Date(startTime).toISOString(),
            scheduled_end: new Date(endTime).toISOString(),
            is_printer: selectedResource?.is_printer || false
          })
        }
      );

      const data = await res.json();

      if (!res.ok) {
        // 422 = sequence error or compatibility error
        throw new Error(data.detail || 'Failed to schedule operation');
      }

      if (data.success === false) {
        // Conflict response with next-available suggestion
        setServerConflicts(data.conflicts || []);
        if (data.next_available_start) {
          setNextAvailableStart(data.next_available_start);
          setNextAvailableEnd(data.next_available_end);
        }
        setError(data.message || 'Scheduling conflict');
        return;
      }

      onScheduled?.();
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleUseSuggestedSlot = (suggestedStart, suggestedEnd) => {
    // Convert ISO strings to datetime-local format
    const start = new Date(suggestedStart);
    const end = new Date(suggestedEnd);
    setStartTime(start.toISOString().slice(0, 16));
    setEndTime(end.toISOString().slice(0, 16));
    setServerConflicts([]);
    setNextAvailableStart(null);
    setNextAvailableEnd(null);
    setError(null);
  };

  const handleClose = () => {
    setResourceId('');
    setStartTime('');
    setEndTime('');
    setError(null);
    setCompatWarning(null);
    setServerConflicts([]);
    setNextAvailableStart(null);
    setNextAvailableEnd(null);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Schedule Operation" disableClose={submitting} className="w-full max-w-lg mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-800">
          <h2 className="text-xl font-semibold text-white">Schedule Operation</h2>
          <button
            onClick={handleClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {/* Operation info */}
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-white">
              <span className="font-medium">{operation?.sequence}:</span>
              <span>{operation?.operation_code}</span>
              {operation?.operation_name && (
                <span className="text-gray-400">({operation.operation_name})</span>
              )}
            </div>
            <div className="text-sm text-gray-500">
              Production Order: {productionOrder?.code}
            </div>
            <div className="text-sm text-gray-500">
              Estimated Duration: {formatDuration(estimatedMinutes)}
            </div>
          </div>

          <hr className="border-gray-800" />

          {/* Resource selector */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Resource <span className="text-red-400">*</span>
            </label>
            <select
              value={resourceId}
              onChange={(e) => setResourceId(e.target.value)}
              disabled={loadingResources}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">
                {loadingResources ? 'Loading...' : 'Select a resource...'}
              </option>
              {resources.map((resource) => (
                <option key={resource.id} value={resource.id}>
                  {resource.code} - {resource.name}
                </option>
              ))}
            </select>
            {resources.length === 0 && !loadingResources && (
              <p className="text-xs text-gray-500 mt-1">
                No resources available for this work center
              </p>
            )}
          </div>

          {/* Start time */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              Start Time <span className="text-red-400">*</span>
            </label>
            <input
              type="datetime-local"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {/* End time (auto-calculated) */}
          <div>
            <label className="block text-sm font-medium text-gray-400 mb-2">
              End Time
              <span className="text-gray-600 font-normal ml-2">(auto-calculated)</span>
            </label>
            <input
              type="datetime-local"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>

          {/* Compatibility warning */}
          <CompatibilityWarning reason={compatWarning} />

          {/* Conflict alert (live check) */}
          {checking ? (
            <div className="text-sm text-gray-500 flex items-center gap-2">
              <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-500"></div>
              Checking for conflicts...
            </div>
          ) : (
            <ConflictAlert
              conflicts={conflicts?.length > 0 ? conflicts : serverConflicts}
              nextAvailableStart={nextAvailableStart}
              nextAvailableEnd={nextAvailableEnd}
              onUseSlot={handleUseSuggestedSlot}
            />
          )}

          {/* Error message */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3">
              <p className="text-red-400 text-sm">{error}</p>
            </div>
          )}

          <hr className="border-gray-800" />

          {/* Actions */}
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting || hasConflicts || !!compatWarning || !resourceId || !startTime}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {submitting ? 'Scheduling...' : 'Schedule'}
            </button>
          </div>
        </form>
    </Modal>
  );
}
