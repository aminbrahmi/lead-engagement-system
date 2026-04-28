// src/api/leads.js
import client from "./client";

export const getLeads = (campaignId) =>
  client.get("/leads", { params: campaignId ? { campaign_id: campaignId } : {} });

export const getLead = (id) =>
  client.get(`/leads/${id}`);

export const getLeadEmails = (id) =>
  client.get(`/leads/${id}/emails`);

export const updateLeadEmailVariant = (id, variant, emailData) =>
  client.patch(`/leads/${id}/emails/${variant}`, emailData);

// Legacy — kept for backward compat
export const updateLeadEmail = (id, emailData) =>
  client.patch(`/leads/${id}/email`, emailData);

export const updateLeadStatus = (id, status) =>
  client.patch(`/leads/${id}`, { status });
