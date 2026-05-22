import client from "./client";

export const getDiscussions = (campaignId = null) =>
  client.get("/discussions", { params: campaignId ? { campaign_id: campaignId } : {} });

export const getThread = (discussionId) =>
  client.get(`/discussions/${discussionId}/messages`);

export const getLeadDiscussion = (leadId) =>
  client.get(`/leads/${leadId}/discussion`);

export const runTracker = (campaignId = null) =>
  client.post("/tracker/run", {}, { params: campaignId ? { campaign_id: campaignId } : {} });

export const sendDiscussionReply = (discussionId, replyData) =>
  client.post(`/discussions/${discussionId}/reply`, replyData);

export const generateDiscussionReply = (discussionId) =>
  client.post(`/discussions/${discussionId}/generate-reply`);
