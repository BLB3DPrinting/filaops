import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useToast } from "../../components/Toast";
import { useFeatureFlags } from "../../hooks/useFeatureFlags";
import { useApi } from "../../hooks/useApi";
import {
  BambuddyAccessLock,
  BambuddyConnectionForm,
  BambuddyHeader,
  BambuddyLegalNotice,
  BambuddyMachinesTable,
  BambuddyStatusPanel,
  LinkPrinterModal,
} from "./bambuddy";
import { DEFAULT_BAMBUDDY_URL, getSyncMessage } from "./bambuddy/utils";

export default function AdminBambuddy() {
  const api = useApi();
  const toast = useToast();
  const { isPro, hasFeature, loading: featuresLoading } = useFeatureFlags();
  const bambuddyAvailable = isPro && hasFeature("bambu_integration");
  const apiKeyInputRef = useRef(null);
  const [status, setStatus] = useState(null);
  const [machines, setMachines] = useState([]);
  const [form, setForm] = useState({ base_url: DEFAULT_BAMBUDDY_URL });
  const [loading, setLoading] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [printers, setPrinters] = useState([]);
  const [selectedMachine, setSelectedMachine] = useState(null);
  const [selectedPrinterId, setSelectedPrinterId] = useState("");
  const [linking, setLinking] = useState(false);
  const [unlinkingId, setUnlinkingId] = useState(null);
  const [machineError, setMachineError] = useState("");

  const connected = Boolean(status?.connected);
  const openUrl = useMemo(
    () => status?.base_url || form.base_url || DEFAULT_BAMBUDDY_URL,
    [form.base_url, status?.base_url],
  );
  const visibleMachines = connected ? machines : [];

  const loadMachines = useCallback(async () => {
    if (!bambuddyAvailable || !connected) {
      return;
    }
    try {
      const data = await api.get("/api/v1/pro/printer-providers/bambuddy/machines");
      setMachineError("");
      setMachines(Array.isArray(data) ? data : []);
    } catch (err) {
      setMachines([]);
      setMachineError(err.message);
    }
  }, [api, bambuddyAvailable, connected]);

  const loadStatus = useCallback(async () => {
    try {
      const data = await api.get("/api/v1/pro/integrations/bambuddy/status");
      setStatus(data);
      if (data?.base_url) {
        setForm((prev) => ({ ...prev, base_url: data.base_url }));
      }
    } catch (err) {
      setStatus({ connected: false, health: "error" });
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  }, [api, toast]);

  const loadPrinters = useCallback(async () => {
    try {
      const data = await api.get("/api/v1/printers?active_only=true&page_size=200");
      setPrinters(Array.isArray(data?.items) ? data.items : []);
    } catch (err) {
      setPrinters([]);
      toast.error(err.message);
    }
  }, [api, toast]);

  useEffect(() => {
    if (featuresLoading) return;
    if (!bambuddyAvailable) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Fetch-on-enable updates state after the async API response.
    loadStatus();
    loadPrinters();
  }, [bambuddyAvailable, featuresLoading, loadPrinters, loadStatus]);

  useEffect(() => {
    if (featuresLoading || !bambuddyAvailable || !connected) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Fetch-on-connect updates state after the async API response.
    loadMachines();
  }, [bambuddyAvailable, connected, featuresLoading, loadMachines]);

  const handleConnect = async (event) => {
    event.preventDefault();
    const apiKey = apiKeyInputRef.current?.value?.trim() || "";
    setConnecting(true);
    try {
      const data = await api.post("/api/v1/pro/integrations/bambuddy/connect", {
        base_url: form.base_url.trim(),
        api_key: apiKey,
      });
      setStatus(data);
      if (data?.base_url) {
        setForm((prev) => ({ ...prev, base_url: data.base_url }));
      }
      toast.success("Bambuddy connected");
    } catch (err) {
      toast.error(err.message);
    } finally {
      if (apiKeyInputRef.current) {
        apiKeyInputRef.current.value = "";
      }
      setConnecting(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const result = await api.post("/api/v1/pro/integrations/bambuddy/sync", {});
      await loadStatus();
      await loadMachines();
      toast.success(getSyncMessage(result));
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSyncing(false);
    }
  };

  const openLinkDialog = (machine) => {
    setSelectedMachine(machine);
    setSelectedPrinterId("");
  };

  const closeLinkDialog = () => {
    if (linking) return;
    setSelectedMachine(null);
    setSelectedPrinterId("");
  };

  const handleLink = async (event) => {
    event.preventDefault();
    if (!selectedMachine || !selectedPrinterId) return;
    setLinking(true);
    try {
      await api.post(
        `/api/v1/pro/printer-providers/bambuddy/printers/${encodeURIComponent(
          selectedMachine.external_id,
        )}/link`,
        { filaops_printer_id: Number(selectedPrinterId) },
      );
      await loadMachines();
      setSelectedMachine(null);
      setSelectedPrinterId("");
      toast.success("Bambuddy machine linked");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLinking(false);
    }
  };

  const handleUnlink = async (machine) => {
    setUnlinkingId(machine.external_id);
    try {
      await api.del(
        `/api/v1/pro/printer-providers/bambuddy/printers/${encodeURIComponent(
          machine.external_id,
        )}/link`,
      );
      await loadMachines();
      toast.success("Bambuddy machine unlinked");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setUnlinkingId(null);
    }
  };

  if (featuresLoading || (bambuddyAvailable && loading)) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  if (!bambuddyAvailable) {
    return <BambuddyAccessLock isPro={isPro} />;
  }

  return (
    <div className="space-y-6">
      <BambuddyHeader openUrl={openUrl} onRefresh={loadStatus} />

      <section className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_360px] gap-6">
        <BambuddyStatusPanel
          connected={connected}
          status={status}
          syncing={syncing}
          onSync={handleSync}
        />
        <BambuddyConnectionForm
          baseUrl={form.base_url}
          connected={connected}
          connecting={connecting}
          inputRef={apiKeyInputRef}
          onBaseUrlChange={(base_url) => setForm({ base_url })}
          onSubmit={handleConnect}
        />
      </section>

      <BambuddyMachinesTable
        connected={connected}
        linking={linking}
        machineError={machineError}
        machines={visibleMachines}
        onLink={openLinkDialog}
        onUnlink={handleUnlink}
        unlinkingId={unlinkingId}
      />

      <BambuddyLegalNotice />

      <LinkPrinterModal
        linking={linking}
        machine={selectedMachine}
        printers={printers}
        selectedPrinterId={selectedPrinterId}
        onClose={closeLinkDialog}
        onPrinterChange={setSelectedPrinterId}
        onSubmit={handleLink}
      />
    </div>
  );
}
