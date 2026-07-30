// src/pages/AnalyticsPage.jsx — Agent Analyst dashboard
import React, { useState, useEffect, useCallback } from "react";
import { authFetch } from "../api/authFetch";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend,
} from "recharts";
import { useTheme } from "../App";
import StatCard from "../components/ui/StatCard";
import {
  getCampaignReport, getWeeklyReport, campaignPdfUrl, weeklyPdfUrl,
} from "../api/analytics";

export default function AnalyticsPage({ leads, campaigns = [], activeCampaign }) {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;

  const [mode, setMode] = useState("campaign");      // "campaign" | "weekly"
  const [campaignId, setCampaignId] = useState(activeCampaign?.id || campaigns[0]?.id || null);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [recsLoading, setRecsLoading] = useState(false);
  const [error, setError] = useState(null);

  const tt = { contentStyle: { background: c.surface, border: `1px solid ${c.border}`, borderRadius: 8, fontSize: 12, color: c.text } };

  // Pick a default campaign when the list arrives
  useEffect(() => {
    if (mode === "campaign" && !campaignId && campaigns.length) {
      setCampaignId(activeCampaign?.id || campaigns[0].id);
    }
  }, [campaigns, activeCampaign, mode, campaignId]);

  // Two-phase load: fast metrics first, then LLM recommendations
  const load = useCallback(async () => {
    setError(null);
    setReport(null);
    setLoading(true);
    try {
      const fast = mode === "weekly"
        ? await getWeeklyReport(false)
        : await getCampaignReport(campaignId, false);
      setReport(fast);
      setLoading(false);

      setRecsLoading(true);
      const full = mode === "weekly"
        ? await getWeeklyReport(true)
        : await getCampaignReport(campaignId, true);
      setReport(full);
    } catch (e) {
      setError("Could not load report. Make sure the backend is running.");
      setLoading(false);
    } finally {
      setRecsLoading(false);
    }
  }, [mode, campaignId]);

  useEffect(() => {
    if (mode === "weekly" || campaignId) load();
  }, [load]);

  const pdfHref = mode === "weekly" ? weeklyPdfUrl() : (campaignId ? campaignPdfUrl(campaignId) : "#");

  // Authenticated PDF download: a plain <a href> can't send the JWT, so fetch the
  // file as a blob (with the token) and trigger the download from memory.
  const downloadPdf = async () => {
    if (pdfHref === "#") return;
    try {
      const res = await authFetch(pdfHref);
      if (!res.ok) return;
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = mode === "weekly" ? "weekly-report.pdf" : "campaign-report.pdf";
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };

  // ── Empty state ──
  if (!campaigns.length && mode === "campaign") {
    return (
      <div style={{ textAlign: "center", padding: 80, color: c.textDim }}>
        <p style={{ fontSize: 40, marginBottom: 16 }}>&#128202;</p>
        <p>Launch a campaign to see analytics</p>
      </div>
    );
  }

  const leadsM = report?.leads;
  const emailsM = report?.emails;
  const totals = report?.totals;

  // Segment data (campaign or weekly totals)
  const seg = mode === "weekly"
    ? { hot: totals?.hot || 0, warm: totals?.warm || 0, cold: totals?.cold || 0 }
    : { hot: leadsM?.hot || 0, warm: leadsM?.warm || 0, cold: leadsM?.cold || 0 };
  const pieData = [
    { name: "Hot", value: seg.hot, color: c.hot },
    { name: "Warm", value: seg.warm, color: c.warm },
    { name: "Cold", value: seg.cold, color: c.cold },
  ].filter((d) => d.value > 0);

  const rates = mode === "weekly" ? totals : emailsM;
  const engageData = rates ? [
    { name: "Click", value: rates.click_rate || 0 },
    { name: "Reply", value: rates.reply_rate || 0 },
    { name: "Bounce", value: rates.bounce_rate || 0 },
  ] : [];

  // A/B variant data (campaign mode only)
  const variants = report?.variants || {};
  const variantKeys = Object.keys(variants).sort();
  const variantChart = variantKeys.length ? [
    { metric: "Click %", ...Object.fromEntries(variantKeys.map((k) => [k, variants[k].click_rate])) },
    { metric: "Reply %", ...Object.fromEntries(variantKeys.map((k) => [k, variants[k].reply_rate])) },
  ] : [];
  const variantColors = [c.accent, c.hot, c.warm, c.cold];

  const card = { background: c.surface, border: `1px solid ${c.border}`, borderRadius: 14, padding: 24 };
  const h4 = { fontSize: 10, color: c.textDim, textTransform: "uppercase", letterSpacing: 1, fontWeight: 700, marginBottom: 16 };

  // Only render the body once the loaded report matches the current mode
  // (prevents shape mismatches while switching campaign ↔ weekly).
  const reportReady = report && (mode === "weekly" ? report.totals : report.leads);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* ── Toolbar ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          {/* Mode toggle */}
          <div style={{ display: "flex", gap: 4 }}>
            {["campaign", "weekly"].map((m) => (
              <button key={m} onClick={() => setMode(m)} style={{
                padding: "6px 14px", borderRadius: 6,
                border: `1px solid ${mode === m ? c.accent : c.border}`,
                background: mode === m ? c.accentGlow : "transparent",
                color: mode === m ? c.accent : c.textMuted,
                fontSize: 12, cursor: "pointer", fontFamily: f.body,
                textTransform: "capitalize", fontWeight: mode === m ? 600 : 400,
              }}>{m === "weekly" ? "Weekly (all)" : "By campaign"}</button>
            ))}
          </div>

          {/* Campaign selector */}
          {mode === "campaign" && (
            <select
              value={campaignId || ""}
              onChange={(e) => setCampaignId(e.target.value)}
              style={{
                padding: "7px 12px", borderRadius: 6, border: `1px solid ${c.border}`,
                background: c.surface, color: c.text, fontSize: 13, fontFamily: f.body,
                cursor: "pointer", maxWidth: 360,
              }}
            >
              {campaigns.map((camp) => (
                <option key={camp.id} value={camp.id}>
                  {(camp.prompt || camp.id).slice(0, 60)}
                </option>
              ))}
            </select>
          )}
        </div>

        <button
          onClick={downloadPdf}
          style={{
            padding: "8px 16px", borderRadius: 8, border: "none",
            background: c.accent, color: "#fff", fontSize: 13, fontWeight: 600,
            cursor: "pointer", fontFamily: f.body, textDecoration: "none",
            display: "inline-flex", alignItems: "center", gap: 6,
          }}
        >
          &#11015; Download PDF report
        </button>
      </div>

      {error && (
        <div style={{ ...card, color: c.hot, borderColor: `${c.hot}44` }}>{error}</div>
      )}

      {loading && !reportReady && (
        <div style={{ ...card, textAlign: "center", color: c.textDim }}>Loading analytics…</div>
      )}

      {reportReady && (
        <>
          {/* ── Summary banner ── */}
          {(report.summary || recsLoading) && (
            <div style={{ ...card, borderLeft: `3px solid ${c.accent}` }}>
              <div style={h4}>Executive summary</div>
              {report.summary
                ? <div style={{ fontSize: 14, color: c.text, lineHeight: 1.6 }}>{report.summary}</div>
                : <div style={{ fontSize: 13, color: c.textDim }}>Generating insights…</div>}
            </div>
          )}

          {/* ── Stat cards ── */}
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            {mode === "weekly" ? (
              <>
                <StatCard label="Campaigns" value={report.campaigns?.length || 0} />
                <StatCard label="Total leads" value={totals?.leads || 0} />
                <StatCard label="Emails sent" value={totals?.sent || 0} color={c.accent} />
                <StatCard label="Reply rate" value={`${totals?.reply_rate || 0}%`} color={c.green} />
                <StatCard label="Meetings" value={totals?.meetings || 0} color={c.green} />
              </>
            ) : (
              <>
                <StatCard label="Total leads" value={leadsM?.total || 0} />
                <StatCard label="Avg score" value={leadsM?.avg_score || 0} color={(leadsM?.avg_score || 0) >= 60 ? c.green : c.warm} />
                <StatCard label="Emails sent" value={emailsM?.sent || 0} color={c.accent} />
                <StatCard label="Click rate" value={`${emailsM?.click_rate || 0}%`} />
                <StatCard label="Reply rate" value={`${emailsM?.reply_rate || 0}%`} color={c.green} />
                <StatCard label="Verified emails" value={`${leadsM?.verified_pct || 0}%`} sub={`${leadsM?.verified || 0}/${leadsM?.with_email || 0}`} color={c.green} />
              </>
            )}
          </div>

          {/* ── Charts row ── */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20 }}>
            <div style={card}>
              <div style={h4}>Segment distribution</div>
              {pieData.length ? (
                <>
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie data={pieData} dataKey="value" cx="50%" cy="50%" innerRadius={45} outerRadius={78} paddingAngle={4} strokeWidth={0}>
                        {pieData.map((d, i) => <Cell key={i} fill={d.color} />)}
                      </Pie>
                      <Tooltip {...tt} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div style={{ display: "flex", justifyContent: "center", gap: 20, fontSize: 12, marginTop: 4 }}>
                    {pieData.map((d) => <span key={d.name} style={{ color: d.color, fontWeight: 500 }}>{d.name}: {d.value}</span>)}
                  </div>
                </>
              ) : <div style={{ color: c.textDim, fontSize: 13, padding: 30, textAlign: "center" }}>No leads</div>}
            </div>

            <div style={card}>
              <div style={h4}>Engagement rates (%)</div>
              <ResponsiveContainer width="100%" height={230}>
                <BarChart data={engageData}>
                  <XAxis dataKey="name" tick={{ fill: c.textMuted, fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: c.textDim, fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
                  <Tooltip {...tt} />
                  <Bar dataKey="value" fill={c.accent} radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* ── Deliverability strip ── */}
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <StatCard label="Clicked" value={(rates?.clicked) ?? 0} sub={mode === "campaign" ? `${emailsM?.total_clicks || 0} total clicks` : undefined} />
            <StatCard label="Replied" value={(rates?.replied) ?? 0} color={c.green} />
            <StatCard label="Bounced" value={(rates?.bounced) ?? 0} color={c.hot} />
            {mode === "campaign" && <StatCard label="Unsubscribed" value={emailsM?.unsubscribed || 0} color={c.warm} />}
          </div>

          {/* ── A/B variant comparison (campaign mode) ── */}
          {mode === "campaign" && variantKeys.length > 0 && (
            <div style={card}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                <span style={h4}>A/B variant performance</span>
                {report.best_variant && (
                  <span style={{ fontSize: 12, color: c.green, fontWeight: 600 }}>
                    Best: Variant {report.best_variant} &#9733;
                  </span>
                )}
              </div>

              {/* Variant table */}
              <div style={{ overflowX: "auto", marginBottom: 20 }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${c.border}` }}>
                      {["Variant", "Sent", "Clicked", "Replied", "Click %", "Reply %"].map((hh) => (
                        <th key={hh} style={{ padding: "8px 12px", textAlign: "left", fontSize: 10, color: c.textDim, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1 }}>{hh}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {variantKeys.map((k) => {
                      const v = variants[k];
                      const best = report.best_variant === k;
                      return (
                        <tr key={k} style={{ borderBottom: `1px solid ${c.border}`, background: best ? c.greenGlow : "transparent" }}>
                          <td style={{ padding: "10px 12px", fontWeight: 700, color: best ? c.green : c.text }}>
                            {k} {best && "★"}
                          </td>
                          <td style={{ padding: "10px 12px", color: c.textMuted, fontFamily: f.mono }}>{v.sent}</td>
                          <td style={{ padding: "10px 12px", color: c.textMuted, fontFamily: f.mono }}>{v.clicked}</td>
                          <td style={{ padding: "10px 12px", color: c.textMuted, fontFamily: f.mono }}>{v.replied}</td>
                          <td style={{ padding: "10px 12px", color: c.text, fontFamily: f.mono }}>{v.click_rate}%</td>
                          <td style={{ padding: "10px 12px", color: c.text, fontFamily: f.mono, fontWeight: 600 }}>{v.reply_rate}%</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              {/* Variant grouped bars */}
              {variantKeys.length >= 2 && (
                <ResponsiveContainer width="100%" height={240}>
                  <BarChart data={variantChart}>
                    <XAxis dataKey="metric" tick={{ fill: c.textMuted, fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: c.textDim, fontSize: 11 }} axisLine={false} tickLine={false} width={28} />
                    <Tooltip {...tt} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    {variantKeys.map((k, i) => (
                      <Bar key={k} dataKey={k} name={`Variant ${k}`} fill={variantColors[i % variantColors.length]} radius={[4, 4, 0, 0]} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          )}

          {/* ── Per-campaign breakdown (weekly mode) ── */}
          {mode === "weekly" && report.campaigns?.length > 0 && (
            <div style={card}>
              <div style={h4}>Per-campaign breakdown</div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${c.border}` }}>
                      {["Campaign", "Leads", "Sent", "Click %", "Reply %", "Best"].map((hh) => (
                        <th key={hh} style={{ padding: "8px 12px", textAlign: "left", fontSize: 10, color: c.textDim, fontWeight: 700, textTransform: "uppercase", letterSpacing: 1 }}>{hh}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {report.campaigns.map((cc) => {
                      const m = cc.metrics;
                      return (
                        <tr key={cc.id} style={{ borderBottom: `1px solid ${c.border}` }}>
                          <td style={{ padding: "10px 12px", color: c.text }}>{(cc.prompt || cc.id).slice(0, 45)}</td>
                          <td style={{ padding: "10px 12px", color: c.textMuted, fontFamily: f.mono }}>{m.leads.total}</td>
                          <td style={{ padding: "10px 12px", color: c.textMuted, fontFamily: f.mono }}>{m.emails.sent}</td>
                          <td style={{ padding: "10px 12px", color: c.text, fontFamily: f.mono }}>{m.emails.click_rate}%</td>
                          <td style={{ padding: "10px 12px", color: c.text, fontFamily: f.mono, fontWeight: 600 }}>{m.emails.reply_rate}%</td>
                          <td style={{ padding: "10px 12px", color: c.green, fontWeight: 600 }}>{m.best_variant || "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── Recommendations ── */}
          <div style={card}>
            <div style={h4}>Optimization recommendations</div>
            {recsLoading && !report.recommendations?.length ? (
              <div style={{ fontSize: 13, color: c.textDim }}>Analyzing data and generating recommendations…</div>
            ) : report.recommendations?.length ? (
              <ol style={{ margin: 0, paddingLeft: 20, display: "flex", flexDirection: "column", gap: 10 }}>
                {report.recommendations.map((r, i) => (
                  <li key={i} style={{ fontSize: 13, color: c.text, lineHeight: 1.6 }}>{r}</li>
                ))}
              </ol>
            ) : (
              <div style={{ fontSize: 13, color: c.textDim }}>No recommendations available.</div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
