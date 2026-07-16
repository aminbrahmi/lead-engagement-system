// src/components/LeadTable.jsx — Simplified (no email verification column)
import React, { useState } from "react";
import { useTheme } from "../App";
import { segmentColor } from "../styles/theme";
import Badge from "./ui/Badge";

const API = process.env.REACT_APP_API_URL || "http://localhost:8000";

function ConfirmModal({ lead, onConfirm, onCancel, theme }) {
  const c = theme.colors;
  const f = theme.fonts;
  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.45)", display: "flex",
      alignItems: "center", justifyContent: "center",
    }}
      onClick={onCancel}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: c.surface, border: `1px solid ${c.border}`,
          borderRadius: 14, padding: "28px 32px", width: 360,
          boxShadow: "0 16px 48px rgba(0,0,0,0.3)",
        }}
      >
        <div style={{ fontSize: 32, marginBottom: 12, textAlign: "center" }}>🗑</div>
        <p style={{ fontSize: 15, fontWeight: 600, color: c.text, textAlign: "center", marginBottom: 6 }}>
          Delete lead?
        </p>
        <p style={{ fontSize: 13, color: c.textMuted, textAlign: "center", marginBottom: 24, lineHeight: 1.5 }}>
          <strong style={{ color: c.text }}>{lead.name && lead.name !== "unknown" ? lead.name : lead.company}</strong>
          {" "}will be permanently removed.
        </p>
        <div style={{ display: "flex", gap: 10 }}>
          <button
            onClick={onCancel}
            style={{
              flex: 1, padding: "9px 0", borderRadius: 8,
              border: `1px solid ${c.border}`, background: "transparent",
              color: c.textMuted, fontSize: 13, cursor: "pointer", fontFamily: f.body, fontWeight: 500,
            }}
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            style={{
              flex: 1, padding: "9px 0", borderRadius: 8,
              border: "none", background: "#ff6b6b",
              color: "#fff", fontSize: 13, cursor: "pointer", fontFamily: f.body, fontWeight: 600,
            }}
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

