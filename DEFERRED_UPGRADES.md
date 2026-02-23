# Deferred Dependency Upgrades

## ESLint 9 → 10 (PR #350, Issue #285)

- **Deferred on:** 2026-02-23
- **Reason:** `eslint-plugin-react-hooks` (React team's official plugin) only supports ESLint ^3-^9. No ESLint 10 support even in canary builds as of 2026-02-23. Our codebase is already on flat config (`eslint.config.js`) so the config migration is not a blocker — the plugin compatibility is.
- **Blocked by:** `eslint-plugin-react-hooks` upstream — watch [React issues](https://github.com/facebook/react/issues) for updates
- **Impact:** Zero — linting tool only, no user-facing changes
- **Recommendation:** Re-check after React team releases ESLint 10 support
