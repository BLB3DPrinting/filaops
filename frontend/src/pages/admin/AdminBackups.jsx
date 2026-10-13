/**
 * Backups — set up, watch and test database backups without shell access.
 *
 * Reads GET /api/v1/admin/backups (schedule, tool versions, storage, latest
 * runs) and /admin/backups/runs (history). The schedule is saved through the
 * generic system setting `database_backup`. "Run backup now" starts a backup
 * in the background; the page polls until it finishes.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "../../hooks/useApi";
import { useToast } from "../../components/Toast";
import { API_URL } from "../../config/api";

const POLL_MS = 3000;

const card =
  "bg-[var(--paper)] border border-[var(--rule-hair)] rounded-xl p-6 shadow-[var(--shadow-pop)]";
const input =
  "w-full bg-[var(--paper-sunk)] border border-[var(--rule-hair)] rounded-lg px-3 py-2 text-[var(--ink)]";
const primaryButton =
  "px-4 py-2 rounded-lg bg-[var(--accent)] text-[var(--accent-ink)] hover:bg-[var(--accent-press)] disabled:opacity-50 disabled:cursor-not-allowed";
const secondaryButton =
  "px-3 py-1.5 rounded-lg bg-[var(--paper-sunk)] text-[var(--ink-2)] border border-[var(--rule-hair)] hover:text-[var(--ink)]";

function formatBytes(bytes) {
  if (bytes == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
}

function formatWhen(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

function browserTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

function timeZoneOptions(current) {
  let zones = [];
  try {
    zones = Intl.supportedValuesOf("timeZone");
  } catch {
    zones = [];
  }
  const all = new Set(["UTC", ...zones, current, browserTimeZone()]);
  return [...all].filter(Boolean).sort();
}

function StatusPill({ status }) {
  const styles = {
    ok: "bg-[var(--status-green-tint)] text-[var(--status-green)]",
    failed: "bg-[var(--status-red-tint)] text-[var(--status-red)]",
    running: "bg-[var(--status-amber-tint)] text-[var(--status-amber)]",
  };
  const labels = { ok: "OK", failed: "Failed", running: "Running" };
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded ${styles[status] || ""}`}>
      {labels[status] || status}
    </span>
  );
}

function Summary({ status }) {
  const last = status.last_success;
  const lastRun = status.last_run;
  const storageProblem = status.storage.problem;
  let tone = "amber";
  let headline = "No backup has completed yet.";
  if (status.running) {
    headline = "A backup is running now…";
  } else if (lastRun && lastRun.status === "failed") {
    tone = "red";
    headline = "The last backup failed.";
  } else if (last) {
    tone = "green";
    headline = `Last good backup: ${formatWhen(last.finished_at)}`;
  }
  const toneClass = {
    green: "border-[var(--status-green)] bg-[var(--status-green-tint)]",
    amber: "border-[var(--status-amber)] bg-[var(--status-amber-tint)]",
    red: "border-[var(--status-red)] bg-[var(--status-red-tint)]",
  }[tone];

  return (
    <div className={`rounded-xl border p-4 ${toneClass}`} data-testid="backup-summary">
      <p className="font-semibold text-[var(--ink)]">{headline}</p>
      {/* The storage warning above already explains a refusal; don't repeat it. */}
      {lastRun && lastRun.status === "failed" && !status.running && lastRun.error !== storageProblem && (
        <p className="text-sm text-[var(--ink-2)] mt-1">{lastRun.error}</p>
      )}
      {last && (
        <p className="text-sm text-[var(--ink-2)] mt-1">
          {formatBytes(last.size_bytes)}, {last.table_count} tables, checked after writing.
        </p>
      )}
      <p className="text-sm text-[var(--ink-2)] mt-1">
        {storageProblem
          ? "No backup will run until the backup folder is fixed."
          : status.next_run_at
          ? `Next scheduled backup: ${formatWhen(status.next_run_at)}`
          : status.scheduler_enabled
            ? "Scheduled backups are turned off."
            : "This server does not run scheduled backups (BACKUP_SCHEDULER_ENABLED=false)."}
      </p>
    </div>
  );
}

// Shown above everything else: while the folder is not on a volume, no
// backup runs, so the admin must see why before anything else on the page.
function StorageWarning({ problem }) {
  return (
    <div
      className="rounded-xl border border-[var(--status-red)] bg-[var(--status-red-tint)] p-4"
      role="alert"
      data-testid="storage-warning"
    >
      <p className="font-semibold text-[var(--status-red)]">Backups are not running</p>
      <p className="text-sm text-[var(--ink)] mt-1">{problem}</p>
    </div>
  );
}

