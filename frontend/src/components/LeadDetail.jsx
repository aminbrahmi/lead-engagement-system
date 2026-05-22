// frontend/src/components/LeadDetail.jsx
import React, { useState } from "react";
import { useTheme } from "../App";
import { segmentColor } from "../styles/theme";
import Badge from "./ui/Badge";
import EmailEditor from "./EmailEditor";

export default function LeadDetail({ lead, campaignId, onClose, onUpdateEmail, onUpdateLead }) {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;
  const [editMode, setEditMode] = useState(false);
  const [editFields, setEditFields] = useState({});

  if (!lead) return null;

  const insights = lead.insights || {};
  const insightEntries = Object.entries(insights).filter(
    ([, v]) => v && v !== "No information found." && v !== "N/A"
  );

  let draftEmails = lead.draft_emails;
  if (typeof draftEmails === "string") { try { draftEmails = JSON.parse(draftEmails); } catch { draftEmails = null; } }
  let draftEmail = lead.draft_email;
  if (typeof draftEmail === "string") { try { draftEmail = JSON.parse(draftEmail); } catch { draftEmail = null; } }

  const isCold = lead.segment === "cold" || lead.status === "not_qualified";
  const canEdit = isCold || editMode;

  const handleFieldChange = (field, value) => {
    setEditFields((prev) => ({ ...prev, [field]: value }));
  };

  const handleInsightChange = (key, value) => {
    setEditFields((prev) => ({
      ...prev,
      insights: { ...(prev.insights || insights), [key]: value },
    }));
  };

  const handleSaveManual = () => {
    if (onUpdateLead) {
      const updates = { ...editFields };
      if (updates.email) {
        // New email entered manually — reset verification state
        updates.email_source = "manual";
        updates.email_verified = false;
        // Promote cold lead to warm
        if (lead.segment === "cold") {
          updates.segment = "warm";
          updates.status = "qualified";
          updates.score = Math.max(lead.score || 0, 50);
        }
      }
      onUpdateLead(lead.id, updates);
    }
    setEditMode(false);
    setEditFields({});
  };

  const insightKeys = ["recent_news", "person_highlights", "company_challenge", "tech_stack", "icebreaker", "value_angle"];

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
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ fontFamily: f.mono, fontSize: 28, fontWeight: 700, color: segmentColor(lead.segment, theme) }}>{lead.score}</div>
            <Badge segment={lead.segment} />
          </div>
          {/* Edit toggle for non-cold leads */}
          {!isCold && (
            <button onClick={() => setEditMode(!editMode)} style={{
              padding: "5px 10px", borderRadius: 6, border: `1px solid ${c.border}`,
              background: editMode ? c.accentGlow : "transparent", color: editMode ? c.accent : c.textMuted,
              fontSize: 11, cursor: "pointer", fontFamily: f.mono,
            }}>{editMode ? "Cancel" : "Edit"}</button>
          )}
        </div>
      </div>

      {/* Cold lead banner */}
      {isCold && (
        <div style={{
          padding: "10px 14px", borderRadius: 8, marginBottom: 16, fontSize: 13,
          background: c.warmGlow, color: c.warm, lineHeight: 1.6,
          border: `1px solid ${c.warm}22`,
        }}>
          This lead is not qualified (no email found). You can manually add an email and insights below to re-qualify and send emails.
        </div>
      )}

      {/* Info grid — editable for cold/edit mode */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px 24px", marginBottom: 24, fontSize: 13 }}>
        {[
          ["Location", "location", lead.location],
          ["Email", "email", lead.email || ""],
          ["Email source", "email_source", lead.email_source || ""],
          ["SMTP verified", null, lead.email_verified ? "Yes" : "No"],
        ].map(([label, field, value]) => (
          <div key={label}>
            <span style={{ color: c.textDim, fontSize: 10, textTransform: "uppercase", letterSpacing: 1, fontWeight: 600 }}>{label}</span>
            {canEdit && field ? (
              <input
                value={editFields[field] !== undefined ? editFields[field] : value}
                onChange={(e) => handleFieldChange(field, e.target.value)}
                placeholder={`Enter ${label.toLowerCase()}`}
                style={{
                  display: "block", width: "100%", marginTop: 4, padding: "6px 10px", borderRadius: 6,
                  border: `1px solid ${c.border}`, background: c.bg, color: c.text,
                  fontFamily: f.mono, fontSize: 12, outline: "none",
                }}
              />
            ) : (
              <div style={{
                color: label === "SMTP verified" ? (lead.email_verified ? c.green : c.warm) : c.textMuted,
                fontFamily: f.mono, fontSize: 12, marginTop: 2, wordBreak: "break-all",
              }}>{value || "\u2014"}</div>
            )}
          </div>
        ))}
      </div>

      {/* Insights — editable for cold/edit mode */}
      <div style={{ marginBottom: 24 }}>
        <h4 style={{ fontSize: 10, color: c.textDim, textTransform: "uppercase", letterSpacing: 1, fontWeight: 700, marginBottom: 12 }}>
          Research insights {canEdit && <span style={{ color: c.accent, fontWeight: 400 }}>(editable)</span>}
        </h4>
        <div style={{ display: "grid", gap: 8 }}>
          {(canEdit ? insightKeys : insightEntries.map(([k]) => k)).map((key) => {
            const val = (editFields.insights && editFields.insights[key] !== undefined)
              ? editFields.insights[key]
              : (insights[key] || "");
            const displayKey = key.replace(/_/g, " ");

            return (
              <div key={key} style={{ background: c.bg, borderRadius: 8, padding: "10px 14px", fontSize: 12, border: `1px solid ${c.border}` }}>
                <span style={{ color: c.accent, fontWeight: 600, fontSize: 10, textTransform: "uppercase", letterSpacing: .5 }}>{displayKey}</span>
                {canEdit ? (
                  <textarea
                    value={val}
                    onChange={(e) => handleInsightChange(key, e.target.value)}
                    placeholder={`Enter ${displayKey}...`}
                    rows={2}
                    style={{
                      display: "block", width: "100%", marginTop: 6, padding: "6px 8px", borderRadius: 4,
                      border: `1px solid ${c.border}`, background: c.surface, color: c.text,
                      fontFamily: f.body, fontSize: 12, lineHeight: 1.5, outline: "none", resize: "vertical",
                    }}
                  />
                ) : (
                  <div style={{ color: c.textMuted, marginTop: 4, lineHeight: 1.6 }}>{val || "\u2014"}</div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Save manual changes button */}
      {canEdit && (Object.keys(editFields).length > 0) && (
        <div style={{ marginBottom: 20 }}>
          <button onClick={handleSaveManual} style={{
            padding: "8px 20px", borderRadius: 8, border: "none", cursor: "pointer",
            background: c.accent, color: "#fff", fontSize: 13, fontWeight: 600, fontFamily: f.body,
          }}>
            {isCold ? "Save and re-qualify as WARM" : "Save changes"}
          </button>
        </div>
      )}

      {/* Score reason */}
      {lead.reason && (
        <div style={{ background: c.bg, borderRadius: 8, padding: "10px 14px", fontSize: 12, color: c.textMuted, marginBottom: 20, lineHeight: 1.6, border: `1px solid ${c.border}` }}>
          <span style={{ color: c.textDim, fontWeight: 700, fontSize: 10, textTransform: "uppercase", letterSpacing: .5 }}>Score reason: </span>{lead.reason}
        </div>
      )}

      {/* Email editor — only if lead has email */}
      {(lead.email || editFields.email) && (
        <EmailEditor
          key={lead.id}
          leadId={lead.id}
          campaignId={campaignId}
          leadEmail={editFields.email || lead.email}
          emailVerified={lead.email_verified}
          draftEmail={draftEmail}
          draftEmails={draftEmails}
          onSave={onUpdateEmail}
        />
      )}
    </div>
  );
}
