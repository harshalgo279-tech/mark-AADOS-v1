// frontend/src/utils/api.js
import axios from "axios";

const BACKEND_BASE_URL =
  import.meta.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

const api = axios.create({
  baseURL: BACKEND_BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 30000,
});

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

export default api;
