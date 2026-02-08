import { forwardRef } from "react";

const VARIANT_CLASSES = {
  success: "bg-green-500/20 text-green-400",
  warning: "bg-amber-500/20 text-amber-400",
  danger: "bg-red-500/20 text-red-400",
  info: "bg-blue-500/20 text-blue-400",
  neutral: "bg-gray-500/20 text-gray-400",
  purple: "bg-purple-500/20 text-purple-400",
};

const DOT_CLASSES = {
  success: "bg-green-400",
  warning: "bg-amber-400",
  danger: "bg-red-400",
  info: "bg-blue-400",
  neutral: "bg-gray-400",
  purple: "bg-purple-400",
};

const SIZE_CLASSES = {
  sm: "px-1.5 py-0.5 text-xs",
  md: "px-2 py-1 text-xs",
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
      className={`inline-flex items-center gap-1.5 font-medium rounded ${variantClasses} ${sizeClasses} ${className}`}
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
