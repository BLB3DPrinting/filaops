/**
 * Feature flags hook — reads live tier and features from AppContext.
 *
 * AppContext fetches /api/v1/system/info on mount. Core always returns
 * tier="community" with no features. When filaops-pro is installed and
 * a valid license key is configured, the backend returns the actual tier
 * and feature list, which this hook surfaces to components.
 *
 * Usage:
 *   const { isPro, hasFeature } = useFeatureFlags();
 *   {isPro && <GLReportsTab />}
 *   {hasFeature("accounting") && <AccountingSection />}
 */
import { useApp } from "../contexts/AppContext";

export const useFeatureFlags = () => {
  const { tier, features, loading } = useApp();

  return {
    tier,
    features,
    hasFeature: (feature) => features.includes(feature),
    isPro: tier === "professional" || tier === "enterprise",
    isEnterprise: tier === "enterprise",
    loading,
  };
};
