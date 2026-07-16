// frontend/src/api/leads.js
import client from "./client";

export const getLeads = (campaignId) =>
  client.get("/leads", { params: campaignId ? { campaign_id: campaignId } : {} });

export const getLead = (id) =>
  client.get(`/leads/${id}`);

export const getLeadEmails = (id) =>
  client.get(`/leads/${id}/emails`);

export const updateLeadEmailVariant = (id, variant, emailData) =>
  client.patch(`/leads/${id}/emails/${variant}`, emailData);

export const updateLeadEmail = (id, emailData) =>
  client.patch(`/leads/${id}/email`, emailData);

export const updateLeadStatus = (id, status) =>
  client.patch(`/leads/${id}`, { status });

export const updateLeadFields = (id, fields) =>
  client.patch(`/leads/${id}/fields`, fields);

// Re-run research insights, regenerate A/B emails, and auto-adjust the score.
// Longer timeout: this does Tavily searches + LLM calls + SMTP verification.
export const reEnrichLead = (id) =>
  client.post(`/leads/${id}/re-enrich`, {}, { timeout: 100000 });

// ML: predicted reply probability (0-100) for each lead → { available, scores: {id: pct} }
export const getReplyScores = () => client.post("/leads/reply-scores");
