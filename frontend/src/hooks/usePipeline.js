// src/hooks/usePipeline.js
import { useState, useCallback, useRef } from "react";
import { launchCampaign } from "../api/campaigns";
import { connectPipeline } from "../api/websocket";
import { timestamp } from "../utils/format";

export default function usePipeline() {
  const [isRunning, setIsRunning] = useState(false);
  const [currentStage, setCurrentStage] = useState("");
  const [logs, setLogs] = useState([]);
  const [leads, setLeads] = useState([]);
  const [campaignId, setCampaignId] = useState(null);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);

  const addLog = useCallback((msg, level = "info", agent = null) => {
    setLogs((prev) => [...prev, { msg, level, agent, time: timestamp() }]);
  }, []);

  const launch = useCallback(
    async (prompt) => {
      // Reset state
      setIsRunning(true);
      setCurrentStage("parse");
      setLogs([]);
      setLeads([]);
      setError(null);

      addLog(`Campaign: "${prompt}"`, "info", "System");

      try {
        // POST to backend — returns { campaign_id }
        const res = await launchCampaign(prompt);
        const id = res.campaign_id;
        setCampaignId(id);

        addLog(`Campaign created: ${id}`, "success", "System");

        // Connect WebSocket for live updates
        wsRef.current = connectPipeline(id, {
          onOpen: () => {
            addLog("Connected to pipeline stream", "info", "WS");
          },
          onLog: (data) => {
            addLog(data.msg, data.level || "info", data.agent || null);
          },
          onStage: (stage) => {
            setCurrentStage(stage);
            addLog(`Stage: ${stage}`, "info", "Pipeline");
          },
          onLeads: (newLeads) => {
            setLeads(newLeads);
            addLog(`Received ${newLeads.length} leads`, "success", "Pipeline");
          },
          onComplete: (data) => {
            setIsRunning(false);
            addLog("Pipeline complete", "success", "System");
          },
          onError: (message) => {
            addLog(`Error: ${message}`, "error", "System");
            setError(message);
          },
          onClose: () => {
            setIsRunning(false);
          },
        });
      } catch (err) {
        addLog(`Launch failed: ${err.message}`, "error", "System");
        setError(err.message);
        setIsRunning(false);
      }
    },
    [addLog]
  );

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  return {
    isRunning,
    currentStage,
    logs,
    leads,
    setLeads,
    campaignId,
    error,
    launch,
    disconnect,
  };
}
