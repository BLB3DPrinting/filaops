/**
 * SalesOrderCard - Card component for displaying sales order with fulfillment status
 * UI-301 - Week 4 UI Refactor
 */
import React from 'react';
import { formatCurrency } from '../../lib/number';
import { formatDate } from '../../utils/formatting';

// Status badge styles per fulfillment state
const STATUS_STYLES = {
  ready_to_ship: 'bg-green-100 text-green-800',
  partially_ready: 'bg-yellow-100 text-yellow-800',
  blocked: 'bg-red-100 text-red-800',
  shipped: 'bg-gray-100 text-gray-600',
  cancelled: 'bg-gray-100 text-gray-400',
  pending_confirmation: 'bg-purple-100 text-purple-800',
};

// Human-readable labels for fulfillment states
const STATUS_LABELS = {
  ready_to_ship: 'Ready to Ship',
  partially_ready: 'Partially Ready',
  blocked: 'Blocked',
  shipped: 'Shipped',
  cancelled: 'Cancelled',
  pending_confirmation: 'Pending Review',
};

// Source badge styles
const SOURCE_STYLES = {
  api: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  portal: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  squarespace: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  woocommerce: 'bg-violet-500/20 text-violet-300 border-violet-500/30',
};

const SOURCE_LABELS = {
  api: 'API',
  portal: 'Portal',
  squarespace: 'Squarespace',
  woocommerce: 'WooCommerce',
  manual: 'Manual',
  quote: 'Quote',
};

// Sources that don't need a badge (implied by context for admin-originated orders)
const SOURCE_HIDDEN = new Set(['manual', 'quote']);

/**
 * Get progress bar color based on fulfillment percentage
 */
function getProgressColor(percent) {
  if (percent === 100) return 'bg-green-500';
  if (percent >= 50) return 'bg-yellow-500';
  if (percent > 0) return 'bg-orange-500';
  return 'bg-red-500';
}

/**
 * SalesOrderCard component
 *
 * @param {Object} props
 * @param {Object} props.order - Sales order data
 * @param {number} props.order.id - Order ID
 * @param {string} props.order.order_number - Order number (e.g., "SO-2025-0042")
 * @param {string} props.order.customer_name - Customer name
 * @param {string} props.order.order_date - Order date (ISO string)
 * @param {string} [props.order.requested_date] - Requested delivery date
 * @param {string} props.order.status - Order status
 * @param {number} props.order.total - Order total amount
 * @param {Object} [props.order.fulfillment] - Fulfillment status from API-302
 * @param {Function} props.onViewDetails - Called with order ID when View Details clicked
 * @param {Function} [props.onShip] - Called with order ID when Ship button clicked
 */
export default function SalesOrderCard({ order, onViewDetails, onShip }) {
  const { fulfillment } = order;
  // Use pending_confirmation status directly if that's the order status
  const state = order.status === 'pending_confirmation' ? 'pending_confirmation' : (fulfillment?.state || 'blocked');
  const canShip = fulfillment?.can_ship_complete || fulfillment?.can_ship_partial;
  const percent = fulfillment?.fulfillment_percent ?? 0;

  // Get the order total - handle different field names
  const orderTotal = order.total ?? order.grand_total ?? order.total_price ?? 0;

  return (
    <div className="bg-gray-800 rounded-lg shadow-sm border border-gray-700 p-4 hover:shadow-md transition-shadow">
      {/* Header: Order number, customer, and status badge */}
      <div className="flex justify-between items-start mb-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-green-400">{order.order_number}</h3>
            {order.source && !SOURCE_HIDDEN.has(order.source) && (
              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${SOURCE_STYLES[order.source] || 'bg-gray-500/20 text-gray-300 border-gray-500/30'}`}>
                {SOURCE_LABELS[order.source] || order.source}
              </span>
            )}
          </div>
          <p className="text-sm text-gray-300">{order.customer_name || 'No Customer'}</p>
        </div>
        <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_STYLES[state] || STATUS_STYLES.blocked}`}>
          {STATUS_LABELS[state] || state}
        </span>
      </div>

      {/* Fulfillment Progress Bar */}
      {fulfillment && (
        <div className="mb-3">
          <div className="flex justify-between text-sm text-gray-400 mb-1">
            <span>{fulfillment.lines_ready}/{fulfillment.lines_total} lines ready</span>
            <span>{percent}%</span>
          </div>
          <div
            className="w-full bg-gray-600 rounded-full h-2"
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Fulfillment progress: ${percent}%`}
          >
            <div
              className={`h-2 rounded-full transition-all ${getProgressColor(percent)}`}
              style={{ width: `${percent}%` }}
            />
          </div>
        </div>
      )}

      {/* Order Details */}
      <div className="text-sm text-gray-400 mb-3 space-y-1">
        <div className="flex justify-between">
          <span>Order Date:</span>
          <span>{formatDate(order.order_date || order.created_at)}</span>
        </div>
        {order.requested_date && (
          <div className="flex justify-between">
            <span>Requested:</span>
            <span>{formatDate(order.requested_date)}</span>
          </div>
        )}
        <div className="flex justify-between font-medium text-white">
          <span>Total:</span>
          <span>{formatCurrency(orderTotal)}</span>
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex justify-between items-center pt-3 border-t border-gray-700">
        <button
          onClick={() => onViewDetails(order.id)}
          className="text-sm text-blue-400 hover:text-blue-300 font-medium"
        >
          View Details
        </button>

        {canShip && onShip && state !== 'shipped' && state !== 'cancelled' && (
          <button
            onClick={() => onShip(order.id)}
            className="px-3 py-1.5 bg-green-600 text-white text-sm font-medium rounded hover:bg-green-700 transition-colors"
          >
            {fulfillment.can_ship_complete ? 'Ship Now' : 'Ship Partial'} →
          </button>
        )}
      </div>
    </div>
  );
}

