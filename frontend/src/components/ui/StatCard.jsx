// src/components/ui/StatCard.jsx
import React from "react";
import { useTheme } from "../../App";

export default function StatCard({ label, value, sub, color }) {
  const { theme } = useTheme();
  const c = theme.colors;
  return (
    <div style={{
      background: c.surface, border: `1px solid ${c.border}`, borderRadius: 12,
      padding: "18px 22px", flex: 1, minWidth: 140,
    }}>
      <div style={{ fontSize: 11, color: c.textDim, marginBottom: 6, letterSpacing: 1, textTransform: "uppercase", fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 30, fontWeight: 700, color: color || c.text, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: c.textDim, marginTop: 6 }}>{sub}</div>}
    </div>
  );
}
