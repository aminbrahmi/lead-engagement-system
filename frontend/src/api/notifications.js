// frontend/src/api/notifications.js
import client from "./client";

export const getNotifications = (unreadOnly = true) =>
  client.get("/notifications", { params: { unread_only: unreadOnly } });

export const markRead = (id) =>
  client.post(`/notifications/${id}/read`);

export const markAllRead = () =>
  client.post("/notifications/read-all");
