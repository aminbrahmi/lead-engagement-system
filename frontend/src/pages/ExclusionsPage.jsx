// src/pages/ExclusionsPage.jsx
import React, { useState, useEffect, useCallback } from "react";
import { useTheme } from "../App";
import { getExclusions, addExclusion, removeExclusion } from "../api/exclusions";

const TYPE_LABEL = {
  email: "Email",
  domain: "Domain",
  company: "Company",
};

const TYPE_COLOR = (type, c) => {
  if (type === "email") return c.accent;
  if (type === "domain") return c.warm;
  return c.textMuted;
};

export default function ExclusionsPage() {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;

  const [exclusions, setExclusions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  // Add-form state
  const [newValue, setNewValue] = useState("");
  const [newType, setNewType] = useState("email");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getExclusions();
      setExclusions(data.exclusions || []);
    } catch {
      setExclusions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleAdd = async () => {
    const val = newValue.trim();
    if (!val) return;
    setAdding(true);
    try {
      await addExclusion(val, newType, "Manually added");
      setNewValue("");
      await load();
    } catch {} finally {
      setAdding(false);
    }
  };

  const handleRemove = async (exc) => {
    const isEmail = exc.type === "email";
    const verb = isEmail ? "Resubscribe" : "Remove";
    if (!window.confirm(`${verb} "${exc.value}"? It will no longer be excluded from campaigns.`)) return;
    try {
      await removeExclusion(exc.id);
      setExclusions((prev) => prev.filter((e) => e.id !== exc.id));
    } catch {}
  };

  const counts = {
    all: exclusions.length,
    email: exclusions.filter((e) => e.type === "email").length,
    domain: exclusions.filter((e) => e.type === "domain").length,
    company: exclusions.filter((e) => e.type === "company").length,
  };
  const filtered = filter === "all" ? exclusions : exclusions.filter((e) => e.type === filter);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Header */}
      <div>
        <h2 style={{ fontSize: 20, fontWeight: 700, color: c.text, margin: 0 }}>Exclusion list</h2>
        <p style={{ fontSize: 13, color: c.textDim, marginTop: 4 }}>
          Emails, domains, and companies that will never be contacted. Unsubscribed leads land here automatically.
        </p>
      </div>

      {/* Add form */}
      <div style={{
        background: c.surface, border: `1px solid ${c.border}`, borderRadius: 12,
        padding: 16, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap",
      }}>
        <select
          value={newType}
          onChange={(e) => setNewType(e.target.value)}
          style={{
            padding: "8px 12px", borderRadius: 8, border: `1px solid ${c.border}`,
            background: c.bg, color: c.text, fontSize: 13, fontFamily: f.body, cursor: "pointer",
          }}
        >
          <option value="email">Email</option>
          <option value="domain">Domain</option>
          <option value="company">Company</option>
        </select>
        <input
          value={newValue}
          onChange={(e) => setNewValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          placeholder={newType === "email" ? "name@company.com" : newType === "domain" ? "company.com" : "Company name"}
          style={{
            flex: 1, minWidth: 200, padding: "8px 12px", borderRadius: 8,
            border: `1px solid ${c.border}`, background: c.bg, color: c.text,
            fontSize: 13, fontFamily: f.body,
          }}
        />
        <button
          onClick={handleAdd}
          disabled={adding || !newValue.trim()}
          style={{
            padding: "8px 18px", borderRadius: 8, border: "none",
            background: c.accent, color: "#fff", fontSize: 13, fontWeight: 600,
            cursor: adding || !newValue.trim() ? "not-allowed" : "pointer",
            opacity: adding || !newValue.trim() ? 0.5 : 1, fontFamily: f.body,
          }}
        >
          {adding ? "Adding…" : "Add exclusion"}
        </button>
      </div>

      {/* List card */}
      <div style={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 14, overflow: "hidden" }}>
        <div style={{
          padding: "16px 24px", borderBottom: `1px solid ${c.border}`,
          display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12,
        }}>
          <h3 style={{ fontSize: 15, fontWeight: 600, color: c.text }}>Excluded ({filtered.length})</h3>
          <div style={{ display: "flex", gap: 6 }}>
            {["all", "email", "domain", "company"].map((t) => (
              <button key={t} onClick={() => setFilter(t)} style={{
                padding: "4px 12px", borderRadius: 6,
                border: `1px solid ${filter === t ? c.accent : c.border}`,
                background: filter === t ? c.accentGlow : "transparent",
                color: filter === t ? c.accent : c.textMuted,
                fontSize: 12, cursor: "pointer", fontFamily: f.body,
                textTransform: "capitalize", fontWeight: filter === t ? 600 : 400,
              }}>{t} ({counts[t]})</button>
            ))}
          </div>
        </div>

        {loading ? (
          <div style={{ padding: 40, textAlign: "center", color: c.textDim, fontSize: 13 }}>Loading…</div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: c.textDim, fontSize: 13 }}>
            No exclusions {filter !== "all" ? `of type "${filter}"` : "yet"}.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${c.border}` }}>
                  {["Value", "Type", "Reason", "Added", ""].map((h) => (
                    <th key={h} style={{
                      padding: "10px 16px", textAlign: "left", fontSize: 10,
                      color: c.textDim, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase",
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((exc) => (
                  <tr key={exc.id} style={{ borderBottom: `1px solid ${c.border}` }}>
                    <td style={{ padding: "12px 16px", fontFamily: f.mono, color: c.text, fontWeight: 500 }}>
                      {exc.value}
                    </td>
                    <td style={{ padding: "12px 16px" }}>
                      <span style={{
                        fontSize: 10, padding: "3px 8px", borderRadius: 4, fontFamily: f.mono, fontWeight: 600,
                        background: c.surfaceAlt, color: TYPE_COLOR(exc.type, c),
                      }}>{TYPE_LABEL[exc.type] || exc.type}</span>
                    </td>
                    <td style={{ padding: "12px 16px", color: c.textMuted }}>{exc.reason || "—"}</td>
                    <td style={{ padding: "12px 16px", color: c.textDim, fontFamily: f.mono, fontSize: 12 }}>
                      {exc.created_at ? new Date(exc.created_at).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" }) : "—"}
                    </td>
                    <td style={{ padding: "8px 16px", textAlign: "right" }}>
                      <button
                        onClick={() => handleRemove(exc)}
                        style={{
                          padding: "5px 12px", borderRadius: 6,
                          border: `1px solid ${exc.type === "email" ? c.accent : c.border}`,
                          background: exc.type === "email" ? c.accentGlow : "transparent",
                          color: exc.type === "email" ? c.accent : c.textMuted,
                          fontSize: 12, cursor: "pointer", fontFamily: f.body, fontWeight: 500,
                          whiteSpace: "nowrap",
                        }}
                        title={exc.type === "email" ? "Re-enable emails to this address" : "Remove from exclusion list"}
                      >
                        {exc.type === "email" ? "Resubscribe" : "Remove"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
