import { useNavigate } from "react-router-dom";
import { SALES_ORDER_COLORS, getStatusColor } from "../../lib/statusColors.js";

export default function RecentOrderRow({ order }) {
  const navigate = useNavigate();

  return (
    <tr
      onClick={() => navigate(`/admin/orders/${order.id}`)}
      className="border-b border-gray-800 hover:bg-gray-800/70 cursor-pointer transition-colors"
    >
      <td className="py-3 px-4 text-white font-medium">{order.order_number}</td>
      <td className="py-3 px-4 text-gray-400">
        {order.product_name || order.customer_name}
      </td>
      <td className="py-3 px-4">
        <span
          className={`px-2 py-1 rounded-full text-xs ${
            getStatusColor(SALES_ORDER_COLORS, order.status)
          }`}
        >
          {order.status?.replace(/_/g, " ")}
        </span>
      </td>
      <td className="py-3 px-4 text-gray-400">
        ${parseFloat(order.grand_total || order.total_price || 0).toFixed(2)}
      </td>
      <td className="py-3 px-2 text-gray-600">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
        </svg>
      </td>
    </tr>
  );
}
