import { useCallback, useEffect, useState } from "react";
import { useApi } from "../../hooks/useApi";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";
import { useProInstaller } from "../../hooks/useProInstaller";
import { useToast } from "../../components/Toast";

/**
 * AdminLicense — license entry + current-state display.
 *
 * Unlike most admin pages, this one is intentionally NOT gated by
 * `useFeatureFlags().isPro`. It is the page that *enables* PRO, so it
 * must work before PRO is installed (Community-tier customers reach it
 * to activate).
 */
export default function AdminLicense() {
  const api = useApi();
  const toast = useToast();
  const { isPro } = useFeatureFlags();
  const { installState, startInstall, resetInstall } = useProInstaller();

  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [licenseKey, setLicenseKey] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const [deactivating, setDeactivating] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await api.get("/api/v1/system/license/info");
      setInfo(data);
      setLoadError(null);
    } catch (err) {
      setLoadError(err?.message || "Failed to load license info");
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleActivate = async (e) => {
    e?.preventDefault?.();
    const key = licenseKey.trim();
    if (!key) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const data = await api.post("/api/v1/system/license/activate", {
        license_key: key,
      });
      setInfo(data);
      setLicenseKey("");
      toast?.success?.(
        `Activated ${data.tier?.toUpperCase?.() || "PRO"} license. Restart Core to load PRO features.`,
      );
    } catch (err) {
      // Backend returns the most useful detail (e.g. "License key not found",
      // "Could not reach the license server"). Surface it directly.
      setSubmitError(err?.message || "Activation failed");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeactivate = async () => {
    if (!window.confirm(
      "Remove this license locally? Core will run as Community until you activate again. " +
      "Your data is preserved.",
    )) {
      return;
    }
    setDeactivating(true);
    try {
      await api.del("/api/v1/system/license/");
      await refresh();
      toast?.success?.("License removed locally. Restart Core to apply.");
    } catch (err) {
      toast?.error?.(err?.message || "Failed to deactivate");
    } finally {
      setDeactivating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="space-y-6">
        <Header />
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-4 text-red-400">
          {loadError}
        </div>
      </div>
    );
  }

  const isActivated = !!info?.activated;
  const tier = info?.tier || "community";
  const features = info?.features || [];
  // Show the install section only when the license is activated but PRO
  // hasn't been loaded into the running Python process. After restart,
  // useFeatureFlags().isPro flips to true and this block disappears.
  const needsInstall = isActivated && !isPro;

  return (
    <div className="space-y-6">
      <Header />

      <CurrentStateCard
        info={info}
        isActivated={isActivated}
        tier={tier}
        features={features}
        onDeactivate={handleDeactivate}
        deactivating={deactivating}
      />

      {needsInstall && (
        <ProInstallSection
          installState={installState}
          onInstall={startInstall}
          onReset={resetInstall}
        />
      )}

      {!isActivated && (
        <ActivateForm
          licenseKey={licenseKey}
          onChange={setLicenseKey}
          onSubmit={handleActivate}
          submitting={submitting}
          error={submitError}
        />
      )}
    </div>
  );
}

function Header() {
  return (
    <div>
      <h1 className="text-2xl font-bold text-white">License & PRO Activation</h1>
      <p className="text-gray-400 mt-1">
        Enter your FilaOps PRO license key to unlock Professional features. Need
        a license? Visit{" "}
        <a
          href="https://filaops.blb3dprinting.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="text-blue-400 hover:text-blue-300 underline"
        >
          filaops.blb3dprinting.com
        </a>
        .
      </p>
    </div>
  );
}

function CurrentStateCard({
  info,
  isActivated,
  tier,
  features,
  onDeactivate,
  deactivating,
}) {
  const tierBadge = isActivated
    ? {
        label: tier.toUpperCase(),
        classes: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
      }
    : {
        label: "COMMUNITY",
        classes: "bg-gray-500/15 text-gray-300 border-gray-500/30",
      };

  return (
    <div className="bg-gray-800/40 border border-gray-700 rounded-lg p-6 space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="text-xs text-gray-500 uppercase tracking-wide">
            Current Tier
          </div>
          <div
            className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-semibold border ${tierBadge.classes}`}
          >
            {tierBadge.label}
          </div>
        </div>
        {isActivated && (
          <button
            onClick={onDeactivate}
            disabled={deactivating}
            className="text-sm text-gray-400 hover:text-red-400 underline transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {deactivating ? "Removing…" : "Remove license"}
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
        <Field label="License key" value={info?.license_key || "—"} mono />
        <Field
          label="Status"
          value={isActivated ? "Active" : "Not activated"}
        />
        <Field
          label="Expires"
          value={info?.expires_at ? formatDate(info.expires_at) : isActivated ? "Perpetual" : "—"}
        />
        <Field
          label="Activated"
          value={info?.activated_at ? formatDate(info.activated_at) : "—"}
        />
      </div>

      {isActivated && features.length > 0 && (
        <div>
          <div className="text-xs text-gray-500 uppercase tracking-wide mb-2">
            Enabled Features ({features.length})
          </div>
          <div className="flex flex-wrap gap-2">
            {features.map((f) => (
              <span
                key={f}
                className="text-xs font-mono bg-gray-700/40 border border-gray-600/40 text-gray-300 px-2 py-1 rounded"
              >
                {f}
              </span>
            ))}
          </div>
        </div>
      )}

      {info?.install_uuid && (
        <div className="pt-3 border-t border-gray-700/50">
          <Field
            label="Install ID"
            value={info.install_uuid}
            mono
            hint="Stable identifier for this Core instance. Sent to the license server during activation."
          />
        </div>
      )}

      {isActivated && (
        <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg px-4 py-3 text-sm text-blue-200">
          <strong>Restart Core</strong> to load PRO features after activation
          changes.
        </div>
      )}
    </div>
  );
}

function ActivateForm({ licenseKey, onChange, onSubmit, submitting, error }) {
  const trimmed = licenseKey.trim();
  return (
    <form
      onSubmit={onSubmit}
      className="bg-gray-800/40 border border-gray-700 rounded-lg p-6 space-y-4"
    >
      <div>
        <label
          htmlFor="license-key-input"
          className="block text-sm font-medium text-gray-200 mb-2"
        >
          License Key
        </label>
        <input
          id="license-key-input"
          type="text"
          value={licenseKey}
          onChange={(e) => onChange(e.target.value)}
          placeholder="FILAOPS-PRO-..."
          autoComplete="off"
          autoCapitalize="off"
          spellCheck="false"
          disabled={submitting}
          className="w-full bg-gray-900/60 border border-gray-700 rounded-md px-3 py-2 text-sm text-white font-mono placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-50"
        />
        <p className="text-xs text-gray-500 mt-1">
          Pasted from your purchase confirmation email. Spaces are trimmed
          automatically.
        </p>
      </div>

      {error && (
        <div
          role="alert"
          className="bg-red-500/10 border border-red-500/30 rounded-md px-3 py-2 text-sm text-red-300"
        >
          {error}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting || trimmed.length === 0}
          className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 disabled:cursor-not-allowed text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
        >
          {submitting ? "Activating…" : "Activate"}
        </button>
        <span className="text-xs text-gray-500">
          Core will contact the license server to validate this key.
        </span>
      </div>
    </form>
  );
}

function ProInstallSection({ installState, onInstall, onReset }) {
  const { state, progress, error, installed_version: installedVersion } = installState;
  const isBusy = state === "downloading" || state === "verifying" || state === "installing";
  const isError = state === "error";
  const isDone = state === "restart_required";

  const stateLabel = {
    downloading: "Downloading PRO package…",
    verifying: "Verifying package integrity…",
    installing: "Installing PRO package…",
  }[state];

  return (
    <div
      data-testid="pro-install-section"
      className="bg-gray-800/40 border border-gray-700 rounded-lg p-6 space-y-4"
    >
      <div className="space-y-1">
        <div className="text-xs text-gray-500 uppercase tracking-wide">
          PRO Installation
        </div>
        <h2 className="text-lg font-semibold text-white">Install PRO Package</h2>
        <p className="text-sm text-gray-400">
          Your license is active, but the PRO package isn't loaded yet. Install
          it from the FilaOps license server to unlock Professional features.
        </p>
      </div>

      {state === "idle" && (
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onInstall}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
          >
            Install PRO
          </button>
          <span className="text-xs text-gray-500">
            Downloads the wheel from the license server and installs it locally.
            No terminal access required.
          </span>
        </div>
      )}

      {isBusy && (
        <div
          role="status"
          aria-live="polite"
          className="bg-blue-500/10 border border-blue-500/30 rounded-md px-4 py-3 flex items-center gap-3"
        >
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-400 flex-shrink-0" />
          <div className="text-sm text-blue-200">
            <div className="font-medium">{stateLabel}</div>
            {progress && progress !== stateLabel && (
              <div className="text-xs text-blue-300/80 mt-0.5">{progress}</div>
            )}
          </div>
        </div>
      )}

      {isDone && (
        <div className="space-y-3">
          <div
            role="status"
            className="bg-emerald-500/10 border border-emerald-500/30 rounded-md px-4 py-3 text-sm text-emerald-200"
          >
            <div className="font-medium">
              PRO installed successfully
              {installedVersion ? ` (v${installedVersion})` : ""}.
            </div>
            <div className="text-xs text-emerald-300/80 mt-1">
              Restart Core to activate PRO features. Core will continue to run
              in Community mode until you restart.
            </div>
          </div>
          <RestartInstructions />
        </div>
      )}

      {isError && (
        <div className="space-y-3">
          <div
            role="alert"
            className="bg-red-500/10 border border-red-500/30 rounded-md px-4 py-3 text-sm text-red-300"
          >
            <div className="font-medium">Installation failed</div>
            <div className="text-xs text-red-300/80 mt-1 break-words">
              {error || "Unknown error"}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => {
                onReset();
                onInstall();
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md text-sm font-medium transition-colors"
            >
              Retry
            </button>
            <button
              type="button"
              onClick={onReset}
              className="text-sm text-gray-400 hover:text-gray-200 underline transition-colors"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function RestartInstructions() {
  // Deployment-agnostic on purpose: customers run Core via Docker, pip, or
  // a future .exe installer. We list the common shapes rather than guess.
  return (
    <div className="text-xs text-gray-400 space-y-1">
      <div className="font-medium text-gray-300 uppercase tracking-wide">
        How to restart
      </div>
      <ul className="list-disc pl-5 space-y-0.5">
        <li>
          <span className="font-medium text-gray-300">Docker:</span>{" "}
          <code className="font-mono text-gray-200">docker compose restart backend</code>
        </li>
        <li>
          <span className="font-medium text-gray-300">systemd:</span>{" "}
          <code className="font-mono text-gray-200">sudo systemctl restart filaops</code>
        </li>
        <li>
          <span className="font-medium text-gray-300">Manual:</span> stop and
          re-start the Python process running uvicorn / Core
        </li>
      </ul>
    </div>
  );
}

function Field({ label, value, mono, hint }) {
  return (
    <div className="space-y-1">
      <div className="text-xs text-gray-500 uppercase tracking-wide">{label}</div>
      <div
        className={`text-gray-200 break-all ${mono ? "font-mono text-xs" : ""}`}
      >
        {value}
      </div>
      {hint && <div className="text-xs text-gray-500">{hint}</div>}
    </div>
  );
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
