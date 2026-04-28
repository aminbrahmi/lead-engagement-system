// src/api/exclusions.js
import client from "./client";

export const getExclusions = () =>
  client.get("/exclusions");

export const addExclusion = (value, type, reason = "") =>
  client.post("/exclusions", { value, type, reason });

export const removeExclusion = (id) =>
  client.delete(`/exclusions/${id}`);
