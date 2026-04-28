// src/components/LeadDetail.jsx — Simplified (no email verification info)
import React from "react";
import { useTheme } from "../App";
import { segmentColor } from "../styles/theme";
import Badge from "./ui/Badge";
import EmailEditor from "./EmailEditor";

export default function LeadDetail({ lead, onClose, onUpdateEmail }) {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;
  if (!lead) return null;

  const insights = lead.insights || {};
  const insightEntries = Object.entries(insights).filter(
    ([, v]) => v && v !== "No information found." && v !== "N/A"
  );

  // Parse draft_emails if it's a string
  let draftEmails = lead.draft_emails;
  if (typeof draftEmails === "string") {
    try { draftEmails = JSON.parse(draftEmails); } catch { draftEmails = null; }
  }
  let draftEmail = lead.draft_email;
  if (typeof draftEmail === "string") {
    try { draftEmail = JSON.parse(draftEmail); } catch { draftEmail = null; }
  }

  return (
    <div style={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 14, padding: 28, position: "relative" }}>
      <button onClick={onClose} style={{ position: "absolute", top: 16, right: 16, background: "none", border: "none", color: c.textMuted, cursor: "pointer", fontSize: 18 }}>x</button>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 24 }}>
        <div style={{
          width: 48, height: 48, borderRadius: 10, display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 20, fontWeight: 700,
          background: `linear-gradient(135deg, ${segmentColor(lead.segment, theme)}22, ${segmentColor(lead.segment, theme)}08)`,
          border: `1px solid ${segmentColor(lead.segment, theme)}33`, color: segmentColor(lead.segment, theme),
        }}>{lead.name && lead.name !== "unknown" ? lead.name[0] : "?"}</div>
        <div>
          <h3 style={{ fontSize: 18, fontWeight: 600, color: c.text }}>{lead.name}</h3>
          <div style={{ fontSize: 13, color: c.textMuted }}>{lead.role} @ {lead.company}</div>
        </div>
        <div style={{ marginLeft: "auto", textAlign: "right" }}>
          <div style={{ fontFamily: f.mono, fontSize: 28, fontWeight: 700, color: segmentColor(lead.segment, theme) }}>{lead.score}</div>
          <Badge segment={lead.segment} />
        </div>
      </div>

      {/* Info grid - Removed SMTP verified field */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 24px", marginBottom: 24, fontSize: 13 }}>
        {[
          ["Location", lead.location],
          ["Email", lead.email || "\u2014"],
          ["Email source", lead.email_source || "\u2014"],
          // Removed: ["SMTP verified", lead.email_verified ? "Yes" : "No"],
        ].map(([k, v]) => (
          <div key={k}>
            <span style={{ color: c.textDim, fontSize: 10, textTransform: "uppercase", letterSpacing: 1, fontWeight: 600 }}>{k}</span>
            <div style={{
              color: c.textMuted,
              fontFamily: f.mono, fontSize: 12, marginTop: 2, wordBreak: "break-all",
            }}>{v}</div>
          </div>
        ))}
      </div>

      {/* Score reason */}
      {lead.reason && (
        <div style={{ background: c.bg, borderRadius: 8, padding: "10px 14px", fontSize: 12, color: c.textMuted, marginBottom: 20, lineHeight: 1.6, border: `1px solid ${c.border}` }}>
          <span style={{ color: c.textDim, fontWeight: 700, fontSize: 10, textTransform: "uppercase", letterSpacing: .5 }}>Score reason: </span>{lead.reason}
        </div>
      )}

      {/* Insights */}
      {insightEntries.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h4 style={{ fontSize: 10, color: c.textDim, textTransform: "uppercase", letterSpacing: 1, fontWeight: 700, marginBottom: 12 }}>Research insights</h4>
          <div style={{ display: "grid", gap: 8 }}>
            {insightEntries.map(([key, val]) => (
              <div key={key} style={{ background: c.bg, borderRadius: 8, padding: "10px 14px", fontSize: 12, border: `1px solid ${c.border}` }}>
                <span style={{ color: c.accent, fontWeight: 600, fontSize: 10, textTransform: "uppercase", letterSpacing: .5 }}>{key.replace(/_/g, " ")}</span>
                <div style={{ color: c.textMuted, marginTop: 4, lineHeight: 1.6 }}>{val}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Email editor - Simplified, removed emailVerified and emailSource props */}
      <EmailEditor
        leadId={lead.id}
        leadEmail={lead.email}
        draftEmail={draftEmail}
        draftEmails={draftEmails}
        onSave={onUpdateEmail}
        onRefresh={() => window.location.reload()}
      />
    </div>
  );
}