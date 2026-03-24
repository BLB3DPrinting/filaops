/**
 * VariantMatrixModal - View and manage variant families for a template item.
 *
 * Shows a 2D grid of material × color combinations. Cells that already have a
 * variant show a green checkmark; available combos are checkboxes; unavailable
 * combos show a dash. Supports bulk-create and per-variant delete.
 */
import { useState, useEffect, useCallback } from 'react';
import Modal from '../Modal';
import ConfirmDialog from '../ConfirmDialog';
import { useToast } from '../Toast';
import { useApi } from '../../hooks/useApi';
import { useFormatCurrency } from '../../hooks/useFormatCurrency';

export default function VariantMatrixModal({ isOpen, onClose, item, onSuccess }) {
  const api = useApi();
  const toast = useToast();
  const formatCurrency = useFormatCurrency();
  const [matrixData, setMatrixData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [selectedCombos, setSelectedCombos] = useState(new Set()); // "mtId-colorId"
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState(null); // variantId pending confirm
  const [syncing, setSyncing] = useState(false);

  const fetchMatrix = useCallback(async () => {
    if (!item?.id) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(`/api/v1/items/${item.id}/variant-matrix`);
      setMatrixData(data);
      setError(null);
    } catch (err) {
      toast.error(err.message);
      setError('Failed to load variant matrix');
    } finally {
      setLoading(false);
    }
  }, [item?.id, api, toast]);

  useEffect(() => {
    if (isOpen) {
      setSelectedCombos(new Set());
      fetchMatrix();
    } else {
      setMatrixData(null);
    }
  }, [isOpen, fetchMatrix]);

  // ── Derived grid data ──────────────────────────────────────────────────────

  const uniqueMaterials = matrixData
    ? [...matrixData.available_combos
        .reduce((map, c) => {
          if (!map.has(c.material_type_id)) {
            map.set(c.material_type_id, { id: c.material_type_id, code: c.material_type_code, name: c.material_type_name });
          }
          return map;
        }, new Map())
        .values()]
    : [];

  const uniqueColors = matrixData
    ? [...matrixData.available_combos
        .reduce((map, c) => {
          if (!map.has(c.color_id)) {
            map.set(c.color_id, { id: c.color_id, code: c.color_code, name: c.color_name, hex: c.color_hex });
          }
          return map;
        }, new Map())
        .values()]
    : [];

  // Quick lookup: "mtId-colorId" → combo object
  const comboMap = matrixData
    ? Object.fromEntries(
        matrixData.available_combos.map((c) => [`${c.material_type_id}-${c.color_id}`, c])
      )
    : {};

  // ── Handlers ──────────────────────────────────────────────────────────────

  const toggleCombo = (mtId, colorId) => {
    const key = `${mtId}-${colorId}`;
    setSelectedCombos((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleBulkCreate = async () => {
    if (selectedCombos.size === 0 || creating) return;
    setCreating(true);
    try {
      const selections = [...selectedCombos].map((key) => {
        const [material_type_id, color_id] = key.split('-').map(Number);
        return { material_type_id, color_id };
      });
      const result = await api.post(`/api/v1/items/${item.id}/variants/bulk`, { selections });
      toast.success(`Created ${result.created?.length ?? selections.length} variant(s)`);
      setSelectedCombos(new Set());
      fetchMatrix();
      onSuccess?.();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setCreating(false);
    }
  };

  const handleSyncRouting = async () => {
    setSyncing(true);
    try {
      const result = await api.post(`/api/v1/items/${item.id}/variants/sync-routing`);
      if (result.errors?.length) {
        toast.error(`Synced ${result.synced}/${result.total} — ${result.errors.length} error(s)`);
      } else {
        toast.success(`Routing synced to ${result.synced} variant${result.synced !== 1 ? 's' : ''}`);
      }
      fetchMatrix();
      onSuccess?.();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSyncing(false);
    }
  };

  const handleDeleteVariant = async () => {
    if (!deletingId) return;
    try {
      await api.del(`/api/v1/items/${item.id}/variants/${deletingId}`);
      toast.success('Variant deleted');
      setDeletingId(null);
      setSelectedCombos(new Set());
      fetchMatrix();
      onSuccess?.();
    } catch (err) {
      toast.error(err.message);
      setDeletingId(null);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const hasVariableMatls = matrixData?.template?.variable_material_ids?.length > 0;
  const variantCount = matrixData?.variants?.length ?? 0;

  return (
    <>
      <Modal
        isOpen={isOpen}
        onClose={onClose}
        title="Variant Matrix"
        className="w-full max-w-5xl max-h-[90vh] flex flex-col"
      >
        <div className="flex flex-col overflow-hidden" style={{ maxHeight: '90vh' }}>
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-gray-700 flex-shrink-0">
            <div>
              <div className="flex items-center gap-3">
                <h2 className="text-xl font-bold text-white">Variant Matrix</h2>
                {matrixData && (
                  <span className="px-2 py-0.5 rounded-full text-xs bg-purple-500/20 text-purple-400 border border-purple-500/30">
                    {variantCount} variant{variantCount !== 1 ? 's' : ''}
                  </span>
                )}
                {variantCount > 0 && (
                  <button
                    onClick={handleSyncRouting}
                    disabled={syncing}
                    title="Push template routing changes (times, work centers, operations) to all variants. Material substitutions are preserved."
                    className="px-3 py-1 text-xs rounded border border-blue-500/30 bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {syncing ? 'Syncing…' : 'Sync Routing'}
                  </button>
                )}
              </div>
              {matrixData && (
                <p className="text-sm text-gray-400 mt-1">
                  <span className="font-mono text-gray-300">{matrixData.template.sku}</span>
                  {' — '}{matrixData.template.name}
                </p>
              )}
            </div>
            <button onClick={onClose} className="text-gray-400 hover:text-white">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="overflow-y-auto flex-1 p-6 space-y-6">
            {loading && (
              <div className="text-center py-8 text-gray-400">Loading matrix...</div>
            )}

            {!loading && error && !matrixData && (
              <div className="p-8 text-center">
                <p className="text-red-400 mb-4">{error}</p>
                <button onClick={fetchMatrix} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded text-sm">
                  Retry
                </button>
              </div>
            )}

            {!loading && matrixData && (
              <>
                {/* Warning: no variable materials */}
                {!hasVariableMatls && (
                  <div className="p-4 bg-yellow-500/10 border border-yellow-500/30 rounded-lg text-yellow-300 text-sm">
                    <span className="font-semibold">No variable materials configured.</span>{' '}
                    Open the Routing Editor for this item and mark at least one material as{' '}
                    <span className="font-mono">Variable</span> before creating variants.
                  </div>
                )}

                {/* Combo Grid */}
                {hasVariableMatls && uniqueMaterials.length === 0 && uniqueColors.length === 0 && (
                  <div className="p-6 text-center text-gray-400">
                    <p>No available material/color combinations found.</p>
                    <p className="text-sm mt-1">Ensure your catalog has MaterialColor entries for variable material types.</p>
                  </div>
                )}

                {uniqueMaterials.length > 0 && uniqueColors.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-300 mb-3">Available Combinations</h3>
                    <div className="overflow-x-auto">
                      <table className="text-sm border-collapse">
                        <thead>
                          <tr>
                            <th className="p-2 text-left text-gray-500 text-xs font-normal w-32">Material \ Color</th>
                            {uniqueColors.map((color) => (
                              <th key={color.id} className="p-2 text-center min-w-[80px]">
                                <div className="flex flex-col items-center gap-1">
                                  <span
                                    className="w-5 h-5 rounded-full border border-gray-600 inline-block"
                                    style={{ backgroundColor: color.hex || '#888' }}
                                    title={color.hex}
                                  />
                                  <span className="text-xs text-gray-300">{color.code}</span>
                                </div>
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {uniqueMaterials.map((mat) => (
                            <tr key={mat.id} className="border-t border-gray-800">
                              <td className="p-2 text-gray-300 text-xs">
                                <div>{mat.code}</div>
                                <div className="text-gray-500">{mat.name}</div>
                              </td>
                              {uniqueColors.map((color) => {
                                const key = `${mat.id}-${color.id}`;
                                const combo = comboMap[key];
                                if (!combo) {
                                  return (
                                    <td key={color.id} className="p-2 text-center text-gray-600">—</td>
                                  );
                                }
                                if (combo.already_exists) {
                                  const variant = matrixData.variants.find((v) => v.id === combo.variant_id);
                                  return (
                                    <td key={color.id} className="p-2 text-center">
                                      <span
                                        className="inline-flex items-center justify-center w-7 h-7 rounded bg-green-500/20 text-green-400 border border-green-500/30 cursor-default"
                                        title={variant ? `${variant.sku} — ${variant.name}` : 'Variant exists'}
                                      >
                                        ✓
                                      </span>
                                    </td>
                                  );
                                }
                                return (
                                  <td key={color.id} className="p-2 text-center">
                                    <input
                                      type="checkbox"
                                      checked={selectedCombos.has(key)}
                                      onChange={() => toggleCombo(mat.id, color.id)}
                                      className="rounded border-gray-600 bg-gray-800 text-blue-500 focus:ring-blue-500"
                                    />
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    <div className="mt-3">
                      <button
                        onClick={handleBulkCreate}
                        disabled={selectedCombos.size === 0 || creating}
                        className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
                      >
                        {creating ? 'Creating...' : `Create ${selectedCombos.size} variant${selectedCombos.size !== 1 ? 's' : ''}`}
                      </button>
                    </div>
                  </div>
                )}

                {/* Existing Variants Table */}
                {variantCount > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-300 mb-3">Existing Variants</h3>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead className="bg-gray-800/50">
                          <tr>
                            <th className="text-left py-2 px-3 text-xs font-medium text-gray-400 uppercase">SKU</th>
                            <th className="text-left py-2 px-3 text-xs font-medium text-gray-400 uppercase">Color</th>
                            <th className="text-left py-2 px-3 text-xs font-medium text-gray-400 uppercase">Material</th>
                            <th className="text-right py-2 px-3 text-xs font-medium text-gray-400 uppercase">Std Cost</th>
                            <th className="text-right py-2 px-3 text-xs font-medium text-gray-400 uppercase">On Hand</th>
                            <th className="text-center py-2 px-3 text-xs font-medium text-gray-400 uppercase">Status</th>
                            <th className="py-2 px-3"></th>
                          </tr>
                        </thead>
                        <tbody>
                          {matrixData.variants.map((v) => (
                            <tr key={v.id} className="border-t border-gray-800 hover:bg-gray-800/30">
                              <td className="py-2 px-3 font-mono text-gray-300">{v.sku}</td>
                              <td className="py-2 px-3">
                                <div className="flex items-center gap-2">
                                  <span
                                    className="w-4 h-4 rounded-full inline-block border border-gray-600 flex-shrink-0"
                                    style={{ backgroundColor: v.color_hex || '#888' }}
                                  />
                                  <span className="text-gray-300">{v.color_code}</span>
                                </div>
                              </td>
                              <td className="py-2 px-3 text-gray-400">{v.material_type_code}</td>
                              <td className="py-2 px-3 text-right text-gray-400">
                                {v.standard_cost != null ? formatCurrency(v.standard_cost) : '—'}
                              </td>
                              <td className="py-2 px-3 text-right text-gray-300">
                                {v.on_hand_qty != null
                                  ? <>
                                      {parseFloat(v.on_hand_qty).toLocaleString()}
                                      {v.inventory_uom && <span className="text-gray-500 text-xs ml-1">{v.inventory_uom}</span>}
                                    </>
                                  : '—'}
                              </td>
                              <td className="py-2 px-3 text-center">
                                <span className={`px-2 py-0.5 rounded-full text-xs ${v.active ? 'bg-green-500/20 text-green-400' : 'bg-gray-500/20 text-gray-400'}`}>
                                  {v.active ? 'Active' : 'Inactive'}
                                </span>
                              </td>
                              <td className="py-2 px-3 text-right">
                                <button
                                  onClick={() => setDeletingId(v.id)}
                                  className="text-red-400 hover:text-red-300 text-xs px-2 py-1 rounded hover:bg-red-500/10"
                                  title="Delete variant"
                                >
                                  Delete
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={!!deletingId}
        title="Delete Variant"
        message="This variant will be permanently deleted. Any inventory or order lines referencing it may be affected."
        confirmLabel="Delete Variant"
        confirmVariant="danger"
        onConfirm={handleDeleteVariant}
        onCancel={() => setDeletingId(null)}
      />
    </>
  );
}
