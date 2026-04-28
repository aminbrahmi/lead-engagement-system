// src/pages/LeadsPage.jsx
import React, { useState } from "react";
import LeadTable from "../components/LeadTable";
import LeadDetail from "../components/LeadDetail";
import { useTheme } from "../App";

export default function LeadsPage({ leads, onUpdateLead, activeCampaign, campaigns, onViewCampaign }) {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;
  const [selected, setSelected] = useState(null);
  const [showDropdown, setShowDropdown] = useState(false);

  const handleUpdateEmail = (leadId, emailData) => {
    onUpdateLead(leadId, { draft_email: emailData });
    if (selected?.id === leadId) {
      setSelected((prev) => ({ ...prev, draft_email: emailData }));
    }
  };

  const truncate = (str, len = 60) =>
    str && str.length > len ? str.slice(0, len) + "..." : str || "";

  if (leads.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 80, color: c.textDim }}>
        <p style={{ fontSize: 40, marginBottom: 16 }}>&#128101;</p>
        <p>No leads yet — launch a campaign</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* ── Campaign breadcrumb / selector ── */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexWrap: "wrap", gap: 12,
      }}>
        {/* Left: active campaign info */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {activeCampaign ? (
            <>
              <span style={{
                fontSize: 10, padding: "3px 8px", borderRadius: 4,
                background: c.accentGlow, color: c.accent,
                fontFamily: f.mono, fontWeight: 600, textTransform: "uppercase",
              }}>
                Campaign
              </span>
              <span style={{ fontSize: 14, fontWeight: 500, color: c.text }}>
                {truncate(activeCampaign.prompt, 70)}
              </span>
              <span style={{ fontSize: 12, color: c.textDim, fontFamily: f.mono }}>
                {activeCampaign.leads_count || leads.length} leads
              </span>
            </>
          ) : (
            <span style={{ fontSize: 14, fontWeight: 500, color: c.text }}>
              Latest pipeline results
            </span>
          )}
        </div>

        {/* Right: campaign switcher dropdown */}
        {campaigns && campaigns.length > 0 && (
          <div style={{ position: "relative" }}>
            <button
              onClick={() => setShowDropdown(!showDropdown)}
              style={{
                padding: "6px 14px", borderRadius: 6,
                border: `1px solid ${c.border}`, background: c.surface,
                color: c.textMuted, fontSize: 12, cursor: "pointer",
                fontFamily: f.body, fontWeight: 500, display: "flex",
                alignItems: "center", gap: 6,
              }}
            >
              Switch campaign
              <span style={{ fontSize: 10, transform: showDropdown ? "rotate(180deg)" : "none", transition: "transform .2s" }}>
                &#9660;
              </span>
            </button>

            {/* Dropdown */}
            {showDropdown && (
              <div style={{
                position: "absolute", top: "calc(100% + 6px)", right: 0,
                width: 380, maxHeight: 320, overflowY: "auto",
                background: c.surface, border: `1px solid ${c.border}`,
                borderRadius: 10, zIndex: 100,
                boxShadow: "0 8px 32px rgba(0,0,0,0.2)",
              }}>
                {campaigns.map((camp) => (
                  <button
                    key={camp.id}
                    onClick={() => {
                      onViewCampaign(camp);
                      setShowDropdown(false);
                      setSelected(null);
                    }}
                    style={{
                      display: "block", width: "100%", textAlign: "left",
                      padding: "12px 16px",
                      borderBottom: `1px solid ${c.border}`,
                      background: activeCampaign?.id === camp.id ? c.accentGlow : "transparent",
                      color: c.text, fontSize: 13, cursor: "pointer",
                      fontFamily: f.body, border: "none",
                      borderBottom: `1px solid ${c.border}`,
                      transition: "background .1s",
                    }}
                    onMouseEnter={(e) => {
                      if (activeCampaign?.id !== camp.id)
                        e.currentTarget.style.background = c.surfaceHover || c.surfaceAlt;
                    }}
                    onMouseLeave={(e) => {
                      if (activeCampaign?.id !== camp.id)
                        e.currentTarget.style.background = "transparent";
                    }}
                  >
                    <div style={{ fontWeight: 500, marginBottom: 4, lineHeight: 1.4 }}>
                      {truncate(camp.prompt, 55)}
                    </div>
                    <div style={{ display: "flex", gap: 8, fontSize: 11, color: c.textDim }}>
                      <span style={{ fontFamily: f.mono }}>{camp.leads_count || 0} leads</span>
                      {camp.hot_count > 0 && <span style={{ color: c.hot }}>{camp.hot_count} hot</span>}
                      {camp.warm_count > 0 && <span style={{ color: c.warm }}>{camp.warm_count} warm</span>}
                      <span>
                        {camp.updated_at
                          ? new Date(camp.updated_at).toLocaleDateString("en", { month: "short", day: "numeric" })
                          : ""}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Lead table ── */}
      <LeadTable leads={leads} onSelect={setSelected} selectedId={selected?.id} />

      {/* ── Lead detail ── */}
      {selected && (
        <LeadDetail
          lead={selected}
          onClose={() => setSelected(null)}
          onUpdateEmail={handleUpdateEmail}
        />
      )}
    </div>
  );
}
