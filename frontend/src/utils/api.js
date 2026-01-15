// frontend/src/utils/api.js
import axios from "axios";

/**
 * DEV FIX (Vite proxy):
 * - When running via Vite (localhost:5173), use SAME-ORIGIN requests.
 *   This ensures /api is proxied to http://127.0.0.1:8000 by vite.config.js
 *   and avoids CORS entirely.
 *
 * PROD:
 * - If VITE_BACKEND_URL is set (e.g., https://api.myapp.com), we use it.
 */
function resolveBaseURL() {
  const env = (import.meta.env.VITE_BACKEND_URL || "").trim();

  // If user explicitly set an absolute URL (prod/staging), use it
  if (env.startsWith("http://") || env.startsWith("https://")) {
    return env.replace(/\/+$/, "");
  }

  // Otherwise, for local dev, use same origin ("" makes axios use window.location.origin)
  // This makes calls go to http://localhost:5173/api/... which Vite proxies to backend.
  return "";
}

const api = axios.create({
  baseURL: resolveBaseURL(),
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

/**
 * NOTE:
 * Keep endpoints as "/api/..." so dev proxy works.
 * If baseURL is absolute (prod), it will become "https://your-backend/api/..."
 */

export const leadsAPI = {
  getAll: (params = {}) => api.get("/api/leads/", { params }),
  getById: (id) => api.get(`/api/leads/${id}`),

  // ✅ MUST exist or you'll get "createManual is not a function"
  createManual: (payload) => api.post("/api/leads/manual", payload),

  getDataPacket: (leadId) => api.get(`/api/leads/${leadId}/data-packet`),
  generateDataPackets: () => api.post("/api/leads/generate-data-packets"),
};

export const manualCallAPI = {
  initiate: (payload) => api.post("/api/manual-call/initiate", payload),
};

export const callsAPI = {
  getById: (callId) => api.get(`/api/calls/${callId}`),
  getTranscript: (callId) => api.get(`/api/calls/${callId}/transcript`),
};

export const emailsAPI = {
  // Get emails for a lead
  getByLeadId: (leadId) => api.get(`/api/emails/lead/${leadId}`),

  // Get single email by ID
  getById: (emailId) => api.get(`/api/emails/${emailId}`),

  // Update email (subject, body, etc.)
  update: (emailId, data) => api.put(`/api/emails/${emailId}`, data),

  // Send a draft email
  send: (emailId) => api.post(`/api/emails/${emailId}/send`),

  // Delete an email
  delete: (emailId) => api.delete(`/api/emails/${emailId}`),

  // Get email analytics summary
  getAnalytics: (params = {}) => api.get("/api/emails/analytics/summary", { params }),

  // Get throttle status
  getThrottleStatus: () => api.get("/api/emails/throttle/status"),

  // Schedule follow-up emails
  scheduleFollowups: (callId) => api.post(`/api/emails/schedule/${callId}`),

  // Cancel scheduled emails for a lead
  cancelScheduled: (leadId, reason = "cancelled") =>
    api.post(`/api/emails/cancel/${leadId}?reason=${encodeURIComponent(reason)}`),
};

export const emailIntelligenceAPI = {
  // Get comprehensive intelligence for a lead
  getLeadIntelligence: (leadId) => api.get(`/api/email-intelligence/lead/${leadId}`),

  // Refresh engagement score for a lead
  refreshEngagement: (leadId) => api.post(`/api/email-intelligence/lead/${leadId}/refresh-engagement`),

  // Get optimal send time for a lead
  getOptimalSendTime: (leadId, preferWithinHours = 48) =>
    api.get(`/api/email-intelligence/lead/${leadId}/optimal-send-time?prefer_within_hours=${preferWithinHours}`),

  // Get next recommended action for a lead
  getNextAction: (leadId, callId = null) =>
    api.get(`/api/email-intelligence/lead/${leadId}/next-action${callId ? `?call_id=${callId}` : ""}`),

  // Analyze a reply
  analyzeReply: (replyText, emailId = null, leadId = null) =>
    api.post("/api/email-intelligence/analyze-reply", {
      reply_text: replyText,
      email_id: emailId,
      lead_id: leadId,
    }),

  // Generate subject line variants
  generateSubjects: (originalSubject, emailType, leadId, numVariants = 3) =>
    api.post("/api/email-intelligence/generate-subjects", {
      original_subject: originalSubject,
      email_type: emailType,
      lead_id: leadId,
      num_variants: numVariants,
    }),

  // Analyze email content quality
  analyzeContent: (subject, bodyHtml, emailType = "follow_up") =>
    api.post("/api/email-intelligence/analyze-content", {
      subject,
      body_html: bodyHtml,
      email_type: emailType,
    }),

  // Get deliverability health
  getHealth: () => api.get("/api/email-intelligence/health"),

  // Get engagement summary across all leads
  getEngagementSummary: () => api.get("/api/email-intelligence/engagement-summary"),

  // Refresh all engagement scores
  refreshAllEngagement: (limit = 100) =>
    api.post(`/api/email-intelligence/refresh-all-engagement?limit=${limit}`),

  // A/B Testing
  createABTest: (data) => api.post("/api/email-intelligence/ab-test", data),
  getABTest: (testId) => api.get(`/api/email-intelligence/ab-test/${testId}`),
  listABTests: (status = null, emailType = null) => {
    const params = new URLSearchParams();
    if (status) params.append("status", status);
    if (emailType) params.append("email_type", emailType);
    return api.get(`/api/email-intelligence/ab-tests?${params.toString()}`);
  },
  recordABTestEvent: (testId, variantId, event) =>
    api.post(`/api/email-intelligence/ab-test/${testId}/record?variant_id=${variantId}&event=${event}`),

  // Get scheduler status
  getSchedulerStatus: () => api.get("/api/emails/scheduler/status"),

  // Get warmup status
  getWarmupStatus: () => api.get("/api/email-intelligence/warmup-status"),
};

export default api;
