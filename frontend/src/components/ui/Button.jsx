import { forwardRef } from "react";

const VARIANT_CLASSES = {
  primary:
    "bg-accent hover:bg-accent-press text-accent-ink font-semibold disabled:bg-paper-sunk disabled:text-ink-4 disabled:border-hair",
  secondary:
    "bg-paper hover:bg-paper-sunk text-ink border-hair disabled:bg-paper-sunk disabled:text-ink-4",
  danger:
    "bg-status-red hover:brightness-90 text-paper font-semibold disabled:bg-paper-sunk disabled:text-ink-4 disabled:border-hair",
  ghost:
    "bg-transparent border-transparent hover:bg-paper-sunk text-ink-2 hover:text-ink disabled:text-ink-4",
};

const SIZE_CLASSES = {
  sm: "h-7 px-3 text-xs gap-1.5 rounded",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-11 px-5 text-base gap-2",
};

function Spinner() {
  return (
    <svg
      className="animate-spin h-4 w-4"
      fill="none"
      viewBox="0 0 24 24"
      aria-hidden="true"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      />
    </svg>
  );
}

const Button = forwardRef(function Button(
  {
    variant = "primary",
    size = "md",
    loading = false,
    disabled = false,
    icon,
    children,
    className = "",
    type = "button",
    ...rest
  },
  ref
) {
  const variantClasses = VARIANT_CLASSES[variant] || VARIANT_CLASSES.primary;
  const sizeClasses = SIZE_CLASSES[size] || SIZE_CLASSES.md;

  return (
    <button
      ref={ref}
      type={type}
      disabled={disabled || loading}
      className={`inline-flex items-center justify-center font-medium rounded-lg border border-transparent transition-colors disabled:cursor-not-allowed ${variantClasses} ${sizeClasses} ${className}`}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  );
});

export default Button;
