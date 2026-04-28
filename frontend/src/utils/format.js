// src/utils/format.js

export const timestamp = () =>
  new Date().toLocaleTimeString("en", {
    hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit",
  });

export const truncate = (str, len = 40) =>
  str && str.length > len ? str.slice(0, len) + "…" : str || "";

export const pct = (n, total) =>
  total ? Math.round((n / total) * 100) : 0;
