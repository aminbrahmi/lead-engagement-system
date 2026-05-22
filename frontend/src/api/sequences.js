// frontend/src/api/sequences.js
import client from "./client";

export const sendCampaign = (campaignId, variant = "A", leadIds = null) =>
  client.post(`/campaigns/${campaignId}/send`, { variant, lead_ids: leadIds });

export const sendSingleLead = (campaignId, leadId, variant = "A") =>
  client.post(`/leads/${leadId}/send-email`, { variant, send_followups: true });

export const getLeadSequence = (leadId) =>
  client.get(`/leads/${leadId}/sequence`);

export const getCampaignSequences = (campaignId) =>
  client.get(`/campaigns/${campaignId}/sequences`);

export const cancelLeadSequence = (leadId) =>
  client.post(`/leads/${leadId}/sequence/cancel`);

export const runScheduler = () =>
  client.post("/scheduler/run");

export const runTracker = (campaignId = null) =>
  client.post("/tracker/run", campaignId ? { campaign_id: campaignId } : {});
