/**
 * Version utility functions
 *
 * The frontend version is imported from package.json at build time (Vite
 * inlines JSON imports).  This eliminates hardcoded version strings that
 * fall out of date.
 *
 * See docs/VERSIONING.md for the full versioning strategy.
 */

import { API_URL } from '../config/api';
import pkgJson from '../../package.json';

/** Version string read from package.json at build time (e.g. "3.0.1"). */
const PACKAGE_VERSION = pkgJson.version;

/**
 * Get current version from backend API
 * @returns {Promise<string>} Current version (e.g., "3.0.1")
 */
export async function getCurrentVersion() {
  try {
    const response = await fetch(`${API_URL}/api/v1/system/version`);
    if (!response.ok) {
      throw new Error('Failed to fetch version');
    }
    const data = await response.json();
    return data.version;
  } catch (error) {
    console.error('Failed to get version from backend:', error);
    return PACKAGE_VERSION;
  }
}

/**
 * Get current version synchronously (build-time value from package.json)
 * @returns {string} Current version (e.g., "3.0.1")
 */
export function getCurrentVersionSync() {
  return PACKAGE_VERSION;
}

/**
 * Compare two semantic versions
 * @param {string} v1 - First version (e.g., "1.1.0")
 * @param {string} v2 - Second version (e.g., "1.2.0")
 * @returns {number} -1 if v1 < v2, 0 if v1 === v2, 1 if v1 > v2
 */
export function compareVersions(v1, v2) {
  // Ensure inputs are strings
  const cleanV1 = String(v1 ?? "0").replace(/^v/, "");
  const cleanV2 = String(v2 ?? "0").replace(/^v/, "");

  const parts1 = cleanV1.split(".").map(Number);
  const parts2 = cleanV2.split(".").map(Number);

  // Ensure both arrays have the same length
  const maxLength = Math.max(parts1.length, parts2.length);
  while (parts1.length < maxLength) parts1.push(0);
  while (parts2.length < maxLength) parts2.push(0);

  for (let i = 0; i < maxLength; i++) {
    if (parts1[i] < parts2[i]) return -1;
    if (parts1[i] > parts2[i]) return 1;
  }

  return 0;
}

/**
 * Check if version v1 is less than v2
 * @param {string} v1 - First version
 * @param {string} v2 - Second version
 * @returns {boolean} True if v1 < v2
 */
export function isVersionLessThan(v1, v2) {
  return compareVersions(v1, v2) < 0;
}

/**
 * Check if version v1 is greater than v2
 * @param {string} v1 - First version
 * @param {string} v2 - Second version
 * @returns {boolean} True if v1 > v2
 */
export function isVersionGreaterThan(v1, v2) {
  return compareVersions(v1, v2) > 0;
}

/**
 * Format version for display (removes 'v' prefix if present)
 * @param {string} version - Version string
 * @returns {string} Formatted version
 */
export function formatVersion(version) {
  return String(version ?? "").replace(/^v/, "");
}
