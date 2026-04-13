import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { createContext, useMemo, lazy, Suspense } from "react";
import { ToastProvider } from "./components/Toast";
import { createApiClient } from "./lib/apiClient";
import { API_URL } from "./config/api";
import { AppProvider } from "./contexts/AppContext";
import { LocaleProvider } from "./contexts/LocaleContext";
import ErrorBoundary from "./components/ErrorBoundary";
import ApiErrorToaster from "./components/ApiErrorToaster";
import AdminLayout from "./components/AdminLayout";
import Setup from "./pages/Setup";
import Onboarding from "./pages/Onboarding";

// eslint-disable-next-line react-refresh/only-export-components
export const ApiContext = createContext(null);

// Auth pages (eager — needed on first load)
import AdminLogin from "./pages/admin/AdminLogin";
import ForgotPassword from "./pages/admin/ForgotPassword";
import ResetPassword from "./pages/admin/ResetPassword";
import AdminPasswordResetApproval from "./pages/admin/AdminPasswordResetApproval";
import NotFound from "./pages/NotFound";
import Pricing from "./pages/Pricing";

// Admin pages (lazy-loaded for smaller initial bundle)
const AdminDashboard = lazy(() => import("./pages/admin/AdminDashboard"));
const AdminOrders = lazy(() => import("./pages/admin/AdminOrders"));
const OrderDetail = lazy(() => import("./pages/admin/OrderDetail"));
const AdminBOM = lazy(() => import("./pages/admin/AdminBOM"));
const AdminItems = lazy(() => import("./pages/admin/AdminItems"));
const AdminPurchasing = lazy(() => import("./pages/admin/AdminPurchasing"));
const AdminProduction = lazy(() => import("./pages/admin/AdminProduction"));
const ProductionOrderDetail = lazy(
  () => import("./pages/admin/ProductionOrderDetail"),
);
const AdminShipping = lazy(() => import("./pages/admin/AdminShipping"));
const AdminManufacturing = lazy(
  () => import("./pages/admin/AdminManufacturing"),
);
const AdminCustomers = lazy(() => import("./pages/admin/AdminCustomers"));
const AdminInventoryTransactions = lazy(
  () => import("./pages/admin/AdminInventoryTransactions"),
);
const AdminAnalytics = lazy(() => import("./pages/admin/AdminAnalytics"));
const AdminMaterialImport = lazy(
  () => import("./pages/admin/AdminMaterialImport"),
);
const AdminOrderImport = lazy(() => import("./pages/admin/AdminOrderImport"));
const AdminUsers = lazy(() => import("./pages/admin/AdminUsers"));
const AdminQuotes = lazy(() => import("./pages/admin/AdminQuotes"));
const AdminPayments = lazy(() => import("./pages/admin/AdminPayments"));
const AdminInvoices = lazy(() => import("./pages/admin/AdminInvoices"));
const AdminSettings = lazy(() => import("./pages/admin/AdminSettings"));
const AdminLocations = lazy(() => import("./pages/admin/AdminLocations"));
const AdminAccounting = lazy(() => import("./pages/admin/AdminAccounting"));
const AdminPrinters = lazy(() => import("./pages/admin/AdminPrinters"));
const AdminFilaFarm = lazy(() => import("./pages/admin/AdminFilaFarm"));
const AdminScrapReasons = lazy(() => import("./pages/admin/AdminScrapReasons"));
const AdminSpools = lazy(() => import("./pages/admin/AdminSpools"));
const AdminSecurity = lazy(() => import("./pages/admin/AdminSecurity"));
const AdminCycleCount = lazy(() => import("./pages/admin/AdminCycleCount"));
const AdminPriceLevels = lazy(() => import("./pages/admin/AdminPriceLevels"));
const AdminAccessRequests = lazy(
  () => import("./pages/admin/AdminAccessRequests"),
);
const AdminCatalogs = lazy(() => import("./pages/admin/AdminCatalogs"));
const AdminNotifications = lazy(
  () => import("./pages/admin/AdminNotifications"),
);
const MaterialTraceability = lazy(
  () => import("./pages/admin/quality/MaterialTraceability"),
);
const QualityDashboard = lazy(
  () => import("./pages/admin/quality/QualityDashboard"),
);
const CommandCenter = lazy(() => import("./pages/CommandCenter"));

// Suspense fallback for lazy-loaded pages
function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
    </div>
  );
}

