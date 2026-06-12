/**
 * Formatting utilities for display
 */

/**
 * Format duration in minutes to human-readable string
 * @param {number} minutes - Duration in minutes
 * @returns {string} Formatted duration (e.g., "2h 30m", "45m", "1h")
 */
export function formatDuration(minutes) {
  if (!minutes || minutes <= 0) return '0m';

  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);

  if (hours === 0) return `${mins}m`;
  if (mins === 0) return `${hours}h`;
  return `${hours}h ${mins}m`;
}

/**
 * Parse datetime string, ensuring UTC interpretation
 * Backend sends UTC times without 'Z' suffix, so we need to add it
 * @param {string|Date} datetime - ISO datetime string or Date object
 * @returns {Date} Date object
 */
export function parseDateTime(datetime) {
  if (!datetime) return null;
  if (datetime instanceof Date) return datetime;

  // If string doesn't have timezone info, assume UTC and add 'Z'
  let dateStr = datetime;
  if (typeof dateStr === 'string' && !dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('-', 10)) {
    dateStr = dateStr + 'Z';
  }
  return new Date(dateStr);
}

/**
 * Format datetime to time string
 * @param {string|Date} datetime - ISO datetime string or Date object
 * @returns {string} Formatted time (e.g., "2:30 PM")
 */
export function formatTime(datetime) {
  if (!datetime) return '';

  const date = parseDateTime(datetime);
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

/**
 * Format datetime to date string
 * @param {string|Date} datetime - ISO datetime string or Date object
 * @returns {string} Formatted date (e.g., "Jan 15, 2025")
 */
export function formatDate(datetime) {
  if (!datetime) return '';

  const date = parseDateTime(datetime);
  return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

/**
 * Format datetime to relative string
 * @param {string|Date} datetime - ISO datetime string or Date object
 * @returns {string} Relative time (e.g., "5 minutes ago", "in 2 hours")
 */
export function formatRelativeTime(datetime) {
  if (!datetime) return '';

  const date = parseDateTime(datetime);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();
  const diffMins = Math.round(diffMs / 60000);

  if (Math.abs(diffMins) < 1) return 'just now';
  if (diffMins < 0) {
    // Past
    const absMins = Math.abs(diffMins);
    if (absMins < 60) return `${absMins}m ago`;
    const hours = Math.floor(absMins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  } else {
    // Future
    if (diffMins < 60) return `in ${diffMins}m`;
    const hours = Math.floor(diffMins / 60);
    if (hours < 24) return `in ${hours}h`;
    const days = Math.floor(hours / 24);
    return `in ${days}d`;
  }
}
