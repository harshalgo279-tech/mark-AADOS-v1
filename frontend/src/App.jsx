// frontend/src/App.jsx
import { useEffect, useMemo, useState } from "react";
import { Users, FileText, Phone, Mail } from "lucide-react";
import ManualCallForm from "./components/ManualCallForm";
import DatabaseViewer from "./components/DatabaseViewer";
import WebSocketManager from "./utils/websocket";
import api from "./utils/api";
import TranscriptPage from "./components/TranscriptPage";

const WS_URL = import.meta?.env?.VITE_WS_URL || "ws://localhost:8000/ws";

// Use the same base URL axios is using (fallback to env, then localhost)
const API_BASE =
  api?.defaults?.baseURL ||
  import.meta?.env?.VITE_BACKEND_URL ||
  "http://127.0.0.1:8000";

const App = () => {
  /**
   * ✅ Lightweight routing without react-router
   * - /transcript opens TranscriptPage (new tab)
   * - Everything else runs inside the main shell
   */
  const isTranscript = useMemo(
    () => window.location.pathname.startsWith("/transcript"),
    []
  );
  if (isTranscript) return <TranscriptPage />;

  const [view, setView] = useState("dashboard");
  const [loading, setLoading] = useState(false);

  const [stats, setStats] = useState({
    total_leads: 0,
    data_packets: 0,
    calls_made: 0,
    pdfs_generated: 0,
    emails_sent: 0,
  });

  const [leads, setLeads] = useState([]);
  const [activities, setActivities] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);

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

  // ✅ Auto-download helper for the PDF (uses absolute URL)
  const triggerPdfDownload = (
    relativeUrl,
    suggestedFilename = "linkedin_pack.pdf"
  ) => {
    if (!relativeUrl) return;

    const base = (API_BASE || "").replace(/\/+$/, ""); // remove trailing /
    const path = String(relativeUrl || "");
    const url = path.startsWith("http")
      ? path
      : `${base}${path.startsWith("/") ? "" : "/"}${path}`;

    const a = document.createElement("a");
    a.href = url;
    a.download = suggestedFilename;
    a.target = "_blank";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const safeFilenamePart = (s) =>
    String(s || "")
      .replace(/[\\/:*?"<>|]+/g, "") // windows forbidden chars
      .replace(/\s+/g, "_")
      .trim()
      .slice(0, 60);

  const fetchStats = async () => {
    try {
      const res = await api.get("/api/reports/dashboard");
      const d = res.data || {};

      setStats({
        total_leads: d.leads?.total ?? 0,
        data_packets: d.leads?.data_packets_created ?? 0,
        calls_made: d.calls?.total ?? 0,
        pdfs_generated: d.pdfs?.generated ?? 0,
        emails_sent: d.emails?.sent ?? 0,
      });
    } catch (error) {
      console.error("❌ Stats error:", error);
      addActivity(
        "error",
        `Failed to load stats: ${error?.message || "unknown error"}`
      );
    }
  };

  const fetchLeads = async () => {
    try {
      const res = await api.get("/api/leads/");
      setLeads(Array.isArray(res.data) ? res.data : []);
    } catch (e) {
      addActivity("error", "Connection error");
    }
  };

  const handleFetchLeads = async () => {
    setLoading(true);
    try {
      addActivity("system", "Starting Apollo lead fetch...");
      const res = await api.post("/api/leads/fetch?count=20");

      if (res.data?.status === "success") {
        addActivity("success", `Fetched ${res.data.count ?? 0} leads from Apollo`);
        await fetchLeads();
        await fetchStats();
      } else {
        addActivity("error", "Apollo fetch returned unexpected response");
      }
    } catch (e) {
      addActivity("error", "Connection error");
    } finally {
      setLoading(false);
    }
  };

  // ✅ WebSocket lifecycle + map server events into Activity Monitor
  useEffect(() => {
    const ws = new WebSocketManager(WS_URL);

    ws.on("connected", () => {
      setWsConnected(true);
      addActivity("system", "System connected");
    });

    ws.on("disconnected", () => {
      setWsConnected(false);
      addActivity("error", "Connection error");
    });

    ws.on("error", () => addActivity("error", "Connection error"));

    // ✅ When backend broadcasts that the LinkedIn PDF is ready, auto-download it
    ws.on("linkedin_pack_ready", (data) => {
      try {
        const downloadUrl = data?.download_url || `/api/calls/${data?.call_id}/linkedin-pack/pdf`;
        const leadName = safeFilenamePart(data?.lead_name || "lead");
        const company = safeFilenamePart(data?.company || "company");
        const callId = data?.call_id || "call";

        const filename = `${leadName}_${company}_call_${callId}_linkedin_pack.pdf`;

        addActivity(
          "success",
          `LinkedIn PDF ready (call_id=${callId}). Downloading...`
        );

        triggerPdfDownload(downloadUrl, filename);
      } catch (e) {
        addActivity("error", "PDF auto-download failed");
      }
    });

    // Optional: log other structured events if your backend emits them
    ws.on("call_status", (data) => {
      if (!data?.call_id) return;
      addActivity("system", `Call status: ${data.status} (call_id=${data.call_id})`);
    });

    ws.on("call_transcript_update", (data) => {
      // keep the feed lightweight (don’t spam); just show the latest delta
      if (data?.delta) addActivity("system", data.delta);
    });

    ws.on("call_in_progress", (data) => {
      if (data?.call_id) addActivity("system", `Call in progress (call_id=${data.call_id})`);
    });

    ws.connect();
    return () => ws.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Initial load
  useEffect(() => {
    fetchStats();
    fetchLeads();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll stats
  useEffect(() => {
    const t = setInterval(() => fetchStats(), 12000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <div className="grid-background" />

      <div className="shell">
        {/* TOP BAR */}
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

            <button className="btn" onClick={handleFetchLeads} disabled={loading}>
              {loading ? "FETCHING..." : "FETCH LEADS"}
            </button>
          </div>
        </div>

        {/* STATUS */}
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

        {/* DASHBOARD */}
        {view === "dashboard" && (
          <>
            {/* KPI Row */}
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

              <div className="card kpi-orange">
                <div className="kpi-top">
                  <FileText size={18} /> PDFS GENERATED
                </div>
                <div className="kpi-value">{stats.pdfs_generated}</div>
              </div>

              <div className="card kpi-red">
                <div className="kpi-top">
                  <Mail size={18} /> EMAILS SENT
                </div>
                <div className="kpi-value">{stats.emails_sent}</div>
              </div>
            </div>

            {/* Main Panels */}
            <div className="main-grid">
              {/* Leads Pipeline */}
              <div className="card" style={{ minHeight: 320 }}>
                <div className="panel-title">LEADS PIPELINE</div>

                {leads.length === 0 ? (
                  <div className="panel-body">No leads yet. Click "Fetch Leads" to start.</div>
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

              {/* Live Activity Monitor */}
              <div className="card" style={{ minHeight: 320 }}>
                <div className="panel-title">LIVE ACTIVITY MONITOR</div>

                <div className="activity-list">
                  {(activities.length
                    ? activities
                    : [
                        {
                          id: 1,
                          type: wsConnected ? "system" : "error",
                          message: wsConnected ? "System connected" : "Connection error",
                          timestamp: new Date().toISOString(),
                        },
                      ]
                  )
                    .slice(0, 6)
                    .map((a) => (
                      <div className="activity-item" key={a.id}>
                        <div className={`activity-bar ${a.type === "error" ? "bar-err" : "bar-ok"}`} />
                        <div className="activity-main">
                          <div className="activity-msg">{a.message}</div>
                          <div className="activity-time">{new Date(a.timestamp).toLocaleTimeString()}</div>
                        </div>
                      </div>
                    ))}
                </div>
              </div>
            </div>
          </>
        )}

        {/* MODALS */}
        {view === "manual-call" && <ManualCallForm onClose={() => setView("dashboard")} />}
        {view === "database" && <DatabaseViewer onClose={() => setView("dashboard")} />}
      </div>
    </>
  );
};

export default App;
