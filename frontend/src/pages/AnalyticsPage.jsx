// src/pages/AnalyticsPage.jsx
import React from "react";
import AnalyticsPanel from "../components/AnalyticsPanel";
import { useTheme } from "../App";

export default function AnalyticsPage({ leads }) {
  const { theme } = useTheme();
  const c = theme.colors;

  if (leads.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 80, color: c.textDim }}>
        <p style={{ fontSize: 40, marginBottom: 16 }}>&#128202;</p>
        <p>Launch a campaign to see analytics</p>
      </div>
    );
  }

  return <AnalyticsPanel leads={leads} />;
}
