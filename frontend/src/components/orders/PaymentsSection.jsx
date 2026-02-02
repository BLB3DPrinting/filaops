/**
 * PaymentsSection - Payment summary, history, and record/refund actions.
 *
 * Extracted from OrderDetail.jsx (ARCHITECT-002)
 */

export default function PaymentsSection({
  payments,
  paymentSummary,
  onRecordPayment,
  onRefund,
}) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
      <div className="flex justify-between items-center mb-4">
        <h2 className="text-lg font-semibold text-white">Payments</h2>
        <div className="flex gap-2">
          {paymentSummary && paymentSummary.total_paid > 0 && (
            <button
              onClick={onRefund}
              className="px-3 py-1 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded text-sm"
            >
              Refund
            </button>
          )}
          <button
            onClick={onRecordPayment}
            className="px-3 py-1 bg-green-600 hover:bg-green-700 text-white rounded text-sm flex items-center gap-1"
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
        <div className="grid grid-cols-4 gap-4 mb-4 p-4 bg-gray-800/50 rounded-lg">
          <div>
            <div className="text-sm text-gray-400">Order Total</div>
            <div className="text-white font-medium">
              ${parseFloat(paymentSummary.order_total || 0).toFixed(2)}
            </div>
          </div>
          <div>
            <div className="text-sm text-gray-400">Paid</div>
            <div className="text-green-400 font-medium">
              ${parseFloat(paymentSummary.total_paid || 0).toFixed(2)}
            </div>
          </div>
          {paymentSummary.total_refunded > 0 && (
            <div>
              <div className="text-sm text-gray-400">Refunded</div>
              <div className="text-red-400 font-medium">
                ${parseFloat(paymentSummary.total_refunded || 0).toFixed(2)}
              </div>
            </div>
          )}
          <div>
            <div className="text-sm text-gray-400">Balance Due</div>
            <div
              className={`font-medium ${
                paymentSummary.balance_due > 0
                  ? "text-yellow-400"
                  : "text-green-400"
              }`}
            >
              ${parseFloat(paymentSummary.balance_due || 0).toFixed(2)}
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
              className="flex justify-between items-center p-3 bg-gray-800 rounded-lg"
            >
              <div className="flex items-center gap-3">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center ${
                    payment.amount < 0 ? "bg-red-500/20" : "bg-green-500/20"
                  }`}
                >
                  {payment.amount < 0 ? (
                    <svg
                      className="w-4 h-4 text-red-400"
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
                      className="w-4 h-4 text-green-400"
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
                  <div className="text-white font-medium">
                    {payment.payment_number}
                  </div>
                  <div className="text-sm text-gray-400">
                    {payment.payment_method}
                    {payment.check_number && ` #${payment.check_number}`}
                    {payment.transaction_id && ` - ${payment.transaction_id}`}
                  </div>
                </div>
              </div>
              <div className="text-right">
                <div
                  className={`font-medium ${
                    payment.amount < 0 ? "text-red-400" : "text-green-400"
                  }`}
                >
                  ${Math.abs(parseFloat(payment.amount)).toFixed(2)}
                </div>
                <div className="text-xs text-gray-500">
                  {new Date(payment.payment_date).toLocaleDateString()}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-6 text-gray-500">
          No payments recorded yet
        </div>
      )}
    </div>
  );
}
