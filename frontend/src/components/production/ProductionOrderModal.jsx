import { useState, useEffect } from 'react';
import { API_URL } from '../../config/api';
import { formatDuration, formatDate } from '../../utils/formatting';
import { PRODUCTION_ORDER_BADGE_CONFIGS } from '../../lib/statusColors.js';
import Modal from '../Modal';
import OperationCard from './OperationCard';
import SkipOperationModal from './SkipOperationModal';
import ShortageModal from './ShortageModal';

/**
 * Status badge component
 */
function StatusBadge({ status }) {
  const config = PRODUCTION_ORDER_BADGE_CONFIGS[status] || PRODUCTION_ORDER_BADGE_CONFIGS.draft;
  return (
    <span className={`px-2 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text}`}>
      {config.label}
    </span>
  );
}

/**
 * Parse datetime string, ensuring UTC interpretation
 * Backend sends UTC times without 'Z' suffix
 */
function parseDateTime(datetime) {
  if (!datetime) return null;
  if (datetime instanceof Date) return datetime;

  // If string doesn't have timezone info, assume UTC and add 'Z'
  let dateStr = datetime;
  if (typeof dateStr === 'string' && !dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    dateStr = dateStr + 'Z';
  }
  return new Date(dateStr);
}

/**
 * ProductionOrderModal - Production execution hub
 *
 * Shows production order details with all operations.
 * Allows operators to Schedule, Start, Complete, and Skip operations.
 */
