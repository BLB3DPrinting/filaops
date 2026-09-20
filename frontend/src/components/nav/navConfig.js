/**
 * Admin sidebar structure: groups, destinations, and their access gates.
 *
 * Extracted verbatim from AdminLayout.jsx. Entries carry adminOnly / proOnly /
 * feature flags; AdminLayout filters on them at render time.
 */

import {
  BOMIcon,
  OrdersIcon,
  QuotesIcon,
  PaymentsIcon,
  MessagesIcon,
  ProductionIcon,
  ShippingIcon,
  ItemsIcon,
  PurchasingIcon,
  WorkCentersIcon,
  PrintersIcon,
  CustomersIcon,
  MaterialImportIcon,
  InventoryIcon,
  AnalyticsIcon,
  AccountingIcon,
  IntegrationsIcon,
  SettingsIcon,
  QualityIcon,
  InvoicesIcon,
  CommandCenterIcon,
} from "./navIcons";

const navGroups = [
  {
    label: null, // No header — home screen entry
    items: [
      {
        path: "/admin",
        label: "Command Center",
        icon: CommandCenterIcon,
        end: true,
      },
      {
        path: "/admin/dashboard",
        label: "Analytics",
        icon: AnalyticsIcon,
      },
      {
        // Advanced Analytics (revenue/customer/product/profit dashboard) is a
        // wholly-PRO page behind reports_advanced. It had a route + page but no
        // nav entry — reachable only by typing the URL. Surface it badged so
        // non-PRO sees the upgrade prompt instead of a hidden dead-end.
        path: "/admin/analytics",
        label: "Advanced Analytics",
        icon: AnalyticsIcon,
        adminOnly: true,
        proOnly: true,
        feature: "reports_advanced",
      },
    ],
  },
  {
    label: "SALES",
    items: [
      {
        path: "/admin/customers",
        label: "Customers",
        icon: CustomersIcon,
        adminOnly: true,
      },
      { path: "/admin/quotes", label: "Quotes", icon: QuotesIcon },
      { path: "/admin/orders", label: "Orders", icon: OrdersIcon },
      { path: "/admin/shipping", label: "Shipping", icon: ShippingIcon },
      { path: "/admin/messages", label: "Messages", icon: MessagesIcon },
    ],
  },
  {
    label: "MONEY",
    adminOnly: true,
    items: [
      {
        path: "/admin/invoices",
        label: "Invoices",
        icon: InvoicesIcon,
        adminOnly: true,
      },
      {
        path: "/admin/payments",
        label: "Payments",
        icon: PaymentsIcon,
        adminOnly: true,
      },
      {
        path: "/admin/accounting",
        label: "Accounting",
        icon: AccountingIcon,
        adminOnly: true,
      },
    ],
  },
  {
    label: "OPERATIONS",
    items: [
      { path: "/admin/production", label: "Production", icon: ProductionIcon },
      {
        path: "/admin/manufacturing",
        label: "Work Centers & Routings",
        icon: WorkCentersIcon,
      },
      { path: "/admin/printers", label: "Printers", icon: PrintersIcon },
      {
        path: "/admin/bambuddy",
        label: "Bambuddy",
        icon: PrintersIcon,
        adminOnly: true,
        proOnly: true,
        feature: "bambu_integration",
      },
      {
        path: "/admin/spools",
        label: "Material Spools",
        icon: InventoryIcon,
        adminOnly: true,
      },
      {
        path: "/admin/intake-studio",
        label: "Intake Studio",
        icon: ProductionIcon,
        adminOnly: true,
        // Intake Studio gates access on isPro at the page level (the
        // intake_unified_flow flag only switches the UI variant, it is not
        // the access gate), so this is proOnly with no feature filter —
        // available to every PRO tier. This is the original PRO-leak audit
        // finding (2026-07-01): the item was previously adminOnly-only.
        proOnly: true,
      },
      {
        path: "/admin/intake-batch",
        label: "Intake Batch",
        icon: ProductionIcon,
        adminOnly: true,
        // Same access model as Intake Studio — isPro page gate, no feature.
        proOnly: true,
      },
    ],
  },
  {
    label: "INVENTORY",
    items: [
      { path: "/admin/items", label: "Items", icon: ItemsIcon },
      { path: "/admin/bom", label: "Bill of Materials", icon: BOMIcon },
      {
        path: "/admin/locations",
        label: "Locations",
        icon: InventoryIcon,
        adminOnly: true,
      },
      {
        path: "/admin/inventory/transactions",
        label: "Transactions",
        icon: InventoryIcon,
        adminOnly: true,
      },
      {
        path: "/admin/inventory/cycle-count",
        label: "Cycle Count",
        icon: InventoryIcon,
        adminOnly: true,
      },
    ],
  },
  {
    label: "PURCHASING",
    items: [
      { path: "/admin/purchasing", label: "Purchasing", icon: PurchasingIcon },
      {
        path: "/admin/materials/import",
        label: "Import Materials",
        icon: MaterialImportIcon,
        adminOnly: true,
      },
    ],
  },
  {
    label: "B2B PORTAL",
    adminOnly: true,
    proOnly: true,
    items: [
      {
        path: "/admin/access-requests",
        label: "Access Requests",
        icon: CustomersIcon,
        adminOnly: true,
      },
      {
        path: "/admin/catalogs",
        label: "Catalogs",
        icon: ItemsIcon,
        adminOnly: true,
      },
      {
        path: "/admin/price-levels",
        label: "Price Levels",
        icon: AccountingIcon,
        adminOnly: true,
        proOnly: true,
      },
    ],
  },
  {
    label: "QUALITY",
    items: [
      {
        path: "/admin/quality",
        label: "Quality Dashboard",
        icon: QualityIcon,
      },
      {
        path: "/admin/quality/plans",
        label: "Quality Plans",
        icon: QualityIcon,
      },
      {
        path: "/admin/quality/traceability",
        label: "Material Traceability",
        icon: QualityIcon,
      },
    ],
  },
  {
    label: "ADMIN",
    adminOnly: true,
    items: [
      {
        path: "/admin/users",
        label: "Team Members",
        icon: CustomersIcon,
        adminOnly: true,
      },
      {
        path: "/admin/security",
        label: "Security Audit",
        icon: QualityIcon,
        adminOnly: true,
      },
      {
        path: "/admin/settings",
        label: "Settings",
        icon: SettingsIcon,
        adminOnly: true,
      },
      {
        path: "/admin/integrations",
        label: "Integrations",
        icon: IntegrationsIcon,
        adminOnly: true,
      },
      {
        path: "/admin/license",
        label: "License",
        icon: SettingsIcon,
        adminOnly: true,
      },
      {
        path: "/admin/orders/import",
        label: "Import Orders",
        icon: MaterialImportIcon,
        adminOnly: true,
      },
      {
        path: "/admin/scrap-reasons",
        label: "Scrap Reasons",
        icon: SettingsIcon,
        adminOnly: true,
      },
    ],
  },
];

export { navGroups };
