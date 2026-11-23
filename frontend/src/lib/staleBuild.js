/**
 * Recovery for a browser tab that is still running a build that has since
 * been replaced.
 *
 * Every build gives its script files new names. A tab opened before an update
 * still holds the old names, so the first screen it opens afterwards asks for
 * a file that is gone and fails with "Failed to fetch dynamically imported
 * module". Reloading the page fetches the new build and fixes it, so we do
 * that once, automatically.
 *
 * At most one automatic reload per build: before reloading, the build the tab
 * is running is written to sessionStorage. If the page that comes back is the
 * same build and fails again (a deploy that is missing a file, the server
 * down), no second reload happens and the normal error screen shows, however
 * long the reload took. A later update is a different build, so it gets its
 * own one reload.
 */

const STORAGE_KEY = "filaops:stale-build-reload";

// Messages for a failed dynamic import or CSS preload: Chrome/Edge, Firefox,
// Safari, then Vite's own preload helper.
const STALE_BUILD_PATTERN =
  /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed|Unable to preload CSS/i;

export function isStaleBuildError(error) {
  const message = typeof error === "string" ? error : error?.message;
  return STALE_BUILD_PATTERN.test(message || "");
}

/**
 * The build this tab is running: the address of the page's entry script
 * (e.g. /assets/index-CZ1E9Z0O.js). Its name changes whenever any file it
 * loads changes, so it identifies the build.
 */
export function currentBuildId(doc = globalThis.document) {
  const script = doc?.querySelector?.('script[type="module"][src]');
  return script?.getAttribute("src") || "unknown";
}

/**
 * Reload the page unless this build was already reloaded once for this
 * reason. Returns true when a reload was started.
 */
export function reloadForNewBuild({
  getStorage = () => globalThis.sessionStorage,
  buildId = currentBuildId(),
  reload = () => globalThis.location.reload(),
} = {}) {
  try {
    // Reading sessionStorage itself can throw (SecurityError when the browser
    // blocks site data), so it is read inside the try.
    const storage = getStorage();
    if (!storage) return false;
    if (storage.getItem(STORAGE_KEY) === buildId) return false;
    storage.setItem(STORAGE_KEY, buildId);
  } catch {
    // Without a way to remember the attempt a reload could loop, so leave it
    // to the user.
    return false;
  }
  reload();
  return true;
}
