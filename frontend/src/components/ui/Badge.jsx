// src/components/ui/Badge.jsx
import React from "react";
import { useTheme } from "../../App";
import { segmentColor, segmentGlow } from "../../styles/theme";

export default function Badge({ segment }) {
  const { theme } = useTheme();
  return (
    <span style={{
      display: "inline-block", padding: "3px 10px", borderRadius: 4,
      fontSize: 10, fontWeight: 700, letterSpacing: 1,
      color: segmentColor(segment, theme),
      background: segmentGlow(segment, theme),
      textTransform: "uppercase", fontFamily: theme.fonts.mono,
    }}>{segment}</span>
  );
}
