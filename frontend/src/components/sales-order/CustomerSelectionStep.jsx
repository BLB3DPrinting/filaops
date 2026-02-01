/**
 * CustomerSelectionStep - Step 1 of the Sales Order Wizard.
 * Customer selection dropdown, customer info display, shipping address form, and order notes.
 */
export default function CustomerSelectionStep({
  customers,
  orderData,
  setOrderData,
  selectedCustomer,
  onNavigateToNewCustomer,
}) {
  return (
    <div className="space-y-6">
      <h3 className="text-lg font-semibold text-white">
        Select Customer
      </h3>

      <div className="flex gap-4">
        <div className="flex-1">
          <select
            value={orderData.customer_id || ""}
            onChange={(e) => {
              const cid = e.target.value
                ? parseInt(e.target.value)
                : null;
              const customer = customers.find((c) => c.id === cid);
              setOrderData({
                ...orderData,
                customer_id: cid,
                shipping_address_line1:
                  customer?.shipping_address_line1 || "",
                shipping_city: customer?.shipping_city || "",
                shipping_state: customer?.shipping_state || "",
                shipping_zip: customer?.shipping_zip || "",
              });
            }}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-white"
          >
            <option value="">-- Walk-in / No Customer --</option>
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.customer_number || `#${c.id}`} -{" "}
                {c.full_name || c.name || c.email}{" "}
                {c.company_name ? `(${c.company_name})` : ""}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={() => onNavigateToNewCustomer()}
          className="px-4 py-2 bg-gray-800 border border-gray-700 text-gray-300 rounded-lg hover:bg-gray-700 hover:text-white whitespace-nowrap"
        >
          + New Customer
        </button>
      </div>

      {selectedCustomer && (
        <div className="bg-gray-800/50 rounded-lg p-4 border border-gray-700">
          <div className="text-white font-medium">
            {selectedCustomer.name}
          </div>
          {selectedCustomer.company && (
            <div className="text-gray-400 text-sm">
              {selectedCustomer.company}
            </div>
          )}
          <div className="text-gray-400 text-sm">
            {selectedCustomer.email}
          </div>
          {selectedCustomer.phone && (
            <div className="text-gray-400 text-sm">
              {selectedCustomer.phone}
            </div>
          )}
        </div>
      )}

      <div className="space-y-4">
        <h4 className="text-md font-medium text-white">
          Shipping Address
        </h4>
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Address
          </label>
          <input
            type="text"
            value={orderData.shipping_address_line1}
            onChange={(e) =>
              setOrderData({
                ...orderData,
                shipping_address_line1: e.target.value,
              })
            }
            placeholder="Street address"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
          />
        </div>
        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              City
            </label>
            <input
              type="text"
              value={orderData.shipping_city}
              onChange={(e) =>
                setOrderData({
                  ...orderData,
                  shipping_city: e.target.value,
                })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              State
            </label>
            <input
              type="text"
              value={orderData.shipping_state}
              onChange={(e) =>
                setOrderData({
                  ...orderData,
                  shipping_state: e.target.value,
                })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-1">
              ZIP
            </label>
            <input
              type="text"
              value={orderData.shipping_zip}
              onChange={(e) =>
                setOrderData({
                  ...orderData,
                  shipping_zip: e.target.value,
                })
              }
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
            />
          </div>
        </div>
        <div>
          <label className="block text-sm text-gray-400 mb-1">
            Order Notes
          </label>
          <textarea
            value={orderData.customer_notes}
            onChange={(e) =>
              setOrderData({
                ...orderData,
                customer_notes: e.target.value,
              })
            }
            rows={2}
            placeholder="Special instructions..."
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white"
          />
        </div>
      </div>
    </div>
  );
}
