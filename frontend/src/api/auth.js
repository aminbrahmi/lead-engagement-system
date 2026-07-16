// src/api/auth.js
import client from "./client";

// profile = { name, role, company, company_description, company_url, company_location, company_size, photo_url }
export const register = (email, password, profile = {}) =>
  client.post("/auth/register", { email, password, ...profile });

export const login = (email, password) =>
  client.post("/auth/login", { email, password });

export const getMe = () => client.get("/auth/me");

export const updateProfile = (fields) => client.patch("/auth/profile", fields);

export const resendVerification = () => client.post("/auth/resend-verification");
