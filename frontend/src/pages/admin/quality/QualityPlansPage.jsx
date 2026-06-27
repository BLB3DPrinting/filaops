import { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { useApi } from "../../../hooks/useApi";
import { useToast } from "../../../components/Toast";
import Modal from "../../../components/Modal";
import QualityPlanEditor from "../../../components/QualityPlanEditor";

/**
 * QualityPlansPage — manage per-product (and template) quality plans. PR-5b (#784).
 *
 * Plans configure WHAT to inspect; they drive the QC measurement form when the
 * company Quality mode is "full" (see the dial in System Settings). They are
 * harmless to author in any mode — a banner explains when they take effect.
 */
export default function QualityPlansPage() {
  const api = useApi();
  const toast = useToast();

  const [plans, setPlans] = useState([]);
  const [productLabels, setProductLabels] = useState({});
  const [policy, setPolicy] = useState(null);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const [editing, setEditing] = useState(null); // {} = new, plan = edit, null = closed
  const [confirmPlan, setConfirmPlan] = useState(null);
  const [deactivating, setDeactivating] = useState(false);

  const fetchPlans = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(
        `/api/v1/quality-plans?include_inactive=${includeInactive}`
      );
      const list = Array.isArray(data) ? data : data.items || [];
      setPlans(list);

      // Resolve product labels for product-scoped plans (best effort).
      const ids = [
        ...new Set(
          list.filter((p) => p.product_id != null).map((p) => p.product_id)
        ),
      ];
      if (ids.length) {
        const settled = await Promise.allSettled(
          ids.map((id) => api.get(`/api/v1/items/${id}`))
        );
        setProductLabels((prev) => {
          const next = { ...prev };
          settled.forEach((r, i) => {
            if (r.status === "fulfilled") {
              next[ids[i]] = `${r.value.sku} — ${r.value.name}`;
            }
          });
          return next;
        });
      }
    } catch (err) {
      setError(err?.message || "Failed to load quality plans.");
    } finally {
      setLoading(false);
    }
  }, [api, includeInactive]);

  useEffect(() => {
    fetchPlans();
  }, [fetchPlans]);

  useEffect(() => {
    let active = true;
    api
      .get("/api/v1/quality/policy")
      .then((p) => {
        if (active) setPolicy(p);
      })
      .catch(() => {
        /* policy banner is informational; ignore failures */
      });
    return () => {
      active = false;
    };
  }, [api]);

  const handleDeactivate = async () => {
    if (!confirmPlan) return;
    setDeactivating(true);
    try {
      await api.del(`/api/v1/quality-plans/${confirmPlan.id}`);
      toast.success("Quality plan deactivated");
      setConfirmPlan(null);
      fetchPlans();
    } catch (err) {
      toast.error(err?.message || "Failed to deactivate plan");
    } finally {
      setDeactivating(false);
    }
  };

  const scopeLabel = (p) =>
    p.is_template
      ? "Template"
      : productLabels[p.product_id] || `Product #${p.product_id}`;

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">
            Quality Plans
          </h1>
          <p className="text-sm text-[var(--text-muted)] mt-1">
            Define the characteristics inspected for a product or as a reusable
            template.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setEditing({})}
          className="px-4 py-2 rounded-md text-sm font-medium bg-cyan-600 text-white hover:bg-cyan-500"
        >
          + New plan
        </button>
      </div>

      {/* Mode banner — plans only drive inspection in "full" mode */}
      {policy && !policy.plan_driven && (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg p-3 text-amber-300 text-sm">
          Quality mode is{" "}
          <span className="font-semibold">{policy.mode}</span>. Plans drive the
          inspection form only in <span className="font-semibold">Full</span>{" "}
          mode — you can author them now and switch on{" "}
          <Link to="/admin/settings" className="underline">
            System Settings
          </Link>{" "}
          when ready.
        </div>
      )}

      {/* Controls */}
      <div className="flex items-center justify-between">
        <label className="inline-flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={includeInactive}
            onChange={(e) => setIncludeInactive(e.target.checked)}
            className="rounded border-[var(--border-subtle)]"
          />
          Show inactive
        </label>
        <span className="text-xs text-[var(--text-muted)]">
          {plans.length} plan{plans.length === 1 ? "" : "s"}
        </span>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-red-400 text-sm">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-[var(--bg-card)] rounded-lg border border-[var(--border-subtle)] overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-[var(--text-muted)] text-sm">
            Loading…
          </div>
        ) : plans.length === 0 ? (
          <div className="p-8 text-center text-[var(--text-muted)] text-sm">
            No quality plans yet. Create one to start inspecting against a spec.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border-subtle)] text-left">
                  <th className="px-4 py-2 text-[var(--text-muted)] font-medium">
                    Code
                  </th>
                  <th className="px-4 py-2 text-[var(--text-muted)] font-medium">
                    Name
                  </th>
                  <th className="px-4 py-2 text-[var(--text-muted)] font-medium">
                    Scope
                  </th>
                  <th className="px-4 py-2 text-[var(--text-muted)] font-medium">
                    Rev
                  </th>
                  <th className="px-4 py-2 text-[var(--text-muted)] font-medium text-right">
                    Characteristics
                  </th>
                  <th className="px-4 py-2 text-[var(--text-muted)] font-medium">
                    Status
                  </th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border-subtle)]">
                {plans.map((p) => (
                  <tr key={p.id} className="hover:bg-[var(--bg-secondary)]">
                    <td className="px-4 py-2 font-mono text-[var(--text-primary)]">
                      {p.code}
                    </td>
                    <td className="px-4 py-2 text-[var(--text-primary)]">
                      {p.name}
                    </td>
                    <td className="px-4 py-2">
                      {p.is_template ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-purple-500/20 text-purple-300 border border-purple-500/30">
                          Template
                        </span>
                      ) : (
                        <span className="text-[var(--text-secondary)]">
                          {scopeLabel(p)}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-[var(--text-secondary)]">
                      v{p.version} · {p.revision}
                    </td>
                    <td className="px-4 py-2 text-right text-[var(--text-secondary)]">
                      {p.characteristics?.length ?? 0}
                    </td>
                    <td className="px-4 py-2">
                      {p.is_active ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-green-500/20 text-green-400 border border-green-500/30">
                          Active
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-500/20 text-gray-400 border border-gray-500/30">
                          Inactive
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2 text-right whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => setEditing(p)}
                        className="text-xs px-2 py-1 rounded-md text-cyan-400 hover:bg-[var(--bg-secondary)]"
                      >
                        Edit
                      </button>
                      {p.is_active && (
                        <button
                          type="button"
                          onClick={() => setConfirmPlan(p)}
                          className="text-xs px-2 py-1 rounded-md text-[var(--text-muted)] hover:text-red-400"
                        >
                          Deactivate
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {editing && (
        <QualityPlanEditor
          plan={editing.id ? editing : null}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            fetchPlans();
          }}
        />
      )}

      {confirmPlan && (
        <Modal
          isOpen
          onClose={() => !deactivating && setConfirmPlan(null)}
          disableClose={deactivating}
          title="Deactivate quality plan"
          className="w-full max-w-md"
        >
          <div className="p-6 space-y-4">
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">
              Deactivate plan?
            </h2>
            <p className="text-sm text-[var(--text-secondary)]">
              <span className="font-mono">{confirmPlan.code}</span> —{" "}
              {confirmPlan.name} will be hidden from active lists. You can
              reactivate it later by editing it.
            </p>
            <div className="flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setConfirmPlan(null)}
                disabled={deactivating}
                className="px-4 py-2 rounded-md text-sm text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeactivate}
                disabled={deactivating}
                className="px-4 py-2 rounded-md text-sm font-medium bg-red-600 text-white hover:bg-red-500 disabled:opacity-50"
              >
                {deactivating ? "Deactivating…" : "Deactivate"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
