export function BambuddyHeader({ openUrl, onRefresh }) {
  return (
    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
      <div>
        <h1 className="text-2xl font-bold text-white">Bambuddy</h1>
        <p className="text-gray-400 mt-1">
          Connect FilaOps PRO to the managed Bambuddy service for Bambu printer operations.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => window.open(openUrl, "_blank", "noopener,noreferrer")}
          className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md text-sm font-medium"
        >
          Open Bambuddy
        </button>
        <button
          type="button"
          onClick={onRefresh}
          className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-md text-sm font-medium"
        >
          Refresh
        </button>
      </div>
    </div>
  );
}
