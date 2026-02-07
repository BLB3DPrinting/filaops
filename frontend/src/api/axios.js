/**
 * Axios-like API wrapper using fetch
 *
 * Provides a consistent API interface similar to axios for making HTTP requests.
 * Used by components that need progress tracking and cleaner response handling.
 *
 * Auth: Uses httpOnly cookies (set by backend on login). No manual token handling.
 */
import { API_URL } from '../config/api';

// Build full URL
const buildUrl = (path) => {
  // Handle both /path and path formats
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_URL}/api/v1${cleanPath}`;
};

// Parse response
const parseResponse = async (response) => {
  const contentType = response.headers.get('content-type');

  if (contentType?.includes('application/json')) {
    return response.json();
  }

  // For blob/file downloads
  if (contentType?.includes('application/octet-stream') ||
      contentType?.includes('application/pdf') ||
      contentType?.includes('text/csv')) {
    return response.blob();
  }

  return response.text();
};

// Handle response errors
const handleResponse = async (response) => {
  if (!response.ok) {
    const error = new Error(`HTTP ${response.status}`);
    try {
      error.response = {
        data: await response.json(),
        status: response.status,
      };
    } catch {
      error.response = {
        data: { detail: response.statusText },
        status: response.status,
      };
    }
    throw error;
  }
  return response;
};

/**
 * GET request
 */
const get = async (path, config = {}) => {
  const response = await fetch(buildUrl(path), {
    method: 'GET',
    credentials: 'include',
    headers: {
      ...config.headers,
    },
  });

  await handleResponse(response);
  const data = await parseResponse(response);
  return { data, status: response.status };
};

/**
 * POST request with FormData support and upload progress
 */
const post = async (path, body, config = {}) => {
  const headers = {};

  // Don't set Content-Type for FormData - browser sets it with boundary
  if (!(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(body);
  }

  // If we have onUploadProgress, use XMLHttpRequest for progress tracking
  if (config.onUploadProgress && body instanceof FormData) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener('progress', (event) => {
        if (event.lengthComputable) {
          config.onUploadProgress({
            loaded: event.loaded,
            total: event.total,
          });
        }
      });

      xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText);
            resolve({ data, status: xhr.status });
          } catch {
            resolve({ data: xhr.responseText, status: xhr.status });
          }
        } else {
          const error = new Error(`HTTP ${xhr.status}`);
          try {
            error.response = {
              data: JSON.parse(xhr.responseText),
              status: xhr.status,
            };
          } catch {
            error.response = {
              data: { detail: xhr.statusText },
              status: xhr.status,
            };
          }
          reject(error);
        }
      });

      xhr.addEventListener('error', () => {
        reject(new Error('Network error'));
      });

      xhr.open('POST', buildUrl(path));
      xhr.withCredentials = true;

      xhr.send(body);
    });
  }

  // Standard fetch for non-progress requests
  const response = await fetch(buildUrl(path), {
    method: 'POST',
    credentials: 'include',
    headers: {
      ...headers,
      ...config.headers,
    },
    body,
  });

  await handleResponse(response);
  const data = await parseResponse(response);
  return { data, status: response.status };
};

/**
 * PUT request
 */
const put = async (path, body, config = {}) => {
  const headers = {
    'Content-Type': 'application/json',
    ...config.headers,
  };

  const response = await fetch(buildUrl(path), {
    method: 'PUT',
    credentials: 'include',
    headers,
    body: JSON.stringify(body),
  });

  await handleResponse(response);
  const data = await parseResponse(response);
  return { data, status: response.status };
};

/**
 * DELETE request
 */
const del = async (path, config = {}) => {
  const response = await fetch(buildUrl(path), {
    method: 'DELETE',
    credentials: 'include',
    headers: {
      ...config.headers,
    },
  });

  await handleResponse(response);

  // DELETE might return empty body
  if (response.status === 204) {
    return { data: null, status: 204 };
  }

  const data = await parseResponse(response);
  return { data, status: response.status };
};

/**
 * PATCH request
 */
const patch = async (path, body, config = {}) => {
  const headers = {
    'Content-Type': 'application/json',
    ...config.headers,
  };

  const response = await fetch(buildUrl(path), {
    method: 'PATCH',
    credentials: 'include',
    headers,
    body: JSON.stringify(body),
  });

  await handleResponse(response);
  const data = await parseResponse(response);
  return { data, status: response.status };
};

// Export as default object (axios-like interface)
const api = {
  get,
  post,
  put,
  delete: del,
  patch,
};

export default api;
