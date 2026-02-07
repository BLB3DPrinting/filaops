/**
 * GLReportsTab - General Ledger reports: Trial Balance, Inventory Valuation, Transaction Ledger.
 */
/* eslint-disable react-hooks/exhaustive-deps */
import { useState, useEffect } from "react";
import { API_URL } from "../../config/api";
import { ErrorAlert, TableSkeleton, CardSkeleton, HelpIcon } from "./AccountingShared";

export default function GLReportsTab() {
  const [activeReport, setActiveReport] = useState("trial-balance");
  const [trialBalance, setTrialBalance] = useState(null);
  const [inventoryVal, setInventoryVal] = useState(null);
  const [ledger, setLedger] = useState(null);
  const [selectedAccount, setSelectedAccount] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchTrialBalance = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/accounting/trial-balance`, {
        credentials: "include",
      });
      if (res.ok) {
        setTrialBalance(await res.json());
        setLastUpdated(new Date());
      } else {
        setError(`Failed to load: ${res.status}`);
      }
    } catch (err) {
      setError(`Network error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchInventoryValuation = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/accounting/inventory-valuation`, {
        credentials: "include",
      });
      if (res.ok) {
        setInventoryVal(await res.json());
        setLastUpdated(new Date());
      } else {
        setError(`Failed to load: ${res.status}`);
      }
    } catch (err) {
      setError(`Network error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const fetchLedger = async (accountCode) => {
    if (!accountCode) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/api/v1/accounting/ledger/${accountCode}`, {
        credentials: "include",
      });
      if (res.ok) {
        setLedger(await res.json());
        setLastUpdated(new Date());
      } else {
        setError(`Failed to load: ${res.status}`);
      }
    } catch (err) {
      setError(`Network error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = () => {
    if (activeReport === "trial-balance") fetchTrialBalance();
    else if (activeReport === "inventory") fetchInventoryValuation();
    else if (activeReport === "ledger" && selectedAccount) fetchLedger(selectedAccount);
  };

  const formatLastUpdated = (date) => {
    if (!date) return "";
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  };

  useEffect(() => {
    if (activeReport === "trial-balance") fetchTrialBalance();
    if (activeReport === "inventory") fetchInventoryValuation();
  }, [activeReport]);

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
    }).format(amount || 0);
  };

  return (
    <div className="space-y-4">
      {/* Report Selector with Refresh */}
      <div className="flex items-center justify-between gap-2 bg-gray-900 border border-gray-800 rounded-xl p-2">
        <div className="flex gap-2">
          <button
            onClick={() => setActiveReport("trial-balance")}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              activeReport === "trial-balance"
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:bg-gray-800"
            }`}
          >
            Trial Balance
          </button>
          <button
            onClick={() => setActiveReport("inventory")}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              activeReport === "inventory"
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:bg-gray-800"
            }`}
          >
            Inventory Valuation
          </button>
          <button
            onClick={() => setActiveReport("ledger")}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              activeReport === "ledger"
                ? "bg-blue-600 text-white"
                : "text-gray-400 hover:bg-gray-800"
            }`}
          >
            Transaction Ledger
          </button>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-gray-500">
              Updated {formatLastUpdated(lastUpdated)}
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={loading}
            className="p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
            title="Refresh data"
          >
            <svg
              className={`w-4 h-4 ${loading ? "animate-spin" : ""}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Loading skeleton based on active report */}
      {loading && activeReport === "trial-balance" && <TableSkeleton rows={8} cols={3} />}
      {loading && activeReport === "inventory" && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <CardSkeleton />
            <CardSkeleton />
            <CardSkeleton />
          </div>
          <TableSkeleton rows={4} cols={5} />
        </div>
      )}
      {loading && activeReport === "ledger" && <TableSkeleton rows={10} cols={6} />}

      {/* Error display with retry */}
      {error && (
        <ErrorAlert
          message={error}
          onRetry={() => {
            if (activeReport === "trial-balance") fetchTrialBalance();
            else if (activeReport === "inventory") fetchInventoryValuation();
            else if (activeReport === "ledger" && selectedAccount) fetchLedger(selectedAccount);
          }}
        />
      )}

      {/* Trial Balance */}
      {activeReport === "trial-balance" && trialBalance && !loading && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
          <div className="p-4 border-b border-gray-800 flex justify-between items-center">
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-semibold text-white">Trial Balance</h3>
                <HelpIcon label="Shows all GL account balances. Debits should equal credits. Click any account to view its transaction ledger." />
              </div>
              <p className="text-sm text-gray-400">As of {trialBalance.as_of_date}</p>
            </div>
            <div className={`px-3 py-1 rounded-full text-sm font-medium ${
              trialBalance.is_balanced
                ? "bg-green-500/20 text-green-400"
                : "bg-red-500/20 text-red-400"
            }`}>
              {trialBalance.is_balanced ? "Balanced" : "Out of Balance"}
            </div>
          </div>
          <table className="w-full">
            <thead className="bg-gray-800/50">
              <tr>
                <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">Account</th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">Debit</th>
                <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">Credit</th>
              </tr>
            </thead>
            <tbody>
              {trialBalance.accounts?.map((acct) => (
                <tr key={acct.account_code} className="border-t border-gray-800 hover:bg-gray-800/50 cursor-pointer"
                    onClick={() => { setSelectedAccount(acct.account_code); setActiveReport("ledger"); fetchLedger(acct.account_code); }}>
                  <td className="py-3 px-4">
                    <span className="text-gray-500 mr-2">{acct.account_code}</span>
                    <span className="text-white">{acct.account_name}</span>
                  </td>
                  <td className="py-3 px-4 text-right text-white">
                    {acct.debit_balance > 0 ? formatCurrency(acct.debit_balance) : "-"}
                  </td>
                  <td className="py-3 px-4 text-right text-white">
                    {acct.credit_balance > 0 ? formatCurrency(acct.credit_balance) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="bg-gray-800/50 font-semibold">
              <tr>
                <td className="py-3 px-4 text-white">Total</td>
                <td className="py-3 px-4 text-right text-white">{formatCurrency(trialBalance.total_debits)}</td>
                <td className="py-3 px-4 text-right text-white">{formatCurrency(trialBalance.total_credits)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {/* Inventory Valuation */}
      {activeReport === "inventory" && inventoryVal && !loading && (
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-white">Inventory Valuation</h3>
            <HelpIcon label="Compares physical inventory value to GL balances. Variances indicate missing journal entries or manual adjustments that weren't recorded." />
          </div>
          {/* Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <div className="text-gray-400 text-sm mb-1">Inventory Value</div>
              <div className="text-2xl font-bold text-white">{formatCurrency(inventoryVal.total_inventory_value)}</div>
            </div>
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
              <div className="text-gray-400 text-sm mb-1">GL Balance</div>
              <div className="text-2xl font-bold text-white">{formatCurrency(inventoryVal.total_gl_balance)}</div>
            </div>
            <div className={`bg-gray-900 border rounded-xl p-5 ${
              inventoryVal.is_reconciled ? "border-green-500/50" : "border-red-500/50"
            }`}>
              <div className="text-gray-400 text-sm mb-1">Variance</div>
              <div className={`text-2xl font-bold ${
                inventoryVal.is_reconciled ? "text-green-400" : "text-red-400"
              }`}>
                {formatCurrency(inventoryVal.total_variance)}
              </div>
              <div className="text-xs mt-1">
                {inventoryVal.is_reconciled ? "Reconciled" : "Needs Review"}
              </div>
            </div>
          </div>

          {/* Category Breakdown */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
            <div className="p-4 border-b border-gray-800">
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-semibold text-white">By Category</h3>
                <HelpIcon label="Breakdown by inventory type: Raw Materials (1200), Components (1200), Finished Goods (1220)." />
              </div>
            </div>
            <table className="w-full">
              <thead className="bg-gray-800/50">
                <tr>
                  <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">Category</th>
                  <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">Items</th>
                  <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">Inventory</th>
                  <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">GL Balance</th>
                  <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">Variance</th>
                </tr>
              </thead>
              <tbody>
                {inventoryVal.categories?.map((cat) => (
                  <tr key={cat.gl_account_code} className="border-t border-gray-800">
                    <td className="py-3 px-4">
                      <span className="text-white">{cat.category}</span>
                      <span className="text-gray-500 text-sm ml-2">({cat.gl_account_code})</span>
                    </td>
                    <td className="py-3 px-4 text-right text-gray-400">{cat.item_count}</td>
                    <td className="py-3 px-4 text-right text-white">{formatCurrency(cat.inventory_value)}</td>
                    <td className="py-3 px-4 text-right text-white">{formatCurrency(cat.gl_balance)}</td>
                    <td className={`py-3 px-4 text-right font-medium ${
                      Math.abs(cat.variance) < 0.01 ? "text-green-400" : "text-red-400"
                    }`}>
                      {formatCurrency(cat.variance)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Transaction Ledger */}
      {activeReport === "ledger" && (
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-semibold text-white">Transaction Ledger</h3>
            <HelpIcon label="Detailed transaction history for a specific GL account. Shows all journal entries affecting the account with running balance." />
          </div>
          {/* Account Selector */}
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
            <div className="flex gap-4 items-end">
              <div className="flex-1">
                <label className="block text-xs text-gray-400 mb-1">Account Code</label>
                <input
                  type="text"
                  value={selectedAccount}
                  onChange={(e) => setSelectedAccount(e.target.value)}
                  placeholder="e.g., 1200"
                  className="w-full bg-gray-800 border border-gray-700 text-white rounded px-3 py-2 text-sm"
                />
              </div>
              <button
                onClick={() => fetchLedger(selectedAccount)}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
              >
                Load Ledger
              </button>
            </div>
          </div>

          {/* Ledger Table */}
          {ledger && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
              <div className="p-4 border-b border-gray-800">
                <h3 className="text-lg font-semibold text-white">
                  {ledger.account_code} - {ledger.account_name}
                </h3>
                <p className="text-sm text-gray-400">
                  {ledger.transaction_count} transactions |
                  Opening: {formatCurrency(ledger.opening_balance)} |
                  Closing: {formatCurrency(ledger.closing_balance)}
                </p>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-800/50">
                    <tr>
                      <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">Date</th>
                      <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">Entry</th>
                      <th className="text-left py-3 px-4 text-xs font-medium text-gray-400 uppercase">Description</th>
                      <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">Debit</th>
                      <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">Credit</th>
                      <th className="text-right py-3 px-4 text-xs font-medium text-gray-400 uppercase">Balance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledger.transactions?.map((txn, idx) => (
                      <tr key={idx} className="border-t border-gray-800 hover:bg-gray-800/50">
                        <td className="py-3 px-4 text-gray-400 text-sm">{txn.entry_date}</td>
                        <td className="py-3 px-4 text-white font-mono text-sm">{txn.entry_number}</td>
                        <td className="py-3 px-4 text-gray-300 text-sm">{txn.description}</td>
                        <td className="py-3 px-4 text-right text-white">
                          {txn.debit > 0 ? formatCurrency(txn.debit) : "-"}
                        </td>
                        <td className="py-3 px-4 text-right text-white">
                          {txn.credit > 0 ? formatCurrency(txn.credit) : "-"}
                        </td>
                        <td className="py-3 px-4 text-right text-blue-400 font-medium">
                          {formatCurrency(txn.running_balance)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
