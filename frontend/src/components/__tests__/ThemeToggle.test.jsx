import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import ThemeToggle from "../ThemeToggle";
import { ThemeProvider } from "../../contexts/ThemeContext";
import { THEME_KEY } from "../../lib/theme";

const html = () => document.documentElement;

beforeEach(() => {
  localStorage.clear();
  html().removeAttribute("data-theme");
  html().removeAttribute("data-glass");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderToggle(props = {}) {
  return render(
    <ThemeProvider>
      <ThemeToggle {...props} />
    </ThemeProvider>
  );
}

describe("ThemeToggle", () => {
  it("renders a labelled group with Day selected by default", () => {
    renderToggle();

    expect(screen.getByRole("group", { name: "Theme" })).toBeInTheDocument();

    const day = screen.getByTestId("theme-toggle-light");
    const dim = screen.getByTestId("theme-toggle-dim");
    expect(day).toHaveTextContent("Day");
    expect(dim).toHaveTextContent("Dim");
    expect(day).toHaveAttribute("type", "button");
    expect(dim).toHaveAttribute("type", "button");
    expect(day).toHaveAttribute("aria-pressed", "true");
    expect(dim).toHaveAttribute("aria-pressed", "false");
  });

  it("reflects a stored dim preference", () => {
    localStorage.setItem(THEME_KEY, "dim");
    renderToggle();

    expect(screen.getByTestId("theme-toggle-dim")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("theme-toggle-light")).toHaveAttribute("aria-pressed", "false");
  });

  it("clicking Dim applies the attribute and flips aria-pressed", async () => {
    const user = userEvent.setup();
    renderToggle();

    await user.click(screen.getByTestId("theme-toggle-dim"));

    expect(html().getAttribute("data-theme")).toBe("dim");
    expect(localStorage.getItem(THEME_KEY)).toBe("dim");
    expect(screen.getByTestId("theme-toggle-dim")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("theme-toggle-light")).toHaveAttribute("aria-pressed", "false");
  });

  it("Enter on the focused Day button restores light", async () => {
    const user = userEvent.setup();
    renderToggle();

    await user.click(screen.getByTestId("theme-toggle-dim"));
    expect(html().getAttribute("data-theme")).toBe("dim");

    screen.getByTestId("theme-toggle-light").focus();
    expect(screen.getByTestId("theme-toggle-light")).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(html().getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem(THEME_KEY)).toBe("light");
    expect(screen.getByTestId("theme-toggle-light")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("theme-toggle-dim")).toHaveAttribute("aria-pressed", "false");
  });

  it("uses Workbench tokens, not raw palette utilities", () => {
    renderToggle({ className: "ml-2" });

    const group = screen.getByRole("group", { name: "Theme" });
    expect(group).toHaveClass("bg-paper-sunk", "border-hair", "ml-2");
    expect(screen.getByTestId("theme-toggle-light")).toHaveClass("bg-ink", "text-paper");
    expect(screen.getByTestId("theme-toggle-dim")).toHaveClass("text-ink-3");
    expect(group.outerHTML).not.toMatch(/\b(bg|text|border)-(gray|blue|white)\b/);
  });
});