export default function LeadTable({ leads, onSelect, selectedId, onDelete, replyScores }) {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;
  const [filter, setFilter] = useState("all");
  const [sortBy, setSortBy] = useState("date");   // date | name | score | reply
  const [pendingDelete, setPendingDelete] = useState(null);

  const base = filter === "all" ? leads : leads.filter((l) => l.segment === filter);
  const filtered = [...base].sort((a, b) => {
    if (sortBy === "name") return (a.name || "").localeCompare(b.name || "");
    if (sortBy === "score") return (b.score || 0) - (a.score || 0);
    if (sortBy === "reply") return ((replyScores?.[b.id] ?? -1) - (replyScores?.[a.id] ?? -1));
    // date (most recent first)
    return new Date(b.updated_at || b.created_at || 0) - new Date(a.updated_at || a.created_at || 0);
  });
  const counts = {
    all: leads.length,
    hot: leads.filter((l) => l.segment === "hot").length,
    warm: leads.filter((l) => l.segment === "warm").length,
    cold: leads.filter((l) => l.segment === "cold").length,
  };

  const handleDeleteConfirmed = async () => {
    const lead = pendingDelete;
    setPendingDelete(null);
    try {
      await fetch(`${API}/leads/${lead.id}`, { method: "DELETE" });
      onDelete?.(lead.id);
    } catch {}
  };

  return (
    <>
    {pendingDelete && (
      <ConfirmModal
        lead={pendingDelete}
        theme={theme}
        onConfirm={handleDeleteConfirmed}
        onCancel={() => setPendingDelete(null)}
      />
    )}
    <div style={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 14, overflow: "hidden" }}>
      <div style={{
        padding: "16px 24px", borderBottom: `1px solid ${c.border}`,
        display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12,
      }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, color: c.text }}>Leads ({filtered.length})</h3>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
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
          {/* Sort control */}
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 11, color: c.textDim }}>Sort:</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              title="Sort leads"
              style={{
                padding: "5px 10px", borderRadius: 6, border: `1px solid ${c.border}`,
                background: c.surface, color: c.text, fontSize: 12, fontFamily: f.body, cursor: "pointer",
              }}
            >
              <option value="date">Date</option>
              <option value="name">Name</option>
              <option value="score">Score</option>
              {replyScores && <option value="reply">Reply %</option>}
            </select>
          </div>
        </div>
      </div>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${c.border}` }}>
              {/* Removed email verification column */}
              {["Name", "Company", "Role", "Score", ...(replyScores ? ["Reply %"] : []), "Segment", "Email", "Emails", "Status", ""].map((h) => (
                <th key={h} style={{
                  padding: "10px 16px", textAlign: "left", fontSize: 10,
                  color: c.textDim, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase",
                  whiteSpace: "nowrap",
                }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((lead) => {
              // draft_emails may arrive as a JSON string — parse before counting variants
              let de = lead.draft_emails;
              if (typeof de === "string") { try { de = JSON.parse(de); } catch { de = null; } }
              const variantCount = de && typeof de === "object" ? Object.keys(de).length : 0;
              const hasAB = variantCount > 1;

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
                  {replyScores && (
                    <td style={{ padding: "12px 16px", minWidth: 70 }}>
                      {typeof replyScores[lead.id] === "number" ? (
                        <span style={{
                          fontSize: 11, fontWeight: 700, fontFamily: f.mono, padding: "2px 8px", borderRadius: 4,
                          color: replyScores[lead.id] >= 60 ? c.green : replyScores[lead.id] >= 40 ? c.warm : c.textMuted,
                          background: replyScores[lead.id] >= 60 ? c.greenGlow : replyScores[lead.id] >= 40 ? c.warmGlow : c.surfaceAlt,
                        }} title="Predicted reply probability (ML)">{replyScores[lead.id]}%</span>
                      ) : <span style={{ color: c.textDim }}>—</span>}
                    </td>
                  )}
                  <td style={{ padding: "12px 16px" }}><Badge segment={lead.segment} /></td>
                  <td style={{ padding: "12px 16px", fontFamily: f.mono, fontSize: 12, color: lead.email ? c.textMuted : c.textDim, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {lead.email || "\u2014"}
                  </td>
                  {/* Removed email verification icon column */}
                  <td style={{ padding: "12px 8px" }}>
                    {hasAB ? (
                      <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: c.accentGlow, color: c.accent, fontFamily: f.mono, fontWeight: 600 }}>A/B</span>
                    ) : (variantCount === 1 || lead.draft_email) ? (
                      <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: c.greenGlow, color: c.green, fontFamily: f.mono, fontWeight: 600 }}>1</span>
                    ) : (
                      <span style={{ fontSize: 12, color: c.textDim }}>{"\u2014"}</span>
                    )}
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <span style={{
                      fontSize: 10, padding: "3px 8px", borderRadius: 4, fontFamily: f.mono, fontWeight: 600,
                      background: lead.status === "enriched" ? c.greenGlow : c.surfaceAlt,
                      color: lead.status === "enriched" ? c.green : c.textMuted,
                    }}>{lead.status}</span>
                  </td>
                  <td style={{ padding: "8px 12px" }} onClick={(e) => e.stopPropagation()}>
                    <button
                      onClick={() => setPendingDelete(lead)}
                      style={{
                        background: "none", border: `1px solid transparent`, borderRadius: 6,
                        cursor: "pointer", color: c.textDim, fontSize: 14, padding: "4px 7px",
                        transition: "all .15s", lineHeight: 1,
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.color = "#ff6b6b";
                        e.currentTarget.style.borderColor = "#ff6b6b33";
                        e.currentTarget.style.background = "#ff6b6b11";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.color = c.textDim;
                        e.currentTarget.style.borderColor = "transparent";
                        e.currentTarget.style.background = "none";
                      }}
                      title="Delete lead"
                    >
                      🗑
                    </button>
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
    </>
  );
}