function SystemChecks({ tools, storage }) {
  return (
    <div className={card}>
      <h2 className="text-lg font-semibold text-[var(--ink)] mb-3">System</h2>
      {tools.problem && (
        <p className="text-sm text-[var(--status-red)] mb-3" role="alert">
          {tools.problem}
        </p>
      )}
      <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
        <dt className="text-[var(--ink-3)]">Database server</dt>
        <dd className="text-[var(--ink)]">PostgreSQL {tools.server_version || "—"}</dd>
        <dt className="text-[var(--ink-3)]">Backup tool</dt>
        <dd className="text-[var(--ink)]">{tools.pg_dump_version || "not found"}</dd>
        <dt className="text-[var(--ink-3)]">Stored in</dt>
        <dd className="text-[var(--ink)] break-all">
          {storage.path}
          {!storage.writable && (
            <span className="text-[var(--status-red)]"> (not writable)</span>
          )}
        </dd>
        <dt className="text-[var(--ink-3)]">Backups on disk</dt>
        <dd className="text-[var(--ink)]">
          {storage.file_count} ({formatBytes(storage.total_bytes)}), {formatBytes(storage.free_bytes)} free
        </dd>
      </dl>
    </div>
  );
}

// Keyed on the saved value by the parent, so a reload with new settings
// starts the form over instead of syncing state in an effect.
function ScheduleForm({ saved, problem, onSave, saving }) {
  const [form, setForm] = useState(saved);
  const myZone = browserTimeZone();
  const dirty = JSON.stringify(form) !== JSON.stringify(saved);

  return (
    <form
      className={card}
      onSubmit={(e) => {
        e.preventDefault();
        onSave(form);
      }}
    >
      <h2 className="text-lg font-semibold text-[var(--ink)] mb-4">Schedule</h2>
      {problem && (
        <p className="text-sm text-[var(--status-red)] mb-4" role="alert">
          The saved schedule can't be used ({problem}), so the default time and
          retention apply. Check the values below and save again.
        </p>
      )}
      <label className="flex items-center gap-2 mb-4 text-[var(--ink)]">
        <input
          type="checkbox"
          checked={form.enabled}
          onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
        />
        Back up the database every day
      </label>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <label className="text-sm text-[var(--ink-2)]">
          Time
          <input
            type="time"
            className={`${input} mt-1`}
            value={form.time}
            required
            onChange={(e) => setForm({ ...form, time: e.target.value })}
          />
        </label>
        <label className="text-sm text-[var(--ink-2)]">
          Time zone
          <select
            className={`${input} mt-1`}
            value={form.timezone}
            onChange={(e) => setForm({ ...form, timezone: e.target.value })}
          >
            {timeZoneOptions(form.timezone).map((zone) => (
              <option key={zone} value={zone}>
                {zone}
              </option>
            ))}
          </select>
          {form.timezone !== myZone && (
            <button
              type="button"
              className="text-xs underline text-[var(--ink-2)] mt-1"
              onClick={() => setForm({ ...form, timezone: myZone })}
            >
              Use my time zone ({myZone})
            </button>
          )}
        </label>
        <label className="text-sm text-[var(--ink-2)]">
          Keep backups for (days)
          <input
            type="number"
            min={1}
            max={365}
            className={`${input} mt-1`}
            value={form.retention_days}
            required
            onChange={(e) => setForm({ ...form, retention_days: Number(e.target.value) })}
          />
        </label>
      </div>
      <p className="text-xs text-[var(--ink-3)] mt-3">
        Older backups are deleted automatically, except the newest good one, which is
        always kept.
      </p>
      <div className="mt-4">
        <button type="submit" className={primaryButton} disabled={!dirty || saving}>
          {saving ? "Saving…" : "Save schedule"}
        </button>
      </div>
    </form>
  );
}

