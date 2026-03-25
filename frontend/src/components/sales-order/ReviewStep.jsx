/**
 * ReviewStep - Step 3 of the Sales Order Wizard.
 * Displays order summary: customer info, shipping, line items with totals, tax, and notes.
 * Supports both product and raw material line items.
 */
export default function ReviewStep({
  selectedCustomer,
  orderData,
  lineItems,
  orderTotal,
  taxSettings,
  customerDiscount = null,
}) {
  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-white">Review Order</h3>

      {/* Customer Discount Notice */}
      {customerDiscount && (
        <div className="bg-green-900/20 border border-green-500/30 rounded-lg px-4 py-3 flex items-center gap-2">
          <span className="text-green-400 font-medium text-sm">
            {customerDiscount}% customer discount will be applied at checkout
          </span>
        </div>
      )}

      {/* Customer Info */}
      <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
        <h4 className="text-md font-medium text-white mb-3">
          Customer
        </h4>
        {selectedCustomer ? (
          <div>
            <div className="text-white">{selectedCustomer.name}</div>
            {selectedCustomer.company && (
              <div className="text-gray-400 text-sm">
                {selectedCustomer.company}
              </div>
            )}
            <div className="text-gray-400 text-sm">
              {selectedCustomer.email}
            </div>
          </div>
        ) : (
          <div className="text-gray-500">
            Walk-in / No customer selected
          </div>
        )}
      </div>

      {/* Shipping */}
      {orderData.shipping_address_line1 && (
        <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
          <h4 className="text-md font-medium text-white mb-3">
            Ship To
          </h4>
          <div className="text-gray-300 text-sm">
            {orderData.shipping_address_line1}
            <br />
            {orderData.shipping_city}, {orderData.shipping_state}{" "}
            {orderData.shipping_zip}
          </div>
        </div>
      )}

      {/* Line Items */}
      <div className="bg-gray-800/50 rounded-lg border border-gray-700">
        <div className="p-4 border-b border-gray-700">
          <h4 className="text-md font-medium text-white">
            Order Lines
          </h4>
        </div>
        <table className="w-full">
          <thead className="bg-gray-800/50">
            <tr>
              <th className="text-left py-2 px-4 text-xs font-medium text-gray-400">
                Item
              </th>
              <th className="text-right py-2 px-4 text-xs font-medium text-gray-400">
                Qty
              </th>
              <th className="text-right py-2 px-4 text-xs font-medium text-gray-400">
                Price
              </th>
              <th className="text-right py-2 px-4 text-xs font-medium text-gray-400">
                Total
              </th>
            </tr>
          </thead>
          <tbody>
            {lineItems.map((li) => {
              const isMaterial = li.line_type === "material";
              const name = isMaterial
                ? li.material?.name
                : li.product?.name;
              const sku = isMaterial
                ? li.material?.sku
                : li.product?.sku;

              return (
                <tr
                  key={li._key}
                  className="border-t border-gray-800"
                >
                  <td className="py-3 px-4">
                    <div className="flex items-center gap-2">
                      {isMaterial && (
                        <span className="px-1.5 py-0.5 text-[10px] font-semibold bg-orange-500/20 text-orange-400 border border-orange-500/30 rounded">
                          RAW
                        </span>
                      )}
                      <div>
                        <div className="text-white">{name}</div>
                        <div className="text-gray-500 text-xs font-mono">
                          {sku}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="py-3 px-4 text-right text-gray-300">
                    {li.quantity}
                  </td>
                  <td className="py-3 px-4 text-right text-gray-300">
                    ${parseFloat(li.unit_price).toFixed(2)}
                  </td>
                  <td className="py-3 px-4 text-right text-green-400 font-medium">
                    ${(li.quantity * li.unit_price).toFixed(2)}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot className="bg-gray-800/80">
            <tr>
              <td
                colSpan={3}
                className="py-3 px-4 text-right text-gray-400"
              >
                Subtotal
              </td>
              <td className="py-3 px-4 text-right text-white font-medium">
                ${orderTotal.toFixed(2)}
              </td>
            </tr>
            {taxSettings.tax_enabled && taxSettings.tax_rate > 0 && (
              <tr>
                <td
                  colSpan={3}
                  className="py-3 px-4 text-right text-gray-400"
                >
                  {taxSettings.tax_name} ({(taxSettings.tax_rate * 100).toFixed(2)}%)
                </td>
                <td className="py-3 px-4 text-right text-white font-medium">
                  ${(orderTotal * taxSettings.tax_rate).toFixed(2)}
                </td>
              </tr>
            )}
            <tr className="border-t border-gray-700">
              <td
                colSpan={3}
                className="py-3 px-4 text-right text-white font-medium"
              >
                Grand Total
              </td>
              <td className="py-3 px-4 text-right text-green-400 font-bold text-lg">
                ${(taxSettings.tax_enabled && taxSettings.tax_rate > 0
                  ? orderTotal * (1 + taxSettings.tax_rate)
                  : orderTotal
                ).toFixed(2)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Notes */}
      {orderData.customer_notes && (
        <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
          <h4 className="text-md font-medium text-white mb-2">
            Order Notes
          </h4>
          <p className="text-gray-300 text-sm">
            {orderData.customer_notes}
          </p>
        </div>
      )}
    </div>
  );
}
