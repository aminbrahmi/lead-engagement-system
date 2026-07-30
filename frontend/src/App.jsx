// frontend/src/App.jsx
import React, { useState, useCallback, useEffect, useRef, createContext, useContext } from "react";
import { BrowserRouter, Routes, Route, useNavigate, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import CampaignPage from "./pages/CampaignPage";
import PipelinePage from "./pages/PipelinePage";
import LeadsPage from "./pages/LeadsPage";
import AnalyticsPage from "./pages/AnalyticsPage";
import InboxPage from "./pages/InboxPage";
import ExclusionsPage from "./pages/ExclusionsPage";
import SettingsPage from "./pages/SettingsPage";
import AuthPage from "./pages/AuthPage";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { resendVerification } from "./api/auth";
import usePipeline from "./hooks/usePipeline";
import useCampaigns from "./hooks/useCampaigns";
import { getLeads } from "./api/leads";
import { deleteCampaign } from "./api/campaigns";
import { darkTheme, lightTheme } from "./styles/theme";
import "./styles/global.css";

// ── Verify-email gate (blocks the app until the email is verified) ─────────────
function VerifyGate() {
  const { theme } = useTheme();
  const c = theme.colors;
  const { user, logout, refreshUser } = useAuth();
  const navigate = useNavigate();
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const resend = async () => {
    setMsg("Sending…");
    try { const r = await resendVerification(); setMsg(r.status === "sent" ? "Verification email sent ✓" : r.status === "already_verified" ? "Already verified — refresh below" : "Failed to send"); }
    catch { setMsg("Failed to send"); }
  };
  const check = async () => {
    setBusy(true); setMsg(null);
    try {
      const me = await refreshUser();
      if (!me.email_verified) setMsg("Still not verified — click the link in your email first.");
    } catch { setMsg("Could not check status"); }
    finally { setBusy(false); }
  };

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: `radial-gradient(1200px 600px at 50% -10%, ${c.accentGlow}, ${c.bg})`, padding: 20,
    }}>
      <div style={{
        width: 420, maxWidth: "100%", background: c.surface, border: `1px solid ${c.border}`,
        borderRadius: 18, padding: "36px 32px", textAlign: "center", boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
      }}>
        <div style={{ fontSize: 40, marginBottom: 8 }}>📧</div>
        <h2 style={{ color: c.text, margin: "0 0 8px" }}>Verify your email</h2>
        <p style={{ color: c.textDim, fontSize: 14, lineHeight: 1.6 }}>
          You must verify your email before using TheLeadFlow. We sent a link to{" "}
          <b style={{ color: c.text }}>{user?.email}</b>. Click it, then press refresh.
        </p>
        {msg && <div style={{ fontSize: 13, color: c.accent, marginTop: 12 }}>{msg}</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 22 }}>
          <button onClick={check} disabled={busy} style={{
            padding: "12px 0", borderRadius: 10, border: "none", background: c.accent, color: "#fff",
            fontWeight: 600, fontSize: 14, cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.6 : 1,
          }}>{busy ? "Checking…" : "I've verified — refresh"}</button>
          <button onClick={resend} style={{
            padding: "10px 0", borderRadius: 10, border: `1px solid ${c.border}`, background: "transparent",
            color: c.textMuted, fontWeight: 600, fontSize: 13, cursor: "pointer",
          }}>Resend verification email</button>
          <button onClick={() => { logout(); navigate("/login"); }} style={{
            padding: "6px 0", background: "none", border: "none", color: c.textDim, fontSize: 12, cursor: "pointer",
          }}>Sign out</button>
        </div>
      </div>
    </div>
  );
}

// ── Profile-completion gate (required after e.g. Google sign-in) ───────────────
const REQUIRED_PROFILE = ["role", "company", "company_url", "company_description"];
const isProfileComplete = (u) =>
  !!u && REQUIRED_PROFILE.every((k) => (u[k] || "").toString().trim().length > 0);

