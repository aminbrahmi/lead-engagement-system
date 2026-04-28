// src/components/CampaignForm.jsx
import React, { useState } from "react";
import { useTheme } from "../App";

const EXAMPLE_PROMPTS = [
  "Find CTOs of AI startups in Berlin that raised funding in the last 12 months",
  "CEOs of fintech companies in Paris with Series A or B funding in 2024",
  "VP Engineering at SaaS startups in London, 50-200 employees",
];

export default function CampaignForm({ onLaunch, onViewCampaign, isRunning, campaigns, campaignsLoading }) {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;
  const [prompt, setPrompt] = useState("");

  const handleSubmit = () => {
    if (prompt.trim() && !isRunning) onLaunch(prompt.trim());
  };

  // Show DB campaigns if available, otherwise show hardcoded examples
  const hasCampaigns = campaigns && campaigns.length > 0;

  return (
    <div style={{ maxWidth: 720, margin: "40px auto" }}>
      <h1 style={{ fontSize: 32, fontWeight: 700, marginBottom: 8, letterSpacing: -0.5, color: c.text }}>
        New campaign
      </h1>
      <p style={{ color: c.textMuted, fontSize: 14, marginBottom: 32, lineHeight: 1.7 }}>
        Describe your campaign in natural language. The pipeline will automatically collect,
        qualify, enrich leads and generate personalized emails.
        {hasCampaigns && " Or view results from a previous campaign below."}
      </p>

      {/* ── Input area ── */}
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g. Find CTOs of AI startups in Berlin that raised funding in the last 12 months"
          rows={4}
          style={{
            width: "100%", padding: "16px 20px", borderRadius: 12,
            background: c.surface, border: `1px solid ${c.border}`, color: c.text,
            fontFamily: f.body, fontSize: 15, lineHeight: 1.7, outline: "none", resize: "none",
          }}
          onKeyDown={(e) => { if (e.key === "Enter" && e.metaKey) handleSubmit(); }}
        />
        <button
          onClick={handleSubmit}
          disabled={isRunning || !prompt.trim()}
          style={{
            padding: "14px 32px", borderRadius: 10, border: "none",
            cursor: isRunning ? "not-allowed" : "pointer",
            background: isRunning ? c.surfaceAlt : `linear-gradient(135deg, ${c.accent}, ${c.accentSoft})`,
            color: "#fff", fontSize: 15, fontWeight: 600, fontFamily: f.body,
            opacity: !prompt.trim() || isRunning ? 0.5 : 1,
            transition: "all .2s", alignSelf: "flex-start",
          }}
        >
          {isRunning ? "Pipeline running..." : "Launch pipeline"}
        </button>
      </div>

      {/* ── Previous campaigns ── */}
      {hasCampaigns && (
        <div style={{ marginTop: 40 }}>
          <div style={{
            fontSize: 10, color: c.textDim, textTransform: "uppercase",
            letterSpacing: 1, fontWeight: 700, marginBottom: 12,
          }}>
            Previous campaigns ({campaigns.length})
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {campaigns.map((camp) => (
              <div
                key={camp.id}
                style={{
                  background: c.surface, border: `1px solid ${c.border}`, borderRadius: 10,
                  padding: "14px 18px", transition: "border-color .15s",
                }}
                onMouseEnter={(e) => (e.currentTarget.style.borderColor = c.accent)}
                onMouseLeave={(e) => (e.currentTarget.style.borderColor = c.border)}
              >
                {/* Prompt text */}
                <div style={{ fontSize: 13, color: c.text, lineHeight: 1.6, marginBottom: 10 }}>
                  {camp.prompt}
                </div>

                {/* Stats row */}
                <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 11, color: c.textDim, fontFamily: f.mono }}>
                    {camp.leads_count || 0} leads
                  </span>
                  {(camp.hot_count > 0) && (
                    <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: c.hotGlow, color: c.hot, fontFamily: f.mono, fontWeight: 600 }}>
                      {camp.hot_count} hot
                    </span>
                  )}
                  {(camp.warm_count > 0) && (
                    <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: c.warmGlow, color: c.warm, fontFamily: f.mono, fontWeight: 600 }}>
                      {camp.warm_count} warm
                    </span>
                  )}
                  {(camp.emails_count > 0) && (
                    <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, background: c.greenGlow, color: c.green, fontFamily: f.mono, fontWeight: 600 }}>
                      {camp.emails_count} emails
                    </span>
                  )}
                  <span style={{ fontSize: 11, color: c.textDim }}>
                    {camp.updated_at
                      ? new Date(camp.updated_at).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" })
                      : camp.created_at
                        ? new Date(camp.created_at).toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" })
                        : ""}
                  </span>

                  {/* Action buttons — pushed right */}
                  <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                    <button
                      onClick={() => onViewCampaign(camp)}
                      style={{
                        padding: "5px 12px", borderRadius: 6,
                        border: `1px solid ${c.accent}`, background: c.accentGlow,
                        color: c.accent, fontSize: 12, fontWeight: 600,
                        cursor: "pointer", fontFamily: f.body,
                      }}
                    >
                      View results
                    </button>
                    <button
                      onClick={() => setPrompt(camp.prompt)}
                      style={{
                        padding: "5px 12px", borderRadius: 6,
                        border: `1px solid ${c.border}`, background: "transparent",
                        color: c.textMuted, fontSize: 12, fontWeight: 500,
                        cursor: "pointer", fontFamily: f.body,
                      }}
                    >
                      Use prompt
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Examples (only if no campaigns yet) ── */}
      {!hasCampaigns && (
        <div style={{ marginTop: 40 }}>
          <div style={{
            fontSize: 10, color: c.textDim, textTransform: "uppercase",
            letterSpacing: 1, fontWeight: 700, marginBottom: 12,
          }}>
            Examples
          </div>
          {EXAMPLE_PROMPTS.map((ex, i) => (
            <button
              key={i}
              onClick={() => setPrompt(ex)}
              style={{
                display: "block", width: "100%", textAlign: "left",
                padding: "12px 16px", marginBottom: 8, borderRadius: 8,
                background: "transparent", border: `1px solid ${c.border}`,
                color: c.textMuted, fontSize: 13, cursor: "pointer",
                fontFamily: f.body, transition: "all .15s",
              }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = c.accent; e.currentTarget.style.color = c.text; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = c.border; e.currentTarget.style.color = c.textMuted; }}
            >
              {ex}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
