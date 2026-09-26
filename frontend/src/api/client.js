/**
 * Intelligent Document Processing (IDP) - HTTP API Client
 * Uses environment variable VITE_API_BASE_URL with graceful fallback.
 */

export const BASE_URL = import.meta.env.VITE_API_BASE_URL
  ? import.meta.env.VITE_API_BASE_URL.replace(/\/$/, '')
  : 'http://127.0.0.1:8000';

/**
 * Universal JSON fetch client with robust error sanitization.
 */
export async function apiClient(endpoint, options = {}) {
  const url = `${BASE_URL}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

  const defaultHeaders = {
    Accept: 'application/json',
  };

  if (options.body && !(options.body instanceof FormData)) {
    defaultHeaders['Content-Type'] = 'application/json';
  }

  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers,
    },
  };

  try {
    const response = await fetch(url, config);

    // Handle 204 No Content
    if (response.status === 204) {
      return null;
    }

    const contentType = response.headers.get('content-type') || '';
    const isJson = contentType.includes('application/json');

    if (!response.ok) {
      let errorMessage = 'Request failed';
      if (isJson) {
        try {
          const errData = await response.json();
          if (typeof errData.detail === 'string') {
            errorMessage = errData.detail;
          } else if (Array.isArray(errData.detail) && errData.detail[0]?.msg) {
            errorMessage = errData.detail[0].msg;
          } else if (errData.message) {
            errorMessage = errData.message;
          }
        } catch {
          errorMessage = `HTTP Error ${response.status}`;
        }
      } else {
        errorMessage = `HTTP Error ${response.status}`;
      }

      // Sanitize away any SQL/internal leaks
      if (errorMessage.includes('SQL') || errorMessage.includes('traceback') || errorMessage.includes('OperationalError')) {
        errorMessage = 'A database error occurred. Please verify backend state.';
      }

      const err = new Error(errorMessage);
      err.status = response.status;
      throw err;
    }

    if (isJson) {
      return await response.json();
    }
    return await response.text();
  } catch (error) {
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      const netError = new Error('Unable to connect to the IDP backend. Please ensure the backend is running.');
      netError.isNetworkError = true;
      throw netError;
    }
    throw error;
  }
}
