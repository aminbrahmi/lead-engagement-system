// src/api/campaigns.js
import client from "./client";

export const launchCampaign = (prompt) =>
  client.post("/campaigns", { prompt });

export const getCampaigns = () =>
  client.get("/campaigns");

export const getCampaign = (id) =>
  client.get(`/campaigns/${id}`);

export const deleteCampaign = (id) =>
  client.delete(`/campaigns/${id}`);

export const getCampaignLeads = (id) =>
  client.get(`/campaigns/${id}/leads`);

export const getCampaignEvents = (id) =>
  client.get(`/campaigns/${id}/events`);

export const exportCampaignCSV = (id) =>
  `${client.defaults.baseURL}/campaigns/${id}/export`;
