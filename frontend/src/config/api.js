/**
 * API Configuration
 *
 * Where the app sends its API calls. "" means the page's own address: calls
 * go to /api/v1/... on the host and port the page was opened on, and the web
 * server that served the page passes them on to the backend.
 *
 * In order:
 *   1. An address set on the frontend container (VITE_API_URL in its
 *      environment; docker-entrypoint.sh writes it into config.js each time
 *      the container starts).
 *   2. An address set when the app was built (VITE_API_URL at build time, or
 *      in .env.local for `npm run dev`).
 *   3. The page's own address, when config.js says the page is served by the
 *      frontend container. Its nginx proxies /api to the backend, so this is
 *      right on any host name and any port, localhost included.
 *   4. The page's own address, when the page is on https or on a host other
 *      than localhost (a build served by another web server, such as Caddy).
 *   5. http://localhost:8000: `npm run dev` with the backend on this machine.
 */
export const getApiUrl = ({
  runtimeConfig = window.__FILAOPS_CONFIG__,
  buildTimeUrl = import.meta.env.VITE_API_URL,
  location = window.location,
} = {}) => {
  if (runtimeConfig?.API_URL) {
    return runtimeConfig.API_URL;
  }

  if (buildTimeUrl) {
    return buildTimeUrl;
  }

  // An empty API_URL cannot say "use the proxy": it is also what "not set"
  // looks like. The container says it with its own field instead.
  if (runtimeConfig?.API_SAME_ORIGIN === true) {
    return "";
  }

  if (
    location.protocol === "https:" ||
    (location.hostname !== "localhost" && location.hostname !== "127.0.0.1")
  ) {
    return "";
  }

  return "http://localhost:8000";
};

export const API_URL = getApiUrl();

/**
 * What to tell someone when the API cannot be reached. The advice depends on
 * how the address was chosen: a Docker install never needs VITE_API_URL, and
 * a build served without the frontend container may.
 */
export const getApiConnectionHelp = ({
  apiUrl = API_URL,
  runtimeConfig = window.__FILAOPS_CONFIG__,
  location = window.location,
} = {}) => {
  if (apiUrl) {
    return `Cannot connect to API at ${apiUrl}. Please ensure the backend is running at that address.`;
  }

  // "" means calls go to the address the page itself was opened on.
  const ownAddress = `Cannot connect to API at ${location.origin}. `;
  if (runtimeConfig?.API_SAME_ORIGIN === true) {
    return ownAddress + "Please ensure the backend is running.";
  }
  return (
    ownAddress +
    `If the backend is at another address, set VITE_API_URL to it (e.g., http://${location.hostname}:8000) and restart or rebuild the frontend.`
  );
};
