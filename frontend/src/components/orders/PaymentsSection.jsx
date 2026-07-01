/**
 * PaymentsSection - Payment summary, history, and record/refund actions.
 *
 * Extracted from OrderDetail.jsx (ARCHITECT-002)
 */
import { useFormatCurrency } from "../../hooks/useFormatCurrency";

export default function PaymentsSection({
  payments,
  paymentSummary,
  onRecordPayment,
  onRefund,
}) {
  const formatCurrency = useFormatCurrency();

  return (
    <div className="bg-[var(--paper)] border border-[var(--rule-hair)] rounded-xl p-6 shadow-[var(--shadow-pop)]">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-[var(--ink)]">Payments</h2>
        <div className="flex gap-2">
          {paymentSummary && paymentSummary.total_paid > 0 && (
            <button
              onClick={onRefund}
              className="px-3 py-1 bg-[var(--status-red-tint)] hover:bg-[var(--status-red-tint)] text-[var(--status-red)] rounded text-sm"
            >
              Refund
            </button>
          )}
          <button
            onClick={onRecordPayment}
            className="px-3 py-1 bg-[var(--orange)] hover:bg-[var(--orange-press)] text-white rounded text-sm flex items-center gap-1"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 6v6m0 0v6m0-6h6m-6 0H6"
              />
            </svg>
            Record Payment
          </button>
        </div>
      </div>

      {/* Payment Summary */}
      {paymentSummary && (
        <div className="grid grid-cols-4 gap-4 mb-4 p-4 bg-[var(--paper-sunk)] rounded-lg">
          <div>
            <div className="text-sm text-[var(--ink-3)]">Order Total</div>
            <div className="text-[var(--ink)] font-medium">
              {formatCurrency(parseFloat(paymentSummary.order_total || 0))}
            </div>
          </div>
          <div>
            <div className="text-sm text-[var(--ink-3)]">Paid</div>
            <div className="text-[var(--status-green)] font-medium">
              {formatCurrency(parseFloat(paymentSummary.total_paid || 0))}
            </div>
          </div>
          {paymentSummary.total_refunded > 0 && (
            <div>
              <div className="text-sm text-[var(--ink-3)]">Refunded</div>
              <div className="text-[var(--status-red)] font-medium">
                {formatCurrency(parseFloat(paymentSummary.total_refunded || 0))}
              </div>
            </div>
          )}
          <div>
            <div className="text-sm text-[var(--ink-3)]">Balance Due</div>
            <div
              className={`font-medium ${
                paymentSummary.balance_due > 0
                  ? "text-[var(--status-amber)]"
                  : "text-[var(--status-green)]"
              }`}
            >
              {formatCurrency(parseFloat(paymentSummary.balance_due || 0))}
            </div>
          </div>
        </div>
      )}

      {/* Payment History */}
      {payments.length > 0 ? (
        <div className="space-y-2">
          {payments.map((payment) => (
            <div
              key={payment.id}
              className="flex justify-between items-center p-3 bg-[var(--paper-sunk)] rounded-lg"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    payment.amount < 0 ? "bg-[var(--status-red-tint)]" : "bg-[var(--status-green-tint)]"
                  }`}
                >
                  {payment.amount < 0 ? (
                    <svg
                      className="w-4 h-4 text-[var(--status-red)]"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"
                      />
                    </svg>
                  ) : (
                    <svg
                      className="w-4 h-4 text-[var(--status-green)]"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M12 6v6m0 0v6m0-6h6m-6 0H6"
                      />
                    </svg>
                  )}
                </div>
                <div>
                  <div className="text-[var(--ink)] font-medium">
                    {payment.payment_number}
                  </div>
                  <div className="text-sm text-[var(--ink-3)]">
                    {payment.payment_method}
                    {payment.check_number && ` #${payment.check_number}`}
                    {payment.transaction_id && ` - ${payment.transaction_id}`}
                  </div>
                </div>
              </div>
              <div className="text-right">
                <div
                  className={`font-medium ${
                    payment.amount < 0 ? "text-[var(--status-red)]" : "text-[var(--status-green)]"
                  }`}
                >
                  {formatCurrency(Math.abs(parseFloat(payment.amount)))}
                </div>
                <div className="text-xs text-[var(--ink-4)]">
                  {new Date(payment.payment_date).toLocaleDateString()}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-6 text-[var(--ink-4)]">
          No payments recorded yet
        </div>
      )}
    </div>
  );
}
