import Badge from "./Badge";

export default {
  title: "UI/Badge",
  component: Badge,
  argTypes: {
    variant: {
      control: "select",
      options: ["success", "warning", "danger", "info", "neutral", "purple"],
    },
    size: { control: "select", options: ["sm", "md"] },
    dot: { control: "boolean" },
  },
};

export const Success = { args: { children: "Active", variant: "success" } };

export const Warning = { args: { children: "Pending", variant: "warning" } };

export const Danger = { args: { children: "Overdue", variant: "danger" } };

export const Info = { args: { children: "Processing", variant: "info" } };

export const Neutral = { args: { children: "Draft", variant: "neutral" } };

export const Purple = { args: { children: "Custom", variant: "purple" } };

export const WithDot = { args: { children: "Active", variant: "success", dot: true } };

export const Small = { args: { children: "SM", variant: "info", size: "sm" } };

export const AllVariants = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <Badge variant="success">Active</Badge>
      <Badge variant="warning">Pending</Badge>
      <Badge variant="danger">Overdue</Badge>
      <Badge variant="info">Processing</Badge>
      <Badge variant="neutral">Draft</Badge>
      <Badge variant="purple">Custom</Badge>
    </div>
  ),
};

export const StatusBadges = {
  render: () => (
    <div className="flex flex-wrap gap-2">
      <Badge variant="success" dot>Completed</Badge>
      <Badge variant="warning" dot>In Progress</Badge>
      <Badge variant="danger" dot>Failed</Badge>
      <Badge variant="info" dot>Queued</Badge>
      <Badge variant="neutral" dot>Cancelled</Badge>
    </div>
  ),
};
