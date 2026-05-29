export function BambuddyMachinesTable({
  connected,
  linking,
  machineError,
  machines,
  onLink,
  onUnlink,
  unlinkingId,
}) {
  const mutationInProgress = linking || Boolean(unlinkingId);

  return (
    <section className="bg-gray-800/40 border border-gray-700 rounded-lg overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-700 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Bambuddy Machines</h2>
          <p className="text-sm text-gray-400">
            Synced printers appear here before they are dispatched through FilaOps jobs.
          </p>
        </div>
        <span className="text-sm text-gray-400">{machines.length} machine(s)</span>
      </div>

      {machineError ? (
        <div className="p-6 text-sm text-red-300 bg-red-500/10 border-t border-red-500/20">
          {machineError}
        </div>
      ) : machines.length === 0 ? (
        <div className="p-8 text-center text-gray-400">
          {connected
            ? "No Bambuddy printers returned yet."
            : "Connect Bambuddy to list managed printers."}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-900/60 text-gray-400">
              <tr>
                <th className="py-3 px-4 text-left font-medium">Machine</th>
                <th className="py-3 px-4 text-left font-medium">Model</th>
                <th className="py-3 px-4 text-left font-medium">IP Address</th>
                <th className="py-3 px-4 text-left font-medium">Status</th>
                <th className="py-3 px-4 text-left font-medium">FilaOps Printer</th>
                <th className="py-3 px-4 text-right font-medium">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-700">
              {machines.map((machine) => (
                <tr key={machine.external_id} className="hover:bg-gray-700/30">
                  <td className="py-3 px-4 text-white font-medium">
                    {machine.name}
                    <div className="text-xs text-gray-500">{machine.external_id}</div>
                  </td>
                  <td className="py-3 px-4 text-gray-300">{machine.model || "-"}</td>
                  <td className="py-3 px-4 text-gray-300">{machine.ip_address || "-"}</td>
                  <td className="py-3 px-4">
                    <span className="inline-flex px-2 py-1 rounded-full border border-gray-600 text-gray-300 text-xs">
                      {machine.status || "unknown"}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-gray-300">
                    {machine.linked_printer ? (
                      <div>
                        <div className="text-white font-medium">
                          {machine.linked_printer.name}
                        </div>
                        <div className="text-xs text-gray-500">
                          {machine.linked_printer.code || `Printer #${machine.linked_printer_id}`}
                        </div>
                      </div>
                    ) : (
                      <span className="text-gray-500">Not linked</span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-right">
                    {machine.linked_printer_id ? (
                      <button
                        type="button"
                        onClick={() => onUnlink(machine)}
                        disabled={mutationInProgress}
                        className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-500 text-white rounded-md text-xs font-medium"
                      >
                        {unlinkingId === machine.external_id ? "Unlinking..." : "Unlink"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onLink(machine)}
                        disabled={mutationInProgress}
                        className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-800 disabled:text-gray-500 text-white rounded-md text-xs font-medium"
                      >
                        Link Printer
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