function RunsTable({ runs }) {
  if (!runs.length) {
    return <p className="text-sm text-[var(--ink-3)]">No backups yet.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left border-b border-[var(--rule-hair)]">
            <th className="px-2 py-2 text-[var(--ink-3)] font-medium">Started</th>
            <th className="px-2 py-2 text-[var(--ink-3)] font-medium">How</th>
            <th className="px-2 py-2 text-[var(--ink-3)] font-medium">Result</th>
            <th className="px-2 py-2 text-[var(--ink-3)] font-medium text-right">Size</th>
            <th className="px-2 py-2 text-[var(--ink-3)] font-medium text-right">Tables</th>
            <th className="px-2 py-2" />
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-b border-[var(--rule-hair)] align-top">
              <td className="px-2 py-2 text-[var(--ink)] whitespace-nowrap">
                {formatWhen(run.started_at)}
              </td>
              <td className="px-2 py-2 text-[var(--ink-2)]">
                {run.trigger === "manual" ? "Run now" : "Scheduled"}
              </td>
              <td className="px-2 py-2">
                <StatusPill status={run.status} />
                {run.error && (
                  <p className="text-xs text-[var(--ink-2)] mt-1 max-w-md">{run.error}</p>
                )}
              </td>
              <td className="px-2 py-2 text-right text-[var(--ink)]">{formatBytes(run.size_bytes)}</td>
              <td className="px-2 py-2 text-right text-[var(--ink)]">{run.table_count ?? "—"}</td>
              <td className="px-2 py-2 text-right whitespace-nowrap">
                {run.downloadable ? (
                  <a
                    className={secondaryButton}
                    href={`${API_URL}/api/v1/admin/backups/runs/${run.id}/download`}
                    download={run.filename}
                  >
                    Download
                  </a>
                ) : run.status === "ok" ? (
                  <span className="text-xs text-[var(--ink-3)]">Removed (older than retention)</span>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function AdminBackups() {
  const api = useApi();
  const toast = useToast();
  const [status, setStatus] = useState(null);
  const [runs, setRuns] = useState([]);
  const [loadError, setLoadError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [starting, setStarting] = useState(false);
  const watchingRun = useRef(null);

  const load = useCallback(async () => {
    try {
      const [nextStatus, nextRuns] = await Promise.all([
        api.get("/api/v1/admin/backups"),
        api.get("/api/v1/admin/backups/runs?limit=30"),
      ]);
      setStatus(nextStatus);
      setRuns(nextRuns);
      setLoadError(null);
      return { status: nextStatus, runs: nextRuns };
    } catch (err) {
      setLoadError(err.message || "Could not load backup status");
      return null;
    }
  }, [api]);

  useEffect(() => {
    load();
  }, [load]);

  // Report how the backup this admin started ended, once it has.
  const reportFinished = useCallback(
    (result) => {
      if (!result || result.status.running || watchingRun.current == null) return;
      const finished = result.runs.find((r) => r.id === watchingRun.current);
      watchingRun.current = null;
      if (finished?.status === "ok") toast.success("Backup finished and verified.");
      else if (finished) toast.error(`Backup failed: ${finished.error || "see the list below"}`);
    },
    [toast],
  );

  // Poll while a backup runs.
  const running = Boolean(status?.running);
  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(async () => reportFinished(await load()), POLL_MS);
    return () => clearInterval(timer);
  }, [running, load, reportFinished]);

  const saveSchedule = async (value) => {
    setSaving(true);
    try {
      await api.put("/api/v1/system/settings/database_backup", { value });
      toast.success("Backup schedule saved.");
      await load();
    } catch {
      // ApiErrorToaster already shows the server's reason.
    } finally {
      setSaving(false);
    }
  };

  const runNow = async () => {
    setStarting(true);
    try {
      const started = await api.post("/api/v1/admin/backups/runs");
      watchingRun.current = started.id;
      toast.success("Backup started.");
      reportFinished(await load());
    } catch {
      // ApiErrorToaster already shows the server's reason (e.g. already running).
    } finally {
      setStarting(false);
    }
  };

  if (loadError && !status) {
    return (
      <div className={card}>
        <p className="text-[var(--status-red)]">{loadError}</p>
        <button type="button" className={`${secondaryButton} mt-3`} onClick={load}>
          Try again
        </button>
      </div>
    );
  }
  if (!status) {
    return (
      <div className="p-6 flex justify-center">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[var(--accent)]" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header in its own paper card: the AdminLayout shell is still the
          dark Neo background (#846), so ink text needs a light surface. */}
      <div className={`${card} flex flex-wrap items-start justify-between gap-4`}>
        <div>
          <h1 className="text-2xl font-bold text-[var(--ink)]">Backups</h1>
          <p className="text-[var(--ink-2)] mt-1 max-w-2xl">
            FilaOps copies its whole database to a file every day and checks that the copy
            is complete. Run one now to test it.
          </p>
        </div>
        <button
          type="button"
          className={primaryButton}
          onClick={runNow}
          disabled={starting || status.running || Boolean(status.storage.problem)}
        >
          {status.running ? "Backup running…" : starting ? "Starting…" : "Run backup now"}
        </button>
      </div>

      {status.storage.problem && <StorageWarning problem={status.storage.problem} />}

      <Summary status={status} />

      <div className="rounded-xl border border-[var(--rule-hair)] bg-[var(--paper-sunk)] p-4 text-sm text-[var(--ink-2)]">
        <p>
          <strong className="text-[var(--ink)]">Keep backups private.</strong> They contain
          customer details and password hashes. Store downloads somewhere only you can reach.
        </p>
        <p className="mt-1">
          Backups kept on this server are lost if the server is lost. Download a copy
          regularly and keep it somewhere else.
        </p>
      </div>

      <ScheduleForm
        key={JSON.stringify(status.settings)}
        saved={status.settings}
        problem={status.settings_problem}
        onSave={saveSchedule}
        saving={saving}
      />

      <SystemChecks tools={status.tools} storage={status.storage} />

      <div className={card}>
        <h2 className="text-lg font-semibold text-[var(--ink)] mb-3">Recent backups</h2>
        <RunsTable runs={runs} />
      </div>
    </div>
  );
}
