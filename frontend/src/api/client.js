const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let detail = null;
    try {
      detail = (await res.json()).detail;
    } catch {
      /* response wasn't JSON */
    }
    throw new ApiError(detail || `Request failed (${res.status})`, res.status, detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  // ── system ──
  health: () => request("/health"),

  // ── events ──
  simulateEvent: (payload) =>
    request("/events/simulate", { method: "POST", body: JSON.stringify(payload) }),
  loadHistorical: (limit) =>
    request(`/events/load-historical${limit ? `?limit=${limit}` : ""}`, { method: "POST" }),
  activeEvents: (limit = 300) => request(`/events/active?limit=${limit}`),
  replayStream: (offset = 0, limit = 100) =>
    request(`/events/replay/stream?offset=${offset}&limit=${limit}`),
  getEvent: (eventId) => request(`/events/${eventId}`),
  getResponseCard: (eventId) => request(`/events/${eventId}/response-card`),
  submitFeedback: (payload) =>
    request("/events/feedback", { method: "POST", body: JSON.stringify(payload) }),

  // ── predict ──
  predictUnscored: (payload) =>
    request("/predict/event", { method: "POST", body: JSON.stringify(payload) }),

  // ── recommend ──
  recommendManpower: (payload) =>
    request("/recommend/manpower", { method: "POST", body: JSON.stringify(payload) }),
  recommendBarricade: (payload) =>
    request("/recommend/barricade", { method: "POST", body: JSON.stringify(payload) }),
  recommendDiversion: (payload) =>
    request("/recommend/diversion", { method: "POST", body: JSON.stringify(payload) }),
  stationAllocation: (payload) =>
    request("/recommend/station-allocation", { method: "POST", body: JSON.stringify(payload) }),

  // ── insights ──
  insightsSummary: () => request("/insights/summary"),
  insightsHourlyPattern: () => request("/insights/hourly-pattern"),
  insightsCauseStats: () => request("/insights/cause-stats"),
  insightsCorridorStats: (topN = 15) => request(`/insights/corridor-stats?top_n=${topN}`),
  insightsSeverityVsPriority: () => request("/insights/severity-vs-priority"),
  insightsModelMetrics: () => request("/insights/model-metrics"),
};

export { ApiError, BASE_URL };
