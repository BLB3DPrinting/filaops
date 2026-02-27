/* eslint-disable react-refresh/only-export-components */
/**
 * AppContext — system tier and feature discovery.
 *
 * Fetches /api/v1/system/info once at mount and exposes { tier, features }
 * so components can gate PRO-only UI:
 *
 *   const { tier } = useApp();
 *   {tier !== "community" && <ProSection />}
 *
 * Core always returns tier="community" with no features.
 * When filaops-pro is installed, the backend returns the actual tier.
 */
import { createContext, useContext, useState, useEffect } from "react";
import { API_URL } from "../config/api";

const AppContext = createContext({
  tier: "community",
  features: [],
  loading: true,
});

export function AppProvider({ children }) {
  const [tier, setTier] = useState("community");
  const [features, setFeatures] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_URL}/api/v1/system/info`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (cancelled || !data) return;
        setTier(data.tier ?? "community");
        setFeatures(data.features_enabled ?? []);
      })
      .catch(() => {
        // Endpoint unreachable — stay on community defaults
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AppContext.Provider value={{ tier, features, loading }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  return useContext(AppContext);
}

export default AppContext;
