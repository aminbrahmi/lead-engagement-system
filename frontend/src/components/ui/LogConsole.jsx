// src/components/ui/LogConsole.jsx
import React, { useEffect, useRef } from "react";
import { useTheme } from "../../App";

export default function LogConsole({ logs }) {
  const { theme } = useTheme();
  const c = theme.colors;
  const endRef = useRef(null);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs.length]);

  const levelColor = { success: c.green, warn: c.warm, error: c.hot, info: c.textMuted };

  return (
    <div style={{
      background: c.bg, border: `1px solid ${c.border}`, borderRadius: 8,
      padding: 16, maxHeight: 200, overflowY: "auto",
      fontFamily: theme.fonts.mono, fontSize: 12, lineHeight: 1.8,
    }}>
      {logs.length === 0 && <span style={{ color: c.textDim }}>Waiting for pipeline...</span>}
      {logs.map((log, i) => (
        <div key={i} style={{ color: levelColor[log.level] || c.textMuted }}>
          <span style={{ color: c.textDim, marginRight: 8 }}>{log.time}</span>
          {log.agent && <span style={{ color: c.accent, marginRight: 6 }}>[{log.agent}]</span>}
          {log.msg}
        </div>
      ))}
      <div ref={endRef} />
    </div>
  );
}
