// src/components/LeadTable.jsx — Simplified (no email verification column)
import React, { useState } from "react";
import { useTheme } from "../App";
import { segmentColor } from "../styles/theme";
import Badge from "./ui/Badge";

export default function LeadTable({ leads, onSelect, selectedId }) {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;
  const [filter, setFilter] = useState("all");
  const filtered = filter === "all" ? leads : leads.filter((l) => l.segment === filter);
  const counts = {
    all: leads.length,
    hot: leads.filter((l) => l.segment === "hot").length,
    warm: leads.filter((l) => l.segment === "warm").length,
    cold: leads.filter((l) => l.segment === "cold").length,
  };

  return (
    <div style={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 14, overflow: "hidden" }}>
      <div style={{
        padding: "16px 24px", borderBottom: `1px solid ${c.border}`,
        display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12,
      }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, color: c.text }}>Leads ({filtered.length})</h3>
        <div style={{ display: "flex", gap: 6 }}>
          {["all", "hot", "warm", "cold"].map((seg) => (
            <button key={seg} onClick={() => setFilter(seg)} style={{
              padding: "4px 12px", borderRadius: 6,
              border: `1px solid ${filter === seg ? c.accent : c.border}`,
              background: filter === seg ? c.accentGlow : "transparent",
              color: filter === seg ? c.accent : c.textMuted,
              fontSize: 12, cursor: "pointer", fontFamily: f.body,
              textTransform: "capitalize", fontWeight: filter === seg ? 600 : 400,
            }}>{seg} ({counts[seg]})</button>
          ))}
        </div>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${c.border}` }}>
              {/* Removed email verification column */}
              {["Name", "Company", "Role", "Score", "Segment", "Email", "Emails", "Status"].map((h) => (
                <th key={h} style={{
                  padding: "10px 16px", textAlign: "left", fontSize: 10,
                  color: c.textDim, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase",
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((lead) => {
              const hasAB = lead.draft_emails && (typeof lead.draft_emails === "object"
                ? Object.keys(lead.draft_emails).length > 1
                : false);

              return (
                <tr
                  key={lead.id || lead.company}
                  onClick={() => onSelect(lead)}
                  style={{
                    cursor: "pointer", borderBottom: `1px solid ${c.border}`,
                    background: selectedId === lead.id ? c.accentGlow : "transparent",
                    transition: "background .15s",
                  }}
                  onMouseEnter={(e) => { if (selectedId !== lead.id) e.currentTarget.style.background = c.surfaceHover || c.surfaceAlt; }}
                  onMouseLeave={(e) => { if (selectedId !== lead.id) e.currentTarget.style.background = "transparent"; }}
                >
                  <td style={{ padding: "12px 16px", fontWeight: 500, color: c.text }}>
                    {!lead.name || lead.name === "unknown"
                      ? <span style={{ color: c.textDim, fontStyle: "italic" }}>Unknown</span>
                      : lead.name}
                  </td>
                  <td style={{ padding: "12px 16px", color: c.text }}>{lead.company}</td>
                  <td style={{ padding: "12px 16px", color: c.textMuted }}>{lead.role}</td>
                  <td style={{ padding: "12px 16px", minWidth: 80 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontFamily: f.mono, fontWeight: 700, color: segmentColor(lead.segment, theme), minWidth: 24 }}>{lead.score}</span>
                      <div style={{ flex: 1, height: 4, borderRadius: 2, background: c.border, maxWidth: 50 }}>
                        <div style={{
                          width: `${lead.score}%`, height: "100%", borderRadius: 2,
                          background: segmentColor(lead.segment, theme), transition: "width .3s",
                        }} />
                      </div>
                    </div>
                  </td>
                  <td style={{ padding: "12px 16px" }}><Badge segment={lead.segment} /></td>
                  <td style={{ padding: "12px 16px", fontFamily: f.mono, fontSize: 12, color: lead.email ? c.textMuted : c.textDim, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {lead.email || "\u2014"}
                  </td>
                  {/* Removed email verification icon column */}
                  <td style={{ padding: "12px 8px" }}>
                    {hasAB ? (
                      <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: c.accentGlow, color: c.accent, fontFamily: f.mono, fontWeight: 600 }}>A/B</span>
                    ) : lead.draft_email ? (
                      <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: c.greenGlow, color: c.green, fontFamily: f.mono, fontWeight: 600 }}>1</span>
                    ) : (
                      <span style={{ fontSize: 12, color: c.textDim }}>\u2014</span>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <span style={{
                      fontSize: 10, padding: "3px 8px", borderRadius: 4, fontFamily: f.mono, fontWeight: 600,
                      background: lead.status === "enriched" ? c.greenGlow : c.surfaceAlt,
                      color: lead.status === "enriched" ? c.green : c.textMuted,
                    }}>{lead.status}</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <div style={{ padding: 40, textAlign: "center", color: c.textDim, fontSize: 13 }}>
            No leads match this filter.
          </div>
        )}
      </div>
    </div>
  );
}