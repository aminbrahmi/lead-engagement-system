// src/components/AnalyticsPanel.jsx
import React from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";
import { useTheme } from "../App";
import StatCard from "./ui/StatCard";

export default function AnalyticsPanel({ leads }) {
  const { theme } = useTheme();
  const c = theme.colors;

  const hot = leads.filter((l) => l.segment === "hot").length;
  const warm = leads.filter((l) => l.segment === "warm").length;
  const cold = leads.filter((l) => l.segment === "cold").length;
  const withEmail = leads.filter((l) => l.email).length;
  const withDraft = leads.filter((l) => l.draft_email).length;
  const avgScore = leads.length ? Math.round(leads.reduce((a, l) => a + (l.score || 0), 0) / leads.length) : 0;

  const pieData = [
    { name: "Hot", value: hot, color: c.hot },
    { name: "Warm", value: warm, color: c.warm },
    { name: "Cold", value: cold, color: c.cold },
  ].filter((d) => d.value > 0);

  const scoreDist = [
    { range: "0-20", count: leads.filter((l) => l.score <= 20).length },
    { range: "21-40", count: leads.filter((l) => l.score > 20 && l.score <= 40).length },
    { range: "41-60", count: leads.filter((l) => l.score > 40 && l.score <= 60).length },
    { range: "61-80", count: leads.filter((l) => l.score > 60 && l.score <= 80).length },
    { range: "81-100", count: leads.filter((l) => l.score > 80).length },
  ];

  const tt = { contentStyle: { background: c.surface, border: `1px solid ${c.border}`, borderRadius: 8, fontSize: 12, color: c.text } };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <StatCard label="Total leads" value={leads.length} />
        <StatCard label="Avg score" value={avgScore} color={avgScore >= 60 ? c.green : c.warm} />
        <StatCard label="Emails found" value={withEmail} sub={`${leads.length ? Math.round(withEmail / leads.length * 100) : 0}% coverage`} color={c.accent} />
        <StatCard label="Drafts ready" value={withDraft} color={c.green} />
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
        <div style={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 14, padding: 24 }}>
          <h4 style={{ fontSize: 10, color: c.textDim, textTransform: "uppercase", letterSpacing: 1, fontWeight: 700, marginBottom: 16 }}>Segment distribution</h4>
          <ResponsiveContainer width="100%" height={180}>
            <PieChart><Pie data={pieData} dataKey="value" cx="50%" cy="50%" innerRadius={42} outerRadius={72} paddingAngle={4} strokeWidth={0}>{pieData.map((d, i) => <Cell key={i} fill={d.color} />)}</Pie><Tooltip {...tt} /></PieChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", justifyContent: "center", gap: 20, fontSize: 12, marginTop: 4 }}>
            {pieData.map((d) => <span key={d.name} style={{ color: d.color, fontWeight: 500 }}>{d.name}: {d.value}</span>)}
          </div>
        </div>
        <div style={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 14, padding: 24 }}>
          <h4 style={{ fontSize: 10, color: c.textDim, textTransform: "uppercase", letterSpacing: 1, fontWeight: 700, marginBottom: 16 }}>Score distribution</h4>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={scoreDist}>
              <XAxis dataKey="range" tick={{ fill: c.textMuted, fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: c.textDim, fontSize: 11 }} axisLine={false} tickLine={false} width={24} />
              <Tooltip {...tt} />
              <Bar dataKey="count" fill={c.accent} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