function ProfileGate() {
  const { theme } = useTheme();
  const c = theme.colors;
  const { user, updateProfile, logout } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    role: user?.role || "",
    company: user?.company || "",
    company_url: user?.company_url || "",
    company_description: user?.company_description || "",
  });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((s) => ({ ...s, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    const role = form.role.trim(), company = form.company.trim();
    const url = form.company_url.trim(), desc = form.company_description.trim();
    if (!role || !company || !url || !desc) { setError("All fields are required"); return; }
    if (!/^https?:\/\/.+/i.test(url)) { setError("Company website must start with http:// or https://"); return; }
    setError(null); setBusy(true);
    try { await updateProfile({ role, company, company_url: url, company_description: desc }); }
    catch (err) { setError(err.message || "Could not save your profile"); }
    finally { setBusy(false); }
  };

  const inp = {
    width: "100%", padding: "10px 12px", borderRadius: 10, boxSizing: "border-box",
    border: `1px solid ${c.border}`, background: c.bg, color: c.text, fontSize: 14, outline: "none",
  };
  const lbl = { display: "block", textAlign: "left", fontSize: 12, fontWeight: 600, color: c.textMuted, margin: "0 0 6px" };

  return (
    <div style={{
      minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
      background: `radial-gradient(1200px 600px at 50% -10%, ${c.accentGlow}, ${c.bg})`, padding: 20,
    }}>
      <form onSubmit={submit} style={{
        width: 460, maxWidth: "100%", background: c.surface, border: `1px solid ${c.border}`,
        borderRadius: 18, padding: "34px 32px", boxShadow: "0 20px 60px rgba(0,0,0,0.15)",
      }}>
        <div style={{ textAlign: "center", marginBottom: 20 }}>
          <h2 style={{ color: c.text, margin: "0 0 6px" }}>Complete your profile</h2>
          <p style={{ color: c.textDim, fontSize: 13, lineHeight: 1.6, margin: 0 }}>
            These details are used to write your outreach emails. All fields are required.
          </p>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={lbl}>Role / title</label>
            <input style={inp} value={form.role} onChange={set("role")} />
          </div>
          <div>
            <label style={lbl}>Company</label>
            <input style={inp} value={form.company} onChange={set("company")} />
          </div>
          <div>
            <label style={lbl}>Company website</label>
            <input style={inp} value={form.company_url} onChange={set("company_url")} />
          </div>
          <div>
            <label style={lbl}>Company description</label>
            <textarea style={{ ...inp, minHeight: 80, resize: "vertical" }} value={form.company_description}
              onChange={set("company_description")} />
          </div>
        </div>

        {error && <div style={{ fontSize: 13, color: c.hot, marginTop: 12 }}>{error}</div>}

        <button type="submit" disabled={busy} style={{
          width: "100%", marginTop: 20, padding: "12px 0", borderRadius: 10, border: "none",
          background: c.accent, color: "#fff", fontWeight: 600, fontSize: 14,
          cursor: busy ? "not-allowed" : "pointer", opacity: busy ? 0.6 : 1,
        }}>{busy ? "Saving…" : "Save and continue"}</button>
        <button type="button" onClick={() => { logout(); navigate("/login"); }} style={{
          width: "100%", marginTop: 8, padding: "6px 0", background: "none", border: "none",
          color: c.textDim, fontSize: 12, cursor: "pointer",
        }}>Sign out</button>
      </form>
    </div>
  );
}

// ── Route protection ──────────────────────────────────────────────────────────
function RequireAuth({ children }) {
  const { isAuthenticated, loading, user } = useAuth();
  if (loading) {
    return <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", color: "#888" }}>Loading…</div>;
  }
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user && !user.email_verified) return <VerifyGate />;
  if (user && !isProfileComplete(user)) return <ProfileGate />;
  return children;
}

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
  const { token } = useAuth();
  // Restore the last viewed campaign/view across page refreshes
  const [activeCampaignId, setActiveCampaignId] = useState(
    () => localStorage.getItem("activeCampaignId") || null
  );

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
      // Show the freshly-run campaign as the selected one (not "Latest pipeline results")
      if (campaignId) setActiveCampaignId(campaignId);
      navigate("/leads");
    }
  }, [isRunning, leads.length, campaignId, fetchCampaigns, navigate]);

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

  const ALL = "__all__";
  const allLeadsView = activeCampaignId === ALL;
  const activeCampaign = activeCampaignId && !allLeadsView
    ? campaigns.find((c) => c.id === activeCampaignId)
    : null;

  // Persist the active view so a refresh keeps the same campaign selected
  useEffect(() => {
    if (activeCampaignId) localStorage.setItem("activeCampaignId", activeCampaignId);
    else localStorage.removeItem("activeCampaignId");
  }, [activeCampaignId]);

  // Once the user is authenticated, restore the last view (campaigns + its leads).
  // These live in memory and are lost on refresh/login — without this the Leads
  // page shows "No leads" until a manual refresh. Runs on login, resets on logout.
  const restoredRef = useRef(false);
  useEffect(() => {
    if (!token) { restoredRef.current = false; return; }
    if (restoredRef.current) return;
    restoredRef.current = true;
    fetchCampaigns();
    const saved = localStorage.getItem("activeCampaignId");
    if (!saved) return;
    (async () => {
      try {
        if (saved === ALL) {
          const data = await getLeads();
          setLeads(data.leads || []);
        } else {
          const fresh = await loadCampaignLeads(saved);
          setLeads(fresh);
        }
      } catch {}
    })();
  }, [token]);

  // View every lead across all campaigns
  const handleViewAll = useCallback(async () => {
    try {
      const data = await getLeads();
      setLeads(data.leads || []);
    } catch {}
    setActiveCampaignId(ALL);
    navigate("/leads");
  }, [setLeads, navigate]);

  // Delete a whole campaign (and all its leads)
  const handleDeleteCampaign = useCallback(async (id) => {
    try { await deleteCampaign(id); } catch (e) { console.error("[App] delete campaign", e); }
    if (activeCampaignId === id) { setActiveCampaignId(null); setLeads([]); }
    fetchCampaigns();
  }, [activeCampaignId, setLeads, fetchCampaigns]);

  const handleRefresh = useCallback(async () => {
    if (activeCampaignId && activeCampaignId !== ALL) {
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
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/register" element={<AuthPage mode="register" />} />
      <Route element={<RequireAuth><Layout isRunning={isRunning} leadsCount={leads.length} /></RequireAuth>}>
        <Route index element={<CampaignPage onLaunch={handleLaunch} onViewCampaign={handleViewCampaign} onDeleteCampaign={handleDeleteCampaign} isRunning={isRunning} campaigns={campaigns} campaignsLoading={campaignsLoading} />} />
        <Route path="pipeline" element={<PipelinePage currentStage={currentStage} logs={logs} isRunning={isRunning} />} />
        <Route path="leads" element={<LeadsPage leads={leads} onUpdateLead={handleUpdateLead} activeCampaign={activeCampaign} campaigns={campaigns} onViewCampaign={handleViewCampaign} onRefresh={handleRefresh} onViewAll={handleViewAll} allLeadsView={allLeadsView} />} />
        <Route path="inbox" element={<InboxPage />} />
        <Route path="analytics" element={<AnalyticsPage leads={leads} campaigns={campaigns} activeCampaign={activeCampaign} />} />
        <Route path="exclusions" element={<ExclusionsPage />} />
        <Route path="settings" element={<SettingsPage />} />
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
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </BrowserRouter>
    </ThemeContext.Provider>
  );
}
