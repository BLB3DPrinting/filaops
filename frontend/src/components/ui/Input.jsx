import { forwardRef, useId } from "react";

const Input = forwardRef(function Input(
  { label, error, helpText, className = "", id: externalId, ...rest },
  ref
) {
  const generatedId = useId();
  const id = externalId || generatedId;
  const errorId = `${id}-error`;
  const helpId = `${id}-help`;

  const borderClass = error
    ? "border-red-500 focus:border-red-500"
    : "border-gray-700 focus:border-blue-500";

  return (
    <div>
      {label && (
        <label
          htmlFor={id}
          className="block text-sm font-medium text-gray-400 mb-1"
        >
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={id}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={
          error ? errorId : helpText ? helpId : undefined
        }
        className={`w-full bg-gray-800 border rounded-lg px-3 py-2 text-white placeholder-gray-500 focus:outline-none ${borderClass} ${className}`}
        {...rest}
      />
      {error && (
        <p id={errorId} className="mt-1 text-sm text-red-400">
          {error}
        </p>
      )}
      {helpText && !error && (
        <p id={helpId} className="mt-1 text-sm text-gray-500">
          {helpText}
        </p>
      )}
    </div>
  );
});

export default Input;
