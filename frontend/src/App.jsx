// src/App.jsx
import React, { useState, useCallback, useEffect, createContext, useContext } from "react";
import { BrowserRouter, Routes, Route, useNavigate } from "react-router-dom";
import Layout from "./components/Layout";
import CampaignPage from "./pages/CampaignPage";
import PipelinePage from "./pages/PipelinePage";
import LeadsPage from "./pages/LeadsPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import usePipeline from "./hooks/usePipeline";
import useCampaigns from "./hooks/useCampaigns";
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

  // Which campaign's leads are we viewing? null = latest pipeline run
  const [activeCampaignId, setActiveCampaignId] = useState(null);

  useEffect(() => () => disconnect(), [disconnect]);

  // Launch new or re-run existing campaign
  const handleLaunch = useCallback(
    (prompt) => {
      launch(prompt);
      setActiveCampaignId(null);
      navigate("/pipeline");
    },
    [launch, navigate]
  );

  // View an old campaign's results
  const handleViewCampaign = useCallback(
    async (campaign) => {
      const oldLeads = await loadCampaignLeads(campaign.id);
      setLeads(oldLeads);
      setActiveCampaignId(campaign.id);
      navigate("/leads");
    },
    [loadCampaignLeads, setLeads, navigate]
  );

  // When pipeline finishes, refresh campaign list and set active
  useEffect(() => {
    if (leads.length > 0 && !isRunning) {
      if (!activeCampaignId) {
        // Pipeline just finished — refresh campaigns
        fetchCampaigns();
      }
      navigate("/leads");
    }
  }, [leads.length, isRunning, activeCampaignId, fetchCampaigns, navigate]);

  const handleUpdateLead = useCallback(
    (leadId, updates) => {
      setLeads((prev) => prev.map((l) => (l.id === leadId ? { ...l, ...updates } : l)));
    },
    [setLeads]
  );

  // Find active campaign info for display
  const activeCampaign = activeCampaignId
    ? campaigns.find((c) => c.id === activeCampaignId)
    : null;

  return (
    <Routes>
      <Route element={<Layout isRunning={isRunning} leadsCount={leads.length} />}>
        <Route
          index
          element={
            <CampaignPage
              onLaunch={handleLaunch}
              onViewCampaign={handleViewCampaign}
              isRunning={isRunning}
              campaigns={campaigns}
              campaignsLoading={campaignsLoading}
            />
          }
        />
        <Route path="pipeline" element={<PipelinePage currentStage={currentStage} logs={logs} isRunning={isRunning} />} />
        <Route
          path="leads"
          element={
            <LeadsPage
              leads={leads}
              onUpdateLead={handleUpdateLead}
              activeCampaign={activeCampaign}
              campaigns={campaigns}
              onViewCampaign={handleViewCampaign}
            />
          }
        />
        <Route path="analytics" element={<AnalyticsPage leads={leads} />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  const [isDark, setIsDark] = useState(true);
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
