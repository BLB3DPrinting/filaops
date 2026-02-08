import Button from "./Button";

export default {
  title: "UI/Button",
  component: Button,
  argTypes: {
    variant: {
      control: "select",
      options: ["primary", "secondary", "danger", "ghost"],
    },
    size: { control: "select", options: ["sm", "md", "lg"] },
    loading: { control: "boolean" },
    disabled: { control: "boolean" },
  },
};

export const Primary = { args: { children: "Save Changes", variant: "primary" } };

export const Secondary = { args: { children: "Cancel", variant: "secondary" } };

export const Danger = { args: { children: "Delete", variant: "danger" } };

export const Ghost = { args: { children: "More Options", variant: "ghost" } };

export const Small = { args: { children: "Small", size: "sm" } };

export const Large = { args: { children: "Large Button", size: "lg" } };

export const Loading = { args: { children: "Saving...", loading: true } };

export const Disabled = { args: { children: "Disabled", disabled: true } };

export const WithIcon = {
  args: {
    children: "Add Item",
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
      </svg>
    ),
  },
};

export const AllVariants = {
  render: () => (
    <div className="flex flex-wrap gap-3">
      <Button variant="primary">Primary</Button>
      <Button variant="secondary">Secondary</Button>
      <Button variant="danger">Danger</Button>
      <Button variant="ghost">Ghost</Button>
    </div>
  ),
};

export const AllSizes = {
  render: () => (
    <div className="flex items-center gap-3">
      <Button size="sm">Small</Button>
      <Button size="md">Medium</Button>
      <Button size="lg">Large</Button>
    </div>
  ),
};