export default function App() {
  const api = useMemo(
    () =>
      createApiClient({
        baseUrl: API_URL,
        onUnauthorized: async () => {
          localStorage.removeItem("adminUser");
          // eslint-disable-next-line react-hooks/immutability -- Redirect in callback, not during render
          window.location.href = "/admin/login";
        },
        onError: (err) => {
          // why: centralized logging hook (also toasts via ApiErrorToaster)
          console.warn("API error:", err.status, err.message);
        },
      }),
    [],
  );

  return (
    <ErrorBoundary>
      <AppProvider>
        <LocaleProvider>
          <ApiContext.Provider value={api}>
            <ToastProvider>
              {/* Global API error toasts */}
              <ApiErrorToaster />
              <BrowserRouter>
                <Routes>
                  {/* Redirect root to admin */}
                  <Route path="/" element={<Navigate to="/admin" replace />} />

                  {/* First-run setup */}
                  <Route path="/setup" element={<Setup />} />
                  <Route path="/onboarding" element={<Onboarding />} />

                  {/* Auth */}
                  <Route path="/admin/login" element={<AdminLogin />} />
                  <Route path="/forgot-password" element={<ForgotPassword />} />
                  <Route
                    path="/reset-password/:token"
                    element={<ResetPassword />}
                  />
                  <Route
                    path="/admin/password-reset/:action/:token"
                    element={<AdminPasswordResetApproval />}
                  />

                  {/* Public Pricing Page */}
                  <Route path="/pricing" element={<Pricing />} />

                  {/* ERP Admin Panel */}
                  <Route path="/admin" element={<AdminLayout />}>
                    <Route
                      index
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminDashboard />
                        </Suspense>
                      }
                    />
                    <Route
                      path="orders"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminOrders />
                        </Suspense>
                      }
                    />
                    <Route
                      path="orders/:orderId"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <OrderDetail />
                        </Suspense>
                      }
                    />
                    <Route
                      path="quotes"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminQuotes />
                        </Suspense>
                      }
                    />
                    <Route
                      path="payments"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminPayments />
                        </Suspense>
                      }
                    />
                    <Route
                      path="invoices"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminInvoices />
                        </Suspense>
                      }
                    />
                    <Route
                      path="customers"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminCustomers />
                        </Suspense>
                      }
                    />
                    <Route
                      path="messages"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminNotifications />
                        </Suspense>
                      }
                    />
                    <Route
                      path="bom"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminBOM />
                        </Suspense>
                      }
                    />
                    <Route
                      path="products"
                      element={<Navigate to="/admin/items" replace />}
                    />
                    <Route
                      path="items"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminItems />
                        </Suspense>
                      }
                    />
                    <Route
                      path="purchasing"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminPurchasing />
                        </Suspense>
                      }
                    />
                    <Route
                      path="manufacturing"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminManufacturing />
                        </Suspense>
                      }
                    />
                    <Route
                      path="production"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminProduction />
                        </Suspense>
                      }
                    />
                    <Route
                      path="production/:orderId"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <ProductionOrderDetail />
                        </Suspense>
                      }
                    />
                    <Route
                      path="shipping"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminShipping />
                        </Suspense>
                      }
                    />
                    <Route
                      path="analytics"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminAnalytics />
                        </Suspense>
                      }
                    />
                    <Route
                      path="materials/import"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminMaterialImport />
                        </Suspense>
                      }
                    />
                    <Route
                      path="orders/import"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminOrderImport />
                        </Suspense>
                      }
                    />
                    <Route
                      path="inventory/transactions"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminInventoryTransactions />
                        </Suspense>
                      }
                    />
                    <Route
                      path="inventory/cycle-count"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminCycleCount />
                        </Suspense>
                      }
                    />
                    <Route
                      path="users"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminUsers />
                        </Suspense>
                      }
                    />
                    <Route
                      path="locations"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminLocations />
                        </Suspense>
                      }
                    />
                    <Route
                      path="accounting"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminAccounting />
                        </Suspense>
                      }
                    />
                    <Route
                      path="printers"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminPrinters />
                        </Suspense>
                      }
                    />
                    <Route
                      path="filafarm"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminFilaFarm />
                        </Suspense>
                      }
                    />
                    <Route
                      path="scrap-reasons"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminScrapReasons />
                        </Suspense>
                      }
                    />
                    <Route
                      path="spools"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminSpools />
                        </Suspense>
                      }
                    />
                    <Route
                      path="quality"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <QualityDashboard />
                        </Suspense>
                      }
                    />
                    <Route
                      path="quality/traceability"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <MaterialTraceability />
                        </Suspense>
                      }
                    />
                    <Route
                      path="command-center"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <CommandCenter />
                        </Suspense>
                      }
                    />
                    <Route
                      path="access-requests"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminAccessRequests />
                        </Suspense>
                      }
                    />
                    <Route
                      path="catalogs"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminCatalogs />
                        </Suspense>
                      }
                    />
                    <Route
                      path="price-levels"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminPriceLevels />
                        </Suspense>
                      }
                    />
                    <Route
                      path="settings"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminSettings />
                        </Suspense>
                      }
                    />
                    <Route
                      path="security"
                      element={
                        <Suspense fallback={<PageLoader />}>
                          <AdminSecurity />
                        </Suspense>
                      }
                    />
                  </Route>

                  {/* Catch-all 404 - must be last */}
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </BrowserRouter>
            </ToastProvider>
          </ApiContext.Provider>
        </LocaleProvider>
      </AppProvider>
    </ErrorBoundary>
  );
}
