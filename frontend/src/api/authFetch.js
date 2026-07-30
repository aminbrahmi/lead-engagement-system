// src/api/authFetch.js
// Drop-in replacement for fetch() that attaches the JWT from localStorage.
// Use for any direct API call so the backend's auth middleware accepts it.
export function authFetch(url, options = {}) {
  const token = localStorage.getItem("token");
  const headers = { ...(options.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(url, { ...options, headers });
}
