import { DEFAULT_BAMBUDDY_URL } from "./utils";

export function BambuddyConnectionForm({
  baseUrl,
  connected,
  connecting,
  inputRef,
  onBaseUrlChange,
  onSubmit,
}) {
  return (
    <form
      onSubmit={onSubmit}
      className="bg-gray-800/40 border border-gray-700 rounded-lg p-6 space-y-4"
    >
      <div>
        <h2 className="text-lg font-semibold text-white">Connection</h2>
        <p className="text-sm text-gray-400 mt-1">
          Use the API key generated in Bambuddy. Clear the field before sharing your screen.
        </p>
      </div>
      <label className="block">
        <span className="text-sm font-medium text-gray-300">Bambuddy URL</span>
        <input
          type="url"
          value={baseUrl}
          onChange={(event) => onBaseUrlChange(event.target.value)}
          className="mt-1 w-full bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          placeholder={DEFAULT_BAMBUDDY_URL}
          required
        />
      </label>
      <label className="block">
        <span className="text-sm font-medium text-gray-300">API Key</span>
        <input
          ref={inputRef}
          type="password"
          className="mt-1 w-full bg-gray-900 border border-gray-700 rounded-md px-3 py-2 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
          autoComplete="off"
          required
        />
      </label>
      <button
        type="submit"
        disabled={connecting}
        className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-400 text-white rounded-md text-sm font-medium"
      >
        {connecting ? "Connecting..." : connected ? "Update Connection" : "Connect"}
      </button>
    </form>
  );
}
