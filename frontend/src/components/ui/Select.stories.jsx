import Select from "./Select";

export default {
  title: "UI/Select",
  component: Select,
  decorators: [(Story) => <div className="max-w-sm"><Story /></div>],
};

const statusOptions = [
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
  { value: "archived", label: "Archived" },
];

export const Default = {
  args: { label: "Status", options: statusOptions, placeholder: "Select status..." },
};

export const WithError = {
  args: { label: "Category", options: statusOptions, error: "Please select a category" },
};

export const WithHelp = {
  args: {
    label: "Warehouse",
    options: [
      { value: "main", label: "Main Warehouse" },
      { value: "overflow", label: "Overflow Storage" },
    ],
    placeholder: "Choose warehouse...",
    helpText: "Where the item will be stored",
  },
};

export const NoPlaceholder = {
  args: { label: "Priority", options: [
    { value: "low", label: "Low" },
    { value: "medium", label: "Medium" },
    { value: "high", label: "High" },
  ]},
};
