// src/api/client.js
import axios from "axios";

const API_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

const client = axios.create({
  baseURL: API_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

// Response interceptor — unwrap data, normalize errors
client.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const message = err.response?.data?.detail || err.message || "Network error";
    return Promise.reject(new Error(message));
  }
);

export default client;
export { API_URL };
