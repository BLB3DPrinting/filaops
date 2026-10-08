import { forwardRef, useId } from "react";

const Select = forwardRef(function Select(
  {
    label,
    error,
    helpText,
    options = [],
    placeholder,
    className = "",
    id: externalId,
    ...rest
  },
  ref
) {
  const generatedId = useId();
  const id = externalId || generatedId;
  const errorId = `${id}-error`;
  const helpId = `${id}-help`;

  const borderClass = error
    ? "border-status-red"
    : "border-hair focus:border-ink";

  return (
    <div>
      {label && (
        <label
          htmlFor={id}
          className="block text-sm text-ink-2 mb-1"
        >
          {label}
        </label>
      )}
      <select
        ref={ref}
        id={id}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={
          error ? errorId : helpText ? helpId : undefined
        }
        className={`w-full h-10 bg-paper border rounded-lg px-3 text-ink disabled:bg-paper-sunk disabled:text-ink-4 ${borderClass} ${className}`}
        {...rest}
      >
        {placeholder && (
          <option value="">{placeholder}</option>
        )}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && (
        <p id={errorId} className="mt-1 text-xs font-medium text-status-red">
          {error}
        </p>
      )}
      {helpText && !error && (
        <p id={helpId} className="mt-1 text-xs text-ink-3">
          {helpText}
        </p>
      )}
    </div>
  );
});

export default Select;
