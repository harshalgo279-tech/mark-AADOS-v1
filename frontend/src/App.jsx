// frontend/src/App.jsx
import { useEffect, useMemo, useState } from "react";
import { Users, FileText, Phone, Mail, LogOut } from "lucide-react";

import ManualCallForm from "./components/ManualCallForm";
import DatabaseViewer from "./components/DatabaseViewer";
import TranscriptPage from "./components/TranscriptPage";
import CallMonitor from "./components/CallMonitor";
import LoginPage from "./components/LoginPage";

import WebSocketManager from "./utils/websocket";
import api from "./utils/api";

function getWsUrl() {
  // First check for explicit WS URL
  const env = (import.meta?.env?.VITE_WS_URL || "").trim();
  if (env.startsWith("ws://") || env.startsWith("wss://")) return env;

  // Derive from backend URL if available
  const backendUrl = (import.meta?.env?.VITE_BACKEND_URL || "").trim();
  if (backendUrl) {
    const url = new URL(backendUrl);
    const wsProto = url.protocol === "https:" ? "wss:" : "ws:";
    return `${wsProto}//${url.host}/api/ws`;
  }

  // Fallback to same host (for local dev)
  const wsProto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${wsProto}//${window.location.host}/api/ws`;
}

const App = () => {
  // Check if on transcript page (public route) - this is constant per page load
  const isTranscript = useMemo(
    () => window.location.pathname.startsWith("/transcript"),
    []
  );

  // ALL HOOKS MUST BE DECLARED BEFORE ANY CONDITIONAL RETURNS
  // Authentication state (use same key as api.js)
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    return !!sessionStorage.getItem("aados_access_token");
  });

  const WS_URL = useMemo(() => getWsUrl(), []);

  const [view, setView] = useState("dashboard");
  const [loading, setLoading] = useState(false);

  const [stats, setStats] = useState({
    total_leads: 0,
    data_packets: 0,
    calls_made: 0,
    emails_sent: 0,
  });

  const [leads, setLeads] = useState([]);
  const [activities, setActivities] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);

  // CALL MONITOR STATE
  const [monitorOpen, setMonitorOpen] = useState(false);
  const [monitorCallId, setMonitorCallId] = useState(null);
  const [monitorStatus, setMonitorStatus] = useState("");
  const [monitorLines, setMonitorLines] = useState([]);

  // Handle logout (use same key as api.js)
  const handleLogout = () => {
    sessionStorage.removeItem("aados_access_token");
    setIsAuthenticated(false);
    setView("dashboard");
  };

  // Handle successful login
  const handleLoginSuccess = () => {
    setIsAuthenticated(true);
  };

  const addActivity = (type, message) => {
    setActivities((prev) => [
      {
        id: Date.now() + Math.random(),
        type,
        message,
        timestamp: new Date().toISOString(),
      },
      ...prev.slice(0, 20),
    ]);
  };

  const normalizeDelta = (delta) => {
    const s = String(delta || "").trim();
    if (!s) return null;

    const normalized = s
      .replace(/\s+(AGENT:)/g, "\n$1")
      .replace(/\s+(LEAD:)/g, "\n$1");

    return normalized.split("\n").map((x) => x.trim()).filter(Boolean);
  };

  const fetchStats = async () => {
    try {
      const res = await api.get("/api/reports/dashboard");
      const d = res.data || {};

      setStats({
        total_leads: d.leads?.total ?? 0,
        data_packets: d.leads?.data_packets_created ?? 0,
        calls_made: d.calls?.total ?? 0,
        emails_sent: d.emails?.sent ?? d.emails?.total ?? 0,
      });
    } catch (error) {
      console.error("Stats fetch issue:", error);
    }
  };

  const fetchLeads = async () => {
    try {
      const res = await api.get("/api/leads/");
      setLeads(Array.isArray(res.data) ? res.data : []);
    } catch {
      // Silently handle - user not authenticated yet
    }
  };

  const handleFetchLeads = async () => {
    setLoading(true);
    try {
      addActivity("system", "Starting Apollo lead fetch...");
      const res = await api.post("/api/leads/fetch?count=20");

      if (res.data?.status === "success") {
        addActivity(
          "success",
          `Fetched ${res.data.count ?? 0} leads from Apollo`
        );
        await fetchLeads();
        await fetchStats();
      } else {
        addActivity("warning", "Apollo fetch returned unexpected response");
      }
    } catch {
      addActivity("warning", "Could not fetch leads");
    } finally {
      setLoading(false);
    }
  };

  // Listen for auth:logout event from API interceptor
  useEffect(() => {
    const handleAuthLogout = () => {
      setIsAuthenticated(false);
    };
    window.addEventListener("auth:logout", handleAuthLogout);
    return () => window.removeEventListener("auth:logout", handleAuthLogout);
  }, []);

  // WebSocket lifecycle - only run when authenticated
  useEffect(() => {
    if (!isAuthenticated) return;

    const ws = new WebSocketManager(WS_URL);

    ws.on("connected", () => {
      setWsConnected(true);
      addActivity("system", "System connected");
    });

    ws.on("disconnected", () => {
      setWsConnected(false);
      addActivity("warning", "WebSocket disconnected");
    });

    ws.on("error", () => addActivity("warning", "WebSocket issue"));

    const pingTimer = setInterval(() => ws.send({ type: "ping" }), 20000);

    ws.on("call_initiated", (data) => {
      const callId = data?.call_id;
      const company = data?.company || "";
      const phone = data?.message || "";

      if (callId) {
        setMonitorCallId(callId);
        setMonitorStatus("queued");
        setMonitorLines([]);
        setMonitorOpen(true);

        sessionStorage.setItem("aados_last_call_id", String(callId));
        addActivity(
          "success",
          `Call initiated (call_id=${callId})${company ? ` for ${company}` : ""}${phone ? ` — ${phone}` : ""}`
        );
      } else {
        addActivity("warning", "Call initiated event missing call_id");
      }
    });

    ws.on("call_in_progress", (data) => {
      if (data?.call_id) {
        setMonitorCallId(data.call_id);
        setMonitorStatus("in-progress");
        setMonitorOpen(true);
        addActivity("system", `Call in progress (call_id=${data.call_id})`);
      }
    });

    ws.on("call_status", (data) => {
      if (!data?.call_id) return;

      const status = String(data.status || "").toLowerCase();
      setMonitorCallId(data.call_id);
      setMonitorStatus(status);

      addActivity("system", `Call status: ${status} (call_id=${data.call_id})`);

      if (
        status === "completed" ||
        status === "failed" ||
        status === "canceled" ||
        status === "busy" ||
        status === "no-answer"
      ) {
        setTimeout(() => {
          setMonitorOpen(false);
        }, 2500);

        fetchStats();
      }
    });

    ws.on("call_transcript_update", (data) => {
      if (!data?.delta) return;

      const parts = normalizeDelta(data.delta);
      if (!parts?.length) return;

      setMonitorOpen(true);
      if (data?.call_id) setMonitorCallId(data.call_id);

      setMonitorLines((prev) => {
        const next = [...prev, ...parts];
        return next.slice(-250);
      });

      addActivity("system", parts.join(" | "));
    });

    ws.on("data_packet_generated", (data) => {
      addActivity(
        "success",
        `Data packet generated (lead_id=${data?.lead_id ?? "?"})`
      );
      fetchStats();
    });

    ws.on("linkedin_messages_generated", (data) => {
      addActivity(
        "success",
        `LinkedIn messages generated (call_id=${data?.call_id ?? "?"})`
      );
    });

    ws.on("emails_created", (data) => {
      addActivity(
        "success",
        `Email drafts created (${data?.count ?? 0}) for call_id=${data?.call_id ?? "?"}`
      );
      fetchStats();
    });

    ws.connect();

    return () => {
      clearInterval(pingTimer);
      ws.disconnect();
    };
  }, [isAuthenticated, WS_URL]);

  // Fetch initial data when authenticated
  useEffect(() => {
    if (!isAuthenticated) return;
    fetchStats();
    fetchLeads();
  }, [isAuthenticated]);

  // Periodic stats refresh when authenticated
  useEffect(() => {
    if (!isAuthenticated) return;
    const t = setInterval(() => fetchStats(), 12000);
    return () => clearInterval(t);
  }, [isAuthenticated]);

  // NOW WE CAN DO CONDITIONAL RETURNS (after all hooks are declared)

  // Transcript page (public route)
  if (isTranscript) {
    return <TranscriptPage />;
  }

  // Login page (not authenticated)
  if (!isAuthenticated) {
    return <LoginPage onLoginSuccess={handleLoginSuccess} />;
  }

  // Main dashboard (authenticated)
  return (
    <>
      <div className="grid-background" />

      <div className="shell">
        <div className="topbar">
          <div className="brand">
            <h1>
              <span className="a">ALGONOX</span> <span className="b">AADOS</span>
            </h1>
            <p>AI Agents Driven Outbound Sales</p>
          </div>

          <div
            style={{
              display: "flex",
              gap: 12,
              alignItems: "center",
              flexWrap: "wrap",
              justifyContent: "flex-end",
            }}
          >
            <button className="btn" onClick={() => setView("dashboard")}>
              DASHBOARD
            </button>
            <button className="btn" onClick={() => setView("manual-call")}>
              MANUAL CALL
            </button>
            <button className="btn" onClick={() => setView("database")}>
              DATABASE
            </button>

            <button
              className="btn"
              onClick={handleFetchLeads}
              disabled={loading}
            >
              {loading ? "FETCHING..." : "FETCH LEADS"}
            </button>

            <button
              className="btn"
              onClick={handleLogout}
              style={{
                background: "rgba(255, 68, 68, 0.2)",
                borderColor: "rgba(255, 68, 68, 0.4)",
              }}
              title="Logout"
            >
              <LogOut size={14} style={{ marginRight: 6 }} />
              LOGOUT
            </button>
          </div>
        </div>

        <div
          style={{
            marginBottom: 12,
            fontFamily: "var(--font-mono)",
            color: "var(--text-mid)",
            letterSpacing: ".12em",
          }}
        >
          WS: {wsConnected ? "CONNECTED" : "DISCONNECTED"}
        </div>

        {view === "dashboard" && (
          <>
            <div className="kpi-row">
              <div className="card kpi-cyan">
                <div className="kpi-top">
                  <Users size={18} /> TOTAL LEADS
                </div>
                <div className="kpi-value">{stats.total_leads}</div>
              </div>

              <div className="card kpi-blue">
                <div className="kpi-top">
                  <FileText size={18} /> DATA PACKETS
                </div>
                <div className="kpi-value">{stats.data_packets}</div>
              </div>

              <div className="card kpi-purple">
                <div className="kpi-top">
                  <Phone size={18} /> CALLS MADE
                </div>
                <div className="kpi-value">{stats.calls_made}</div>
              </div>

              <div className="card kpi-red">
                <div className="kpi-top">
                  <Mail size={18} /> EMAILS
                </div>
                <div className="kpi-value">{stats.emails_sent}</div>
              </div>
            </div>

            <div className="main-grid">
              <div className="card" style={{ minHeight: 320 }}>
                <div className="panel-title">LEADS PIPELINE</div>

                {leads.length === 0 ? (
                  <div className="panel-body">
                    No leads yet. Click "Fetch Leads" to start.
                  </div>
                ) : (
                  <div className="table-wrap">
                    <table className="table">
                      <thead>
                        <tr>
                          <th align="left">NAME</th>
                          <th align="left">COMPANY</th>
                          <th align="left">STATUS</th>
                        </tr>
                      </thead>
                      <tbody>
                        {leads.slice(0, 10).map((l) => (
                          <tr key={l.id}>
                            <td>{l.name}</td>
                            <td>{l.company}</td>
                            <td>{l.status}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="card" style={{ minHeight: 320 }}>
                <div className="panel-title">LIVE ACTIVITY MONITOR</div>

                <div className="activity-list">
                  {(activities.length
                    ? activities
                    : [
                        {
                          id: 1,
                          type: wsConnected ? "system" : "warning",
                          message: wsConnected
                            ? "System connected"
                            : "Connecting...",
                          timestamp: new Date().toISOString(),
                        },
                      ]
                  )
                    .slice(0, 6)
                    .map((a) => (
                      <div className="activity-item" key={a.id}>
                        <div
                          className={`activity-bar ${
                            a.type === "warning" ? "bar-err" : "bar-ok"
                          }`}
                        />
                        <div className="activity-main">
                          <div className="activity-msg">{a.message}</div>
                          <div className="activity-time">
                            {new Date(a.timestamp).toLocaleTimeString()}
                          </div>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            </div>
          </>
        )}

        {view === "manual-call" && (
          <ManualCallForm onClose={() => setView("dashboard")} />
        )}
        {view === "database" && (
          <DatabaseViewer onClose={() => setView("dashboard")} />
        )}
      </div>
    </>
  );
};

export default App;
