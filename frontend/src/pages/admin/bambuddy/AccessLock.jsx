import { Link } from "react-router-dom";

export function BambuddyAccessLock({ isPro }) {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-white">Bambuddy</h1>
      <div className="bg-gray-800/40 border border-gray-700 rounded-lg p-6">
        <h2 className="text-lg font-semibold text-white">
          {isPro ? "Bambuddy not enabled" : "PRO required"}
        </h2>
        <p className="text-sm text-gray-400 mt-2">
          {isPro
            ? "This PRO license does not include the Bambu integration feature."
            : "Bambuddy printer orchestration is available with FilaOps PRO."}
        </p>
        <Link
          to="/admin/license"
          className="inline-flex mt-4 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md text-sm font-medium"
        >
          Open License
        </Link>
      </div>
    </div>
  );
}
