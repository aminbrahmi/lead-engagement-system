// src/api/websocket.js

const WS_URL = process.env.REACT_APP_WS_URL || "ws://localhost:8000/ws";

/**
 * Connect to the pipeline WebSocket.
 * Returns { send, close } — call close() on unmount.
 *
 * Events emitted by backend:
 *   { type: "log",       data: { msg, level, agent } }
 *   { type: "stage",     data: { stage } }
 *   { type: "leads",     data: { leads: [...] } }
 *   { type: "complete",  data: { campaign_id } }
 *   { type: "error",     data: { message } }
 */
export function connectPipeline(campaignId, handlers) {
  const ws = new WebSocket(`${WS_URL}/pipeline/${campaignId}`);

  ws.onopen = () => {
    handlers.onOpen?.();
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case "log":
          handlers.onLog?.(msg.data);
          break;
        case "stage":
          handlers.onStage?.(msg.data.stage);
          break;
        case "leads":
          handlers.onLeads?.(msg.data.leads);
          break;
        case "complete":
          handlers.onComplete?.(msg.data);
          break;
        case "error":
          handlers.onError?.(msg.data.message);
          break;
        default:
          break;
      }
    } catch (err) {
      console.error("[WS] Parse error:", err);
    }
  };

  ws.onerror = (err) => {
    console.error("[WS] Error:", err);
    handlers.onError?.("WebSocket connection error");
  };

  ws.onclose = () => {
    handlers.onClose?.();
  };

  return {
    send: (data) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(data)),
    close: () => ws.close(),
  };
}
