/**
 * ThemeToggle — Day / Dim segmented control for the top bar.
 *
 * Reads and writes the theme through useTheme(); the store applies the
 * `data-theme` attribute and persists the choice. The track sits on
 * paper-sunk with the selected segment as ink-on-paper, following the
 * design system's segmented-control rule, so it reads the same in both themes.
 *
 * Usage:
 *   <ThemeToggle className="ml-2" />
 */
import { useTheme } from "../contexts/ThemeContext";

const OPTIONS = [
  { value: "light", label: "Day", testId: "theme-toggle-light" },
  { value: "dim", label: "Dim", testId: "theme-toggle-dim" },
];

function ThemeToggle({ className = "" }) {
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="group"
      aria-label="Theme"
      className={`inline-flex bg-paper-sunk rounded-lg p-0.5 border border-hair ${className}`.trim()}
    >
      {OPTIONS.map(({ value, label, testId }) => {
        const selected = theme === value;
        return (
          <button
            key={value}
            type="button"
            aria-pressed={selected}
            data-testid={testId}
            onClick={() => setTheme(value)}
            className={`px-3 py-1 rounded-md text-sm font-medium transition-colors ${
              selected ? "bg-ink text-paper" : "text-ink-3 hover:text-ink"
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

export default ThemeToggle;
