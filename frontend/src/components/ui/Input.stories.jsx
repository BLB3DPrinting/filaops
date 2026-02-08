import Input from "./Input";

export default {
  title: "UI/Input",
  component: Input,
  argTypes: {
    type: { control: "select", options: ["text", "email", "number", "password"] },
  },
  decorators: [(Story) => <div className="max-w-sm"><Story /></div>],
};

export const Default = {
  args: { label: "Email", type: "email", placeholder: "user@example.com" },
};

export const WithHelp = {
  args: { label: "SKU", placeholder: "PROD-001", helpText: "Unique product identifier" },
};

export const WithError = {
  args: { label: "Email", type: "email", value: "invalid", error: "Please enter a valid email address" },
};

export const Password = {
  args: { label: "Password", type: "password", placeholder: "Enter password" },
};

export const Number = {
  args: { label: "Quantity", type: "number", placeholder: "0", min: 0 },
};

export const Required = {
  args: { label: "Name *", placeholder: "Required field", required: true },
};
