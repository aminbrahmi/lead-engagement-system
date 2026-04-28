// src/hooks/useCampaigns.js
import { useState, useCallback, useEffect } from "react";
import * as campaignsApi from "../api/campaigns";

export default function useCampaigns() {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchCampaigns = useCallback(async () => {
    setLoading(true);
    try {
      const data = await campaignsApi.getCampaigns();
      setCampaigns(data.campaigns || []);
    } catch {
      // silent — campaigns may not exist yet
    } finally {
      setLoading(false);
    }
  }, []);

  // Auto-fetch on mount
  useEffect(() => {
    fetchCampaigns();
  }, [fetchCampaigns]);

  const loadCampaignLeads = useCallback(async (campaignId) => {
    try {
      const data = await campaignsApi.getCampaignLeads(campaignId);
      return data.leads || [];
    } catch {
      return [];
    }
  }, []);

  return { campaigns, fetchCampaigns, loadCampaignLeads, loading };
}
