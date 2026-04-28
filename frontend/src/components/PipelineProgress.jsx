// src/components/PipelineProgress.jsx
import React from "react";
import { useTheme } from "../App";
import LogConsole from "./ui/LogConsole";

const STAGES = [
  { key: "parse", label: "Parse campaign", icon: "01" },
  { key: "collect", label: "Collect leads", icon: "02" },
  { key: "qualify", label: "Qualify & score", icon: "03" },
  { key: "enrich", label: "Enrich data", icon: "04" },
  { key: "emails", label: "Generate emails", icon: "05" },
];

export { STAGES };

export default function PipelineProgress({ currentStage, logs, isRunning }) {
  const { theme } = useTheme();
  const c = theme.colors;
  const f = theme.fonts;
  const stageIdx = STAGES.findIndex((s) => s.key === currentStage);
  const allDone = !isRunning && stageIdx >= STAGES.length - 1 && logs.length > 0;

  return (
    <div style={{ background: c.surface, border: `1px solid ${c.border}`, borderRadius: 14, padding: 28 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 24 }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, color: c.text }}>Pipeline progress</h3>
        {isRunning && <span style={{ fontSize: 11, color: c.accent, fontFamily: f.mono, animation: "pulse 1.5s infinite" }}>RUNNING</span>}
        {allDone && <span style={{ fontSize: 11, color: c.green, fontFamily: f.mono }}>COMPLETE</span>}
      </div>
      <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
        {STAGES.map((stage, i) => {
          const done = i < stageIdx || allDone;
          const active = i === stageIdx && isRunning;
          return (
            <div key={stage.key} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
              <div style={{ width: "100%", height: 3, borderRadius: 2, background: done ? c.accent : active ? c.accentSoft : c.border, transition: "all .5s" }} />
              <div style={{
                width: 34, height: 34, borderRadius: 8, display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 12, fontWeight: 700, fontFamily: f.mono,
                background: done || active ? c.accentGlow : "transparent",
                border: `1px solid ${done || active ? c.accent : c.border}`,
                color: done || active ? c.accent : c.textDim, transition: "all .3s",
              }}>{stage.icon}</div>
              <div style={{ fontSize: 11, color: done || active ? c.text : c.textDim, textAlign: "center", lineHeight: 1.3 }}>{stage.label}</div>
            </div>
          );
        })}
      </div>
      <LogConsole logs={logs} />
    </div>
  );
}
