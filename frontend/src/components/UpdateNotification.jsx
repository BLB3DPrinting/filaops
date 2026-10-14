import React, { useState } from "react";
import { useUpdateChecker } from "../hooks/useUpdateChecker";
import { API_URL } from "../config/api";

// FilaOps has no in-app updater: upgrades run on the host (back up, check out
// the release tag, rebuild). This banner only points the admin at the steps.
const UPGRADE_DOCS_URL = "https://blb3dprinting.github.io/filaops/UPGRADE/";

const UpdateNotification = () => {
  const { updateInfo, hasUpdate, dismissUpdate } = useUpdateChecker();
  const [showModal, setShowModal] = useState(false);
  const [instructions, setInstructions] = useState(null);
  const [loading, setLoading] = useState(false);

  if (!hasUpdate) return null;

  const loadInstructions = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/api/v1/system/updates/instructions`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const data = await res.json();
      setInstructions(data);
      setShowModal(true);
    } catch (err) {
      console.error("Failed to load instructions:", err);
      window.open(UPGRADE_DOCS_URL, "_blank", "noopener,noreferrer");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-lg shadow-lg p-4 mb-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🎉</span>
            <div>
              <h3 className="font-semibold">FilaOps {updateInfo.latest_version} Available!</h3>
              <p className="text-sm opacity-90">
                Current: {updateInfo.current_version || "unknown"} |
                {updateInfo.release_date && ` Released: ${new Date(updateInfo.release_date).toLocaleDateString()}`}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <button onClick={loadInstructions} disabled={loading} className="bg-white text-indigo-600 px-4 py-2 rounded font-semibold hover:bg-gray-100 disabled:opacity-50">
              {loading ? "Loading..." : "How to Upgrade"}
            </button>
            {updateInfo.release_url && (
              <a href={updateInfo.release_url} target="_blank" rel="noopener noreferrer" className="bg-white/20 border border-white/30 px-4 py-2 rounded hover:bg-white/30">
                Release Notes
              </a>
            )}
            <button onClick={dismissUpdate} className="text-white/80 hover:text-white px-2" title="Dismiss">✕</button>
          </div>
        </div>
      </div>

      {showModal && instructions && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onClick={() => setShowModal(false)}>
          <div className="bg-white dark:bg-gray-800 rounded-lg max-w-2xl w-full max-h-[80vh] overflow-hidden" onClick={(e) => e.stopPropagation()}>
            <div className="border-b border-gray-200 dark:border-gray-700 p-6 flex justify-between items-center">
              <h2 className="text-xl font-bold dark:text-white">Update to {updateInfo.latest_version}</h2>
              <button onClick={() => setShowModal(false)} className="text-gray-500 dark:text-gray-400 text-2xl">✕</button>
            </div>
            <div className="p-6 overflow-y-auto max-h-[60vh]">
              <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded p-4 mb-4">
                <strong className="text-yellow-800 dark:text-yellow-200">Important:</strong>
                <ul className="mt-2 text-sm text-yellow-700 dark:text-yellow-300 space-y-1">
                  <li>Downtime: {instructions.downtime}</li>
                  {instructions.backup_recommendation && <li>{instructions.backup_recommendation}</li>}
                  <li>Run these steps on the computer FilaOps is installed on, in order.</li>
                </ul>
              </div>
              <h3 className="font-semibold dark:text-white mb-3">Instructions:</h3>
              <ol className="space-y-2">
                {instructions.instructions.map((step, i) => (
                  <li key={i} className="bg-gray-50 dark:bg-gray-900/50 p-3 rounded border-l-4 border-indigo-500">
                    <code className="text-sm dark:text-gray-200">{step}</code>
                  </li>
                ))}
              </ol>
              {instructions.rollback_steps && (
                <details className="mt-4 bg-gray-50 dark:bg-gray-900/50 p-4 rounded">
                  <summary className="cursor-pointer font-semibold dark:text-white">Rollback Steps</summary>
                  <ol className="mt-2 space-y-1 text-sm">
                    {instructions.rollback_steps.map((step, i) => (<li key={i} className="dark:text-gray-300"><code>{step}</code></li>))}
                  </ol>
                </details>
              )}
              <div className="mt-4 pt-4 border-t dark:border-gray-700 text-sm">
                <p className="dark:text-gray-300"><strong>Time:</strong> {instructions.estimated_time}</p>
                <p className="dark:text-gray-300 mt-1">
                  <a href={instructions.documentation_url} target="_blank" rel="noopener noreferrer" className="text-indigo-600 dark:text-indigo-400 hover:underline">Full Documentation</a>
                </p>
              </div>
            </div>
            <div className="border-t dark:border-gray-700 p-6 flex gap-3 justify-end">
              <button onClick={() => setShowModal(false)} className="bg-gray-100 dark:bg-gray-700 px-6 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-600">Close</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};

export default UpdateNotification;
