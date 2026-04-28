// src/pages/PipelinePage.jsx
import React from "react";
import PipelineProgress from "../components/PipelineProgress";
import { useTheme } from "../App";

export default function PipelinePage({ currentStage, logs, isRunning }) {
  const { theme } = useTheme();
  const c = theme.colors;

  if (logs.length === 0) {
    return (
      <div style={{ textAlign: "center", padding: 80, color: c.textDim }}>
        <p style={{ fontSize: 40, marginBottom: 16 }}>&#9881;</p>
        <p>Launch a campaign to see the pipeline in action</p>
      </div>
    );
  }

  return <PipelineProgress currentStage={currentStage} logs={logs} isRunning={isRunning} />;
}
