/**
 * orderWorkflowUtils - order status sets + money formatter shared by
 * OrderDetail and the components extracted from it (DEBT-1 D1-C).
 *
 * Lives in its own module (not a component file) so react-refresh fast
 * refresh keeps working for the component files.
 */
export const formatMoney = (value) => `$${parseFloat(value || 0).toFixed(2)}`;

export const SHIPPED_ORDER_STATUSES = new Set(["shipped", "delivered", "completed"]);
export const UNCONFIRMED_ORDER_STATUSES = new Set(["draft", "pending", "pending_confirmation"]);
