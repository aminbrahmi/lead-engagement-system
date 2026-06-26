// src/api/analytics.js
import client, { API_URL } from "./client";

// Recommendations require an LLM call → allow more time
const LLM_TIMEOUT = 90000;

export const getCampaignReport = (id, recommendations = true) =>
  client.get(`/analytics/campaign/${id}`, {
    params: { recommendations },
    timeout: recommendations ? LLM_TIMEOUT : 30000,
  });

export const getWeeklyReport = (recommendations = true) =>
  client.get(`/analytics/weekly`, {
    params: { recommendations },
    timeout: recommendations ? LLM_TIMEOUT : 30000,
  });

// Direct PDF download URLs (browser handles the download)
export const campaignPdfUrl = (id) => `${API_URL}/analytics/campaign/${id}/pdf`;
export const weeklyPdfUrl = () => `${API_URL}/analytics/weekly/pdf`;