export default function ProductionOrderModal({
  productionOrder,
  onClose,
  onUpdated,
}) {
  const [operations, setOperations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState(null);
  const [expandedOpId, setExpandedOpId] = useState(null);
  const [notes, setNotes] = useState('');
  const [notesSaving, setNotesSaving] = useState(false);

  // Skip modal state
  const [skipModalOpen, setSkipModalOpen] = useState(false);
  const [operationToSkip, setOperationToSkip] = useState(null);

  // Shortage modal state
  const [shortageModalOpen, setShortageModalOpen] = useState(false);
  const [shortageInfo, setShortageInfo] = useState(null);

  const [refreshRoutingLoading, setRefreshRoutingLoading] = useState(false);

  // Spool assignment state
  const [assignedSpools, setAssignedSpools] = useState([]);
  const [spoolPickerFor, setSpoolPickerFor] = useState(null); // component_id of material being assigned
  const [availableSpools, setAvailableSpools] = useState([]);
  const [spoolLoading, setSpoolLoading] = useState(false);

  // Schedule modal state (for pending ops)
  const [scheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [operationToSchedule, setOperationToSchedule] = useState(null);
  const [workCenters, setWorkCenters] = useState([]);
  const [resources, setResources] = useState([]);
  const [selectedWorkCenter, setSelectedWorkCenter] = useState(null);
  const [selectedResource, setSelectedResource] = useState(null);
  const [scheduledStart, setScheduledStart] = useState('');
  const [suggestedSlot, setSuggestedSlot] = useState(null); // { start, end } when conflict occurs

  // Fetch operations on mount
  useEffect(() => {
    if (productionOrder?.id) {
      fetchOperations();
      fetchAssignedSpools();
      setNotes(productionOrder.notes || '');
    }
  }, [productionOrder?.id]);

  // Fetch work centers for scheduling
  useEffect(() => {
    fetchWorkCenters();
  }, []);

  // Fetch resources when work center changes
  useEffect(() => {
    if (selectedWorkCenter) {
      fetchResources(selectedWorkCenter);
    } else {
      setResources([]);
    }
  }, [selectedWorkCenter]);

  const fetchAssignedSpools = async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/spools`,
        { credentials: "include" }
      );
      if (res.ok) {
        setAssignedSpools(await res.json());
      }
    } catch { /* ignore */ }
  };

  const openSpoolPicker = async (componentId) => {
    setSpoolPickerFor(componentId);
    setAvailableSpools([]);
    setSpoolLoading(true);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/spools/?product_id=${componentId}&status=active`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        setAvailableSpools(data.items || []);
      }
    } catch { /* ignore */ }
    setSpoolLoading(false);
  };

  const assignSpool = async (spoolId) => {
    if (spoolLoading) return;
    try {
      setSpoolLoading(true);
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/spools/${spoolId}`,
        { method: "POST", credentials: "include" }
      );
      if (res.ok) {
        await fetchAssignedSpools();
        setSpoolPickerFor(null);
      }
    } catch { /* ignore */ }
    setSpoolLoading(false);
  };

  const fetchOperations = async () => {
    try {
      setLoading(true);
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/operations`,
        { credentials: "include" }
      );
      if (res.ok) {
        const data = await res.json();
        const ops = data.operations || data || [];
        setOperations(ops);

        // Auto-expand running operation
        const runningOp = ops.find((op) => op.status === 'running');
        if (runningOp) {
          setExpandedOpId(runningOp.id);
        }
      }
    } catch { // err unused
      setError('Failed to load operations');
    } finally {
      setLoading(false);
    }
  };

  const fetchWorkCenters = async () => {
    try {
      const res = await fetch(
        `${API_URL}/api/v1/work-centers/?center_type=machine&active_only=true`,
        { credentials: "include" }
      );
      if (res.ok) {
        setWorkCenters(await res.json());
      }
    } catch {
      // Non-critical
    }
  };

  const fetchResources = async (workCenterId) => {
    try {
      const [resourcesRes, printersRes] = await Promise.all([
        fetch(
          `${API_URL}/api/v1/work-centers/${workCenterId}/resources?active_only=true`,
          { credentials: "include" }
        ),
        fetch(
          `${API_URL}/api/v1/work-centers/${workCenterId}/printers?active_only=true`,
          { credentials: "include" }
        ),
      ]);

      const allResources = [];

      if (resourcesRes.ok) {
        const data = await resourcesRes.json();
        allResources.push(
          ...data.filter((r) => r.status === 'available' || r.status === 'idle')
        );
      }

      if (printersRes.ok) {
        const printers = await printersRes.json();
        // Get existing resource codes to avoid duplicates
        const existingCodes = new Set(allResources.map((r) => r.code));
        allResources.push(
          ...printers
            .filter((p) => p.status === 'idle' || p.status === 'available' || !p.status)
            .filter((p) => !existingCodes.has(p.code)) // Skip if already in resources
            .map((p) => ({
              id: p.id,
              code: p.code,
              name: p.name,
              status: p.status || 'available',
              is_printer: true,
            }))
        );
      }

      setResources(allResources);
    } catch {
      // Non-critical
    }
  };

  // Calculate max qty for current operation (from previous op or PO qty)
  const getMaxQtyForOperation = (opIndex) => {
    if (opIndex === 0) {
      return productionOrder.quantity_ordered || 0;
    }
    const prevOp = operations[opIndex - 1];
    if (prevOp?.status === 'complete') {
      return prevOp.quantity_completed || 0;
    }
    if (prevOp?.status === 'skipped') {
      // Inherit from the one before
      return getMaxQtyForOperation(opIndex - 1);
    }
    return productionOrder.quantity_ordered || 0;
  };

  // Handle schedule operation
  const handleSchedule = (operation) => {
    setOperationToSchedule(operation);
    setSelectedWorkCenter(operation.work_center_id || null);
    const now = new Date();
    now.setHours(now.getHours() + 1);
    setScheduledStart(now.toISOString().slice(0, 16));
    setScheduleModalOpen(true);
  };

  const submitSchedule = async () => {
    if (!operationToSchedule || !selectedResource) return;

    setActionLoading(true);
    setError(null);
    setSuggestedSlot(null);

    try {
      // Calculate end time from operation planned times
      const plannedMinutes =
        (parseFloat(operationToSchedule.planned_setup_minutes) || 0) +
        (parseFloat(operationToSchedule.planned_run_minutes) || 0);
      const start = new Date(scheduledStart);
      const end = new Date(start.getTime() + plannedMinutes * 60000);

      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/operations/${operationToSchedule.id}/schedule`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            resource_id: selectedResource.id,
            scheduled_start: start.toISOString(),
            scheduled_end: end.toISOString(),
            is_printer: selectedResource.is_printer || false,
          }),
        }
      );

      if (!res.ok) {
        const data = await res.json();

        // If conflict (409), fetch next available slot and suggest it
        if (res.status === 409) {
          try {
            const slotRes = await fetch(
              `${API_URL}/api/v1/production-orders/resources/next-available`,
              {
                method: 'POST',
                credentials: 'include',
                headers: {
                  'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                  resource_id: selectedResource.id,
                  duration_minutes: Math.ceil(plannedMinutes) || 60,
                  is_printer: selectedResource.is_printer || false,
                  after: start.toISOString(),
                }),
              }
            );
            if (slotRes.ok) {
              const slot = await slotRes.json();
              setSuggestedSlot({
                start: slot.next_available,
                end: slot.suggested_end,
              });
              setError('Scheduling conflict. See suggested time below.');
              return;
            }
          } catch { // err unused
            // If we can't get suggestion, fall through to regular error
          }
        }

        throw new Error(data.detail || 'Failed to schedule operation');
      }

      setScheduleModalOpen(false);
      setOperationToSchedule(null);
      setSelectedResource(null);
      setSuggestedSlot(null);
      fetchOperations();
      onUpdated?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Apply suggested time slot
  const applySuggestedSlot = () => {
    if (suggestedSlot) {
      const suggested = new Date(suggestedSlot.start);
      setScheduledStart(suggested.toISOString().slice(0, 16));
      setSuggestedSlot(null);
      setError(null);
    }
  };

  // Handle start operation
  const handleStart = async (operation) => {
    setActionLoading(true);
    setError(null);

    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/operations/${operation.id}/start`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({}),
        }
      );

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start operation');
      }

      // Refresh operations first, then notify parent
      await fetchOperations();
      onUpdated?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle complete operation
  const handleComplete = async (operationId, qtyGood, qtyBad, scrapReason = null) => {
    setActionLoading(true);
    setError(null);

    try {
      const payload = {
        quantity_completed: qtyGood,
        quantity_scrapped: qtyBad,
      };
      if (scrapReason) {
        payload.scrap_reason = scrapReason;
      }

      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/operations/${operationId}/complete`,
        {
          method: 'POST',
          credentials: 'include',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        }
      );

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to complete operation');
      }

      const data = await res.json();

      // Check if PO is now short - show shortage modal
      if (data.production_order?.status === 'short' && data.production_order?.quantity_short > 0) {
        setShortageInfo({
          poCode: data.production_order.code,
          quantityOrdered: data.production_order.quantity_ordered,
          quantityCompleted: data.production_order.quantity_completed,
          quantityShort: data.production_order.quantity_short,
          salesOrderId: data.production_order.sales_order_id,
          salesOrderCode: data.production_order.sales_order_code,
          productId: productionOrder.product_id || productionOrder.product?.id,
        });
        setShortageModalOpen(true);
      }

      // Refresh operations first, then notify parent
      await fetchOperations();
      onUpdated?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  // Handle skip operation
  const handleSkip = (operation) => {
    setOperationToSkip(operation);
    setSkipModalOpen(true);
  };

  const onSkipped = () => {
    fetchOperations();
    onUpdated?.();
  };

  // Handle notes save
  const saveNotes = async () => {
    if (notes === productionOrder.notes) return;

    setNotesSaving(true);
    try {
      await fetch(`${API_URL}/api/v1/production-orders/${productionOrder.id}`, {
        method: 'PUT',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ notes }),
      });
      onUpdated?.();
    } catch {
      // Silent fail
    } finally {
      setNotesSaving(false);
    }
  };

  // Handle claim (assign current user to next operation)
  const handleClaim = async () => {
    const nextOp = operations.find(
      (op) => op.status === 'pending' || op.status === 'queued' || op.status === 'running'
    );
    if (!nextOp) return;

    // For now, just set operator_name - would need user context for real implementation
    // This is a placeholder - in production you'd get the current user from auth context
    alert('Claim functionality requires user authentication context');
  };

  // Refresh routing — re-snapshot the product's current active routing
  const handleRefreshRouting = async () => {
    if (refreshRoutingLoading) return;
    if (!window.confirm('Re-apply the current routing to this production order? Any pending operations will be replaced.')) return;
    setRefreshRoutingLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${API_URL}/api/v1/production-orders/${productionOrder.id}/refresh-routing`,
        { method: 'POST', credentials: 'include' }
      );
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        const detail = data?.detail;
        const message =
          typeof detail === 'string'
            ? detail
            : Array.isArray(detail)
              ? detail.map((d) => (typeof d === 'string' ? d : d?.msg)).filter(Boolean).join('; ')
              : detail
                ? JSON.stringify(detail)
                : 'Failed to refresh routing';
        throw new Error(message);
      }
      await fetchOperations();
      onUpdated?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setRefreshRoutingLoading(false);
    }
  };

  // Calculate totals
  const totalMinutes = operations.reduce(
    (sum, op) =>
      sum +
      (parseFloat(op.planned_setup_minutes) || 0) +
      (parseFloat(op.planned_run_minutes) || 0),
    0
  );

  const completedOps = operations.filter((op) => op.status === 'complete').length;
  const runningOps = operations.filter((op) => op.status === 'running').length;

  // Gather all materials
  const allMaterials = operations.flatMap((op) => op.materials || []);
  const materialsReady = allMaterials.filter(
    (m) => m.status === 'allocated' || m.status === 'consumed'
  ).length;
  const materialsBlocking = allMaterials.filter(
    (m) => m.status === 'unavailable' || m.status === 'pending'
  );

  if (!productionOrder) return null;

  const canRefreshRouting = ['draft', 'released', 'on_hold'].includes(productionOrder.status);

  return (
    <Modal isOpen={true} onClose={onClose} title={`Production Order ${productionOrder.code}`} className="w-full max-w-3xl mx-4 max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex justify-between items-start p-6 border-b border-gray-800">
          <div>
            <div className="flex items-center gap-3">
              <h2 className="text-xl font-bold text-white">{productionOrder.code}</h2>
              <StatusBadge status={productionOrder.status} />
            </div>
            <p className="text-gray-400 mt-1">
              {productionOrder.product_name || productionOrder.product?.name || 'Unknown Product'}
              <span className="text-gray-500"> × </span>
              <span className="text-white font-mono">
                {productionOrder.quantity_ordered}
              </span>
              {productionOrder.due_date && (
                <span className="text-gray-500 ml-3">
                  Due: {formatDate(productionOrder.due_date)}
                </span>
              )}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-2xl leading-none"
          >
            ×
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="mx-6 mt-4 bg-red-900/20 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* Content - Scrollable */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Summary stats */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="text-gray-500 text-xs">Operations</div>
              <div className="text-white font-medium">
                {completedOps}/{operations.length} complete
                {runningOps > 0 && (
                  <span className="text-purple-400 ml-1">({runningOps} running)</span>
                )}
              </div>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="text-gray-500 text-xs">Est. Duration</div>
              <div className="text-white font-medium font-mono">
                {formatDuration(totalMinutes)}
              </div>
            </div>
            <div className="bg-gray-800/50 rounded-lg p-3">
              <div className="text-gray-500 text-xs">Materials</div>
              <div
                className={`font-medium ${
                  materialsBlocking.length > 0 ? 'text-red-400' : 'text-green-400'
                }`}
              >
                {allMaterials.length > 0
                  ? `${materialsReady}/${allMaterials.length} ready`
                  : 'None required'}
              </div>
            </div>
          </div>

          {/* Operations */}
          <div>
            <h3 className="text-gray-400 text-sm font-medium mb-3">OPERATIONS</h3>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-purple-500"></div>
              </div>
            ) : operations.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-gray-500 mb-3">No operations defined for this order</p>
                {canRefreshRouting && (
                  <button
                    onClick={handleRefreshRouting}
                    disabled={refreshRoutingLoading}
                    className="px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded-lg transition-colors text-sm"
                  >
                    {refreshRoutingLoading ? 'Refreshing…' : 'Apply Routing Now'}
                  </button>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                {operations.map((op, idx) => (
                  <OperationCard
                    key={op.id}
                    operation={op}
                    maxQty={getMaxQtyForOperation(idx)}
                    expanded={expandedOpId === op.id}
                    onToggleExpand={() =>
                      setExpandedOpId(expandedOpId === op.id ? null : op.id)
                    }
                    onSchedule={handleSchedule}
                    onStart={handleStart}
                    onComplete={handleComplete}
                    onSkip={handleSkip}
                    loading={actionLoading}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Materials */}
          {allMaterials.length > 0 && (
            <div>
              <h3 className="text-gray-400 text-sm font-medium mb-3">MATERIALS</h3>
              <div className="bg-gray-800/30 rounded-lg p-4 space-y-2">
                {allMaterials.slice(0, 5).map((mat, idx) => {
                  const matSpool = assignedSpools.find(
                    (s) => s.product_id === mat.component_id
                  );
                  return (
                    <div key={idx} className="space-y-1">
                      <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-300">
                          {mat.component_name || mat.component_sku || 'Unknown'}
                          <span className="text-gray-500 ml-2">
                            × {mat.quantity_required} {mat.unit || ''}
                          </span>
                        </span>
                        <div className="flex items-center gap-2">
                          <span
                            className={
                              mat.status === 'consumed'
                                ? 'text-green-400'
                                : mat.status === 'allocated'
                                ? 'text-blue-400'
                                : 'text-red-400'
                            }
                          >
                            {mat.status}
                          </span>
                          {mat.component_id && (
                            <button
                              onClick={() => openSpoolPicker(mat.component_id)}
                              className="text-xs px-2 py-0.5 rounded bg-gray-700 hover:bg-gray-600 text-gray-300 transition-colors"
                              title="Assign spool for traceability (optional)"
                            >
                              {matSpool ? '🔗 ' + matSpool.spool_code : 'Assign Spool'}
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
                {allMaterials.length > 5 && (
                  <div className="text-gray-500 text-xs">
                    +{allMaterials.length - 5} more materials
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Spool Picker Dropdown */}
          {spoolPickerFor && (
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
              <div className="flex justify-between items-center mb-3">
                <h4 className="text-sm font-medium text-white">Select Spool</h4>
                <button
                  onClick={() => setSpoolPickerFor(null)}
                  className="text-gray-400 hover:text-white text-sm"
                >
                  ✕
                </button>
              </div>
              {spoolLoading ? (
                <div className="text-gray-400 text-sm">Loading spools…</div>
              ) : availableSpools.length === 0 ? (
                <div className="text-gray-500 text-sm">No active spools found for this material.</div>
              ) : (
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {availableSpools.map((spool) => (
                    <button
                      key={spool.id}
                      onClick={() => assignSpool(spool.id)}
                      disabled={spoolLoading}
                      className="w-full flex items-center justify-between px-3 py-2 rounded hover:bg-gray-700 text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <span className="text-white">{spool.spool_number}</span>
                      <span className="text-gray-400">
                        {(spool.current_weight_kg ?? 0).toFixed(2)} kg
                        {spool.supplier_lot_number && (
                          <span className="ml-2 text-gray-500">Lot: {spool.supplier_lot_number}</span>
                        )}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Assigned Spools Summary */}
          {assignedSpools.length > 0 && (
            <div>
              <h3 className="text-gray-400 text-sm font-medium mb-3">ASSIGNED SPOOLS</h3>
              <div className="bg-gray-800/30 rounded-lg p-4 space-y-1">
                {assignedSpools.map((s, idx) => (
                  <div key={idx} className="flex items-center justify-between text-sm">
                    <span className="text-gray-300">
                      {s.spool_code}
                      <span className="text-gray-500 ml-2">— {s.product_name}</span>
                    </span>
                    <span className="text-gray-400 text-xs">
                      {s.quantity_remaining != null ? `${s.quantity_remaining} kg remaining` : ''}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Notes */}
          <div>
            <h3 className="text-gray-400 text-sm font-medium mb-3">NOTES</h3>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={saveNotes}
              rows={3}
              placeholder="Add production notes..."
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white placeholder-gray-500 resize-none focus:border-blue-500 focus:outline-none"
            />
            {notesSaving && (
              <div className="text-gray-500 text-xs mt-1">Saving...</div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-between items-center p-6 border-t border-gray-800">
          <div className="flex gap-2">
            <button
              onClick={handleClaim}
              className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg transition-colors"
            >
              Claim for Me
            </button>
            {canRefreshRouting && (
              <button
                onClick={handleRefreshRouting}
                disabled={refreshRoutingLoading}
                className="px-4 py-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white rounded-lg transition-colors text-sm"
                title="Re-apply the product's current active routing to this order"
              >
                {refreshRoutingLoading ? 'Refreshing…' : 'Refresh Routing'}
              </button>
            )}
          </div>
          <button
            onClick={onClose}
            className="px-6 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
          >
            Close
          </button>
        </div>

      {/* Skip Modal */}
      <SkipOperationModal
        isOpen={skipModalOpen}
        onClose={() => {
          setSkipModalOpen(false);
          setOperationToSkip(null);
        }}
        operation={operationToSkip}
        productionOrderId={productionOrder.id}
        onSkipped={onSkipped}
      />

      {/* Schedule Modal */}
      {scheduleModalOpen && operationToSchedule && (
        <div className="fixed inset-0 z-60 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60"
            onClick={() => setScheduleModalOpen(false)}
          />
          <div className="relative bg-gray-900 border border-gray-700 rounded-xl w-full max-w-md mx-4 p-6 space-y-4">
            <h3 className="text-lg font-semibold text-white">Schedule Operation</h3>
            <p className="text-gray-400 text-sm">
              {operationToSchedule.operation_code || `Op ${operationToSchedule.sequence}`}
            </p>

            {/* Work Center */}
            <div>
              <label className="block text-sm text-gray-400 mb-1">Work Center</label>
              {operationToSchedule.work_center_id ? (
                // Operation has a defined work center - lock it
                <div className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white">
                  {workCenters.find((wc) => wc.id === operationToSchedule.work_center_id)?.name ||
                    operationToSchedule.work_center_name ||
                    `Work Center ${operationToSchedule.work_center_id}`}
                </div>
              ) : (
                // No work center defined - allow selection
                <select
                  value={selectedWorkCenter || ''}
                  onChange={(e) =>
                    setSelectedWorkCenter(e.target.value ? parseInt(e.target.value) : null)
                  }
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                >
                  <option value="">Select work center...</option>
                  {workCenters.map((wc) => (
                    <option key={wc.id} value={wc.id}>
                      {wc.code} - {wc.name}
                    </option>
                  ))}
                </select>
              )}
            </div>

            {/* Resource */}
            {selectedWorkCenter && (
              <div>
                <label className="block text-sm text-gray-400 mb-1">
                  Machine/Printer
                </label>
                <select
                  value={selectedResource?.id || ''}
                  onChange={(e) => {
                    const res = resources.find(
                      (r) => r.id === parseInt(e.target.value)
                    );
                    setSelectedResource(res || null);
                  }}
                  className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
                >
                  <option value="">Select machine...</option>
                  {resources.map((res) => (
                    <option key={res.id} value={res.id}>
                      {res.code} - {res.name}
                      {res.is_printer ? ' [Printer]' : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Start Time */}
            <div>
              <label className="block text-sm text-gray-400 mb-1">Start Time</label>
              <input
                type="datetime-local"
                value={scheduledStart}
                onChange={(e) => setScheduledStart(e.target.value)}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
              />
            </div>

            {/* Suggested Slot (shown after conflict) */}
            {suggestedSlot && (
              <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg p-3">
                <p className="text-blue-300 text-sm mb-2">
                  Next available slot: {parseDateTime(suggestedSlot.start).toLocaleString()}
                </p>
                <button
                  onClick={applySuggestedSlot}
                  className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 transition-colors"
                >
                  Use This Time
                </button>
              </div>
            )}

            {/* Actions */}
            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setScheduleModalOpen(false)}
                className="px-4 py-2 text-gray-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={submitSchedule}
                disabled={actionLoading || !selectedResource}
                className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {actionLoading ? 'Scheduling...' : 'Schedule'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Shortage Modal */}
      <ShortageModal
        isOpen={shortageModalOpen}
        onClose={() => {
          setShortageModalOpen(false);
          setShortageInfo(null);
        }}
        poCode={shortageInfo?.poCode}
        quantityOrdered={shortageInfo?.quantityOrdered}
        quantityCompleted={shortageInfo?.quantityCompleted}
        quantityShort={shortageInfo?.quantityShort}
        salesOrderId={shortageInfo?.salesOrderId}
        salesOrderCode={shortageInfo?.salesOrderCode}
        productId={shortageInfo?.productId}
        onReplacementCreated={() => {
          // Refresh the list and notify user
          onUpdated?.();
        }}
      />
    </Modal>
  );
}
