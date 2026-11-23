/**
 * Recovery for a browser tab that is still running a build that has since
 * been replaced.
 *
 * Every build gives its script files new names. A tab opened before an update
 * still holds the old names, so the first screen it opens afterwards asks for
 * a file that is gone and fails with "Failed to fetch dynamically imported
 * module". Reloading the page fetches the new build and fixes it, so we do
 * that once, automatically. The timestamp in sessionStorage stops a reload
 * loop if the file is missing for some other reason (a broken deploy, the
 * server being down): a second failure within the window shows the normal
 * error screen instead.
 */

const STORAGE_KEY = "filaops:stale-build-reload";
const RELOAD_WINDOW_MS = 30_000;

// Messages for a failed dynamic import or CSS preload: Chrome/Edge, Firefox,
// Safari, then Vite's own preload helper.
const STALE_BUILD_PATTERN =
  /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS/i;

export function isStaleBuildError(error) {
  const message = typeof error === "string" ? error : error?.message;
  return STALE_BUILD_PATTERN.test(message || "");
}

/**
 * Reload the page unless it was already reloaded for this reason in the last
 * 30 seconds. Returns true when a reload was started.
 */
export function reloadForNewBuild({
  storage = globalThis.sessionStorage,
  now = Date.now(),
  reload = () => globalThis.location.reload(),
} = {}) {
  try {
    const last = Number(storage?.getItem(STORAGE_KEY) || 0);
    if (now - last < RELOAD_WINDOW_MS) return false;
    storage?.setItem(STORAGE_KEY, String(now));
  } catch {
    // Storage blocked (private mode, site data off): without a way to
    // remember the attempt, a reload could loop, so leave it to the user.
    return false;
  }
  reload();
  return true;
}
