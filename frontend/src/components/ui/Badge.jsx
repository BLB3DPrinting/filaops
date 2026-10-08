import { forwardRef } from "react";

const VARIANT_CLASSES = {
  success: "bg-status-green-tint text-status-green",
  warning: "bg-status-amber-tint text-status-amber",
  danger: "bg-status-red-tint text-status-red",
  info: "bg-status-amber-tint text-status-amber",
  neutral: "bg-paper-sunk text-ink-2",
  purple: "bg-status-amber-tint text-status-amber",
};

const DOT_CLASSES = {
  success: "bg-status-green",
  warning: "bg-status-amber",
  danger: "bg-status-red",
  info: "bg-status-amber",
  neutral: "bg-ink-3",
  purple: "bg-status-amber",
};

const SIZE_CLASSES = {
  sm: "px-2 py-0.5 text-xs",
  md: "px-2.5 py-1 text-xs",
};

const Badge = forwardRef(function Badge(
  {
    variant = "neutral",
    size = "md",
    dot = false,
    children,
    className = "",
    ...rest
  },
  ref
) {
  const variantClasses = VARIANT_CLASSES[variant] || VARIANT_CLASSES.neutral;
  const sizeClasses = SIZE_CLASSES[size] || SIZE_CLASSES.md;
  const dotClass = DOT_CLASSES[variant] || DOT_CLASSES.neutral;

  return (
    <span
      ref={ref}
      className={`inline-flex items-center gap-1.5 font-semibold rounded-full ${variantClasses} ${sizeClasses} ${className}`}
      {...rest}
    >
      {dot && (
        <span
          className={`w-1.5 h-1.5 rounded-full ${dotClass}`}
          aria-hidden="true"
        />
      )}
      {children}
    </span>
  );
});

export default Badge;
