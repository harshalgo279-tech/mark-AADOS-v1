// frontend/src/components/TranscriptPage.jsx
import { useEffect, useMemo, useState } from "react";
import api from "../utils/api";

const TranscriptPage = () => {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const queryCallId = params.get("call_id");
  const storedCallId = sessionStorage.getItem("aados_last_call_id");

  const callId = queryCallId || storedCallId;

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchTranscript = async () => {
    if (!callId) {
      setError("Missing call_id. Open this page from the Call Lead button.");
      return;
    }

    setLoading(true);
    setError("");
    try {
      const res = await api.get(`/api/calls/${callId}/transcript`);
      setData(res.data || null);
      setLastUpdated(new Date().toISOString());
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Failed to load transcript");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTranscript();
  }, [callId]); // eslint-disable-line

  useEffect(() => {
    if (!callId) return;
    const t = setInterval(() => {
      const status = String(data?.status || "").toLowerCase();
      if (!status || (status !== "completed" && status !== "failed" && status !== "canceled")) {
        fetchTranscript();
      }
    }, 2500);
    return () => clearInterval(t);
  }, [callId, data?.status]); // eslint-disable-line

  const transcriptText =
    data?.full_transcript ||
    data?.transcript_record?.full_transcript ||
    "";

  return (
    <>
      <div className="grid-background" />

      <div className="shell">

        {/* HEADER */}
        <div className="topbar">
          <div className="brand">
            <h1>
              <span className="a">ALGONOX</span> <span className="b">AADOS</span>
            </h1>
            <p>Call Transcript</p>
          </div>

          <div style={{ display: "flex", gap: 12 }}>
            <button className="btn" onClick={fetchTranscript} disabled={loading}>
              {loading ? "REFRESHING..." : "REFRESH"}
            </button>
            <button className="btn" onClick={() => window.close()}>
              CLOSE TAB
            </button>
          </div>
        </div>

        {/* ERROR */}
        {error && (
          <div className="alert-error">
            {error}
          </div>
        )}

        {/* CALL DETAILS */}
        <div className="card" style={{ padding: 18, marginBottom: 16 }}>
          <div className="panel-title">CALL DETAILS</div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 12,
              marginTop: 10,
            }}
          >
            <KV k="Call ID" v={data?.call_id || callId || "-"} />
            <KV k="Lead ID" v={data?.lead_id ?? "-"} />
            <KV k="Status" v={data?.status || "-"} />
            <KV k="Duration" v={data?.duration ? `${data.duration}s` : "-"} />
            <KV k="Sentiment" v={data?.sentiment || "-"} />
            <KV k="Interest" v={data?.interest_level || "-"} />
            <KV
              k="Recording"
              v={
                data?.recording_url ? (
                  <a
                    href={data.recording_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "var(--accent-purple)", fontWeight: 700 }}
                  >
                    Open recording
                  </a>
                ) : "-"
              }
            />
            <KV
              k="Last updated"
              v={lastUpdated ? new Date(lastUpdated).toLocaleTimeString() : "-"}
            />
          </div>
        </div>

        {/* SUMMARY */}
        <div className="card" style={{ padding: 18, marginBottom: 16 }}>
          <div className="panel-title">SUMMARY</div>

          <div
            className="panel-body"
            style={{
              minHeight: 90,
              whiteSpace: "pre-wrap",
            }}
          >
            {data?.transcript_summary ||
              "No summary yet. This appears after analysis completes."}
          </div>
        </div>

        {/* FULL TRANSCRIPT */}
        <div className="card" style={{ padding: 18 }}>
          <div className="panel-title">FULL TRANSCRIPT</div>

          {transcriptText ? (
            <div
              style={{
                marginTop: 12,
                borderRadius: 12,
                border: "1px solid rgba(147,51,234,0.15)",
                background: "rgba(248,245,255,0.75)",
                padding: 14,
                maxHeight: "60vh",
                overflowY: "auto",
                fontFamily: "var(--font-mono)",
                lineHeight: 1.45,
                color: "#1F2937",
              }}
            >
              {transcriptText}
            </div>
          ) : (
            <div className="panel-body">
              No transcript yet. If the call just ended, wait ~10–30s.
              This page auto-refreshes.
            </div>
          )}
        </div>
      </div>
    </>
  );
};

const KV = ({ k, v }) => (
  <div
    style={{
      display: "flex",
      justifyContent: "space-between",
      gap: 12,
      padding: "10px 12px",
      borderRadius: 12,
      border: "1px solid rgba(147,51,234,0.12)",
      background: "rgba(248,245,255,.75)",
    }}
  >
    <div
      style={{
        color: "#6B7280",
        fontFamily: "var(--font-mono)",
        letterSpacing: ".08em",
        fontSize: 11,
        textTransform: "uppercase",
        fontWeight: 700,
      }}
    >
      {k}
    </div>
    <div
      style={{
        color: "#1F2937",
        fontFamily: "var(--font-mono)",
        fontSize: 12,
      }}
    >
      {v}
    </div>
  </div>
);

export default TranscriptPage;
