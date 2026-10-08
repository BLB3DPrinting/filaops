import React from "react";
import "../src/index.css";

// Industrial Workbench (#846): every story renders in both themes. The Day/Dim
// toolbar switch writes the same `data-theme` attribute the app shell will
// write, so stories exercise the real token cascade in index.css rather than a
// Storybook-only background colour.
const THEME_ATTR = "data-theme";

const withWorkbenchTheme = (Story, context) => {
  const theme = context.globals.theme === "dim" ? "dim" : "light";
  document.documentElement.setAttribute(THEME_ATTR, theme);
  document.body.style.backgroundColor = "var(--paper)";
  document.body.style.color = "var(--ink)";
  return React.createElement(Story);
};

/** @type { import('@storybook/react-vite').Preview } */
const preview = {
  globalTypes: {
    theme: {
      description: "Workbench theme",
      toolbar: {
        title: "Theme",
        icon: "paintbrush",
        items: [
          { value: "light", title: "Day" },
          { value: "dim", title: "Dim" },
        ],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: {
    theme: "light",
  },
  decorators: [withWorkbenchTheme],
  parameters: {
    backgrounds: { disable: true },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    a11y: {
      test: "todo",
    },
  },
};

export default preview;
