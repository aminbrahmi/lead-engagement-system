// src/api/sender.js
import client from "./client";

export const getSender = () =>
  client.get("/sender");

export const saveSender = (config) =>
  client.post("/sender", config);
