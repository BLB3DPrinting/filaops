/**
 * IPProbeSection - Find printers by IP address with probe detection.
 *
 * Extracted from AdminPrinters.jsx (ARCHITECT-002)
 */
import { useState } from "react";
import { API_URL } from "../../config/api";
import { useToast } from "../Toast";

export default function IPProbeSection({ onPrinterFound }) {
  const toast = useToast();
  const [ipAddress, setIpAddress] = useState("");
  const [probing, setProbing] = useState(false);
  const [probeResult, setProbeResult] = useState(null);

  const handleProbe = async () => {
    if (!ipAddress.trim()) {
      toast.error("Please enter an IP address");
      return;
    }

    // Basic IP validation
    const ipRegex = /^(\d{1,3}\.){3}\d{1,3}$/;
    if (!ipRegex.test(ipAddress.trim())) {
      toast.error("Please enter a valid IP address");
      return;
    }

    setProbing(true);
    setProbeResult(null);

    try {
      const res = await fetch(
        `${API_URL}/api/v1/printers/probe-ip?ip_address=${encodeURIComponent(ipAddress.trim())}`,
        {
          method: "POST",
          credentials: "include",
        }
      );

      if (!res.ok) throw new Error("Probe failed");

      const result = await res.json();
      setProbeResult(result);

      if (result.reachable) {
        toast.success(`Found ${result.brand || "printer"} at ${ipAddress}`);
        if (!result.already_registered) {
          onPrinterFound({
            ip_address: result.ip_address,
            brand: result.brand || "generic",
            model: result.model,
            name: result.suggested_name,
            suggested_code: result.suggested_code,
            already_registered: false,
          });
        }
      } else {
        toast.error(`No printer found at ${ipAddress}`);
      }
    } catch (err) {
      toast.error("Failed to probe IP: " + err.message);
    } finally {
      setProbing(false);
    }
  };

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-6">
      <h2 className="text-lg font-medium text-white mb-2">Find Printer by IP</h2>
      <p className="text-gray-400 text-sm mb-4">
        Enter a printer's IP address to detect it. Works with BambuLab, Klipper, and OctoPrint.
      </p>

      <div className="flex gap-3">
        <input
          type="text"
          value={ipAddress}
          onChange={(e) => setIpAddress(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleProbe()}
          placeholder="192.168.1.100"
          className="flex-1 bg-gray-900 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500 font-mono"
        />
        <button
          onClick={handleProbe}
          disabled={probing}
          className="bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 text-white px-6 py-2 rounded-lg transition-colors flex items-center gap-2"
        >
          {probing ? (
            <>
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Probing...
            </>
          ) : (
            <>
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
              </svg>
              Probe
            </>
          )}
        </button>
      </div>

      {/* Probe Result */}
      {probeResult && (
        <div className={`mt-4 p-3 rounded-lg ${probeResult.reachable ? "bg-green-500/10 border border-green-500/30" : "bg-red-500/10 border border-red-500/30"}`}>
          {probeResult.reachable ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <svg className="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-green-400 font-medium">Printer Found!</span>
              </div>
              <div className="text-sm text-gray-300 space-y-1">
                <div>Brand: <span className="text-white">{probeResult.brand || "Unknown"}</span></div>
                <div>Open ports: <span className="text-white font-mono text-xs">{probeResult.ports_open?.map(p => `${p.port} (${p.service})`).join(", ") || "None"}</span></div>
                {probeResult.already_registered && (
                  <div className="text-yellow-400">
                    Already registered as: {probeResult.existing_printer?.name} ({probeResult.existing_printer?.code})
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-red-400">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
              <span>No printer detected at this IP</span>
            </div>
          )}
        </div>
      )}

      {/* Quick tip */}
      <div className="mt-4 text-xs text-gray-500">
        Tip: Check your router's DHCP client list to find printer IPs, or look in your printer's network settings.
      </div>
    </div>
  );
}
