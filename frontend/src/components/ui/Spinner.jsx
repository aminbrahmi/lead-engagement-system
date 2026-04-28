// src/components/ui/Spinner.jsx
import React from "react";
import { useTheme } from "../../App";

export default function Spinner({ size = 18, color }) {
  const { theme } = useTheme();
  const c = theme.colors;
  return (
    <span
      style={{
        display: "inline-block",
        width: size,
        height: size,
        border: `2px solid ${c.border}`,
        borderTopColor: color || c.accent,
        borderRadius: "50%",
        animation: "spin 0.6s linear infinite",
      }}
    />
  );
}
