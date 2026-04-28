// src/hooks/useLeads.js
import { useState, useCallback } from "react";
import * as leadsApi from "../api/leads";

export default function useLeads() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchLeads = useCallback(async (campaignId) => {
    setLoading(true);
    setError(null);
    try {
      const data = await leadsApi.getLeads(campaignId);
      return data.leads || data || [];
    } catch (err) {
      setError(err.message);
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  const saveEmail = useCallback(async (leadId, emailData) => {
    try {
      await leadsApi.updateLeadEmail(leadId, emailData);
      return true;
    } catch (err) {
      setError(err.message);
      return false;
    }
  }, []);

  return { fetchLeads, saveEmail, loading, error };
}
