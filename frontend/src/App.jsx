// frontend/src/App.jsx
import React, { useState, useCallback, useEffect, useRef, createContext, useContext } from "react";
import { BrowserRouter, Routes, Route, useNavigate } from "react-router-dom";
import Layout from "./components/Layout";
import CampaignPage from "./pages/CampaignPage";
import PipelinePage from "./pages/PipelinePage";
import LeadsPage from "./pages/LeadsPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import InboxPage from "./pages/InboxPage";
import ExclusionsPage from "./pages/ExclusionsPage";
import usePipeline from "./hooks/usePipeline";
import useCampaigns from "./hooks/useCampaigns";
import { getLeads } from "./api/leads";
import { darkTheme, lightTheme } from "./styles/theme";
import "./styles/global.css";

// ── Theme context ────────────────────────────────────────────────────────────
export const ThemeContext = createContext();
export const useTheme = () => useContext(ThemeContext);

function AppRoutes() {
  const navigate = useNavigate();
  const {
    isRunning, currentStage, logs, leads, setLeads,
    campaignId, error, launch, disconnect,
  } = usePipeline();
  const { campaigns, fetchCampaigns, loadCampaignLeads, loading: campaignsLoading } = useCampaigns();
  const [activeCampaignId, setActiveCampaignId] = useState(null);

  useEffect(() => () => disconnect(), [disconnect]);

  const handleLaunch = useCallback(
    (prompt) => { launch(prompt); setActiveCampaignId(null); navigate("/pipeline"); },
    [launch, navigate]
  );

  const handleViewCampaign = useCallback(
    async (campaign) => {
      const oldLeads = await loadCampaignLeads(campaign.id);
      setLeads(oldLeads);
      setActiveCampaignId(campaign.id);
      navigate("/leads");
    },
    [loadCampaignLeads, setLeads, navigate]
  );

  // Navigate to /leads only when the pipeline JUST finished (running→done), not on every re-render
  const prevIsRunning = useRef(false);
  useEffect(() => {
    const justFinished = prevIsRunning.current && !isRunning;
    prevIsRunning.current = isRunning;
    if (justFinished && leads.length > 0) {
      fetchCampaigns();
      navigate("/leads");
    }
  }, [isRunning, leads.length, fetchCampaigns, navigate]);

  const handleUpdateLead = useCallback(
    (leadId, updates) => {
      if (updates._deleted) {
        setLeads((prev) => prev.filter((l) => l.id !== leadId));
      } else {
        setLeads((prev) => prev.map((l) => (l.id === leadId ? { ...l, ...updates } : l)));
      }
    },
    [setLeads]
  );

  const activeCampaign = activeCampaignId
    ? campaigns.find((c) => c.id === activeCampaignId)
    : null;

  const handleRefresh = useCallback(async () => {
    if (activeCampaignId) {
      const fresh = await loadCampaignLeads(activeCampaignId);
      setLeads(fresh);
    } else {
      try {
        const data = await getLeads();
        setLeads(data.leads || []);
      } catch {}
    }
    fetchCampaigns();
  }, [activeCampaignId, loadCampaignLeads, setLeads, fetchCampaigns]);

  return (
    <Routes>
      <Route element={<Layout isRunning={isRunning} leadsCount={leads.length} />}>
        <Route index element={<CampaignPage onLaunch={handleLaunch} onViewCampaign={handleViewCampaign} isRunning={isRunning} campaigns={campaigns} campaignsLoading={campaignsLoading} />} />
        <Route path="pipeline" element={<PipelinePage currentStage={currentStage} logs={logs} isRunning={isRunning} />} />
        <Route path="leads" element={<LeadsPage leads={leads} onUpdateLead={handleUpdateLead} activeCampaign={activeCampaign} campaigns={campaigns} onViewCampaign={handleViewCampaign} onRefresh={handleRefresh} />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="analytics" element={<AnalyticsPage leads={leads} />} />
        <Route path="exclusions" element={<ExclusionsPage />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  // ──────────────────────────────────────────────────────────
  // CHANGE: default to light mode (was true → now false)
  // ──────────────────────────────────────────────────────────
  const [isDark, setIsDark] = useState(false);
  const theme = isDark ? darkTheme : lightTheme;
  const toggleTheme = useCallback(() => setIsDark((p) => !p), []);

  return (
    <ThemeContext.Provider value={{ theme, isDark, toggleTheme }}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ThemeContext.Provider>
  );
}
