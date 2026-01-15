// frontend/src/components/CallMonitor.jsx
import { Phone, FileText, X, ExternalLink } from "lucide-react";

const CallMonitor = ({ callId, status, transcript, onClose, onOpenTranscript }) => {
  const prettyStatus = String(status || "in-progress");
  const formatted = formatTranscript(transcript);

  return (
    <div style={overlay}>
      <div style={card}>
        <div style={topRow}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Phone size={22} style={{ color: "#0EA5E9" }} />
            <div style={title}>
              CALL MONITOR {callId ? `#${callId}` : ""}
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {onOpenTranscript && (
              <button onClick={onOpenTranscript} style={linkBtn}>
                <ExternalLink size={16} /> Open Transcript
              </button>
            )}
            <button onClick={onClose} style={iconBtn} aria-label="Close">
              <X size={20} />
            </button>
          </div>
        </div>

        <div style={statusRow}>
          Status: <span style={statusPill}>{prettyStatus}</span>
        </div>

        <div style={transcriptHeader}>
          <FileText size={16} style={{ color: "#0EA5E9" }} />
          <div style={transcriptTitle}>LIVE TRANSCRIPT</div>
        </div>

        <div style={transcriptBox}>
          {formatted || "No transcript yet..."}
        </div>
      </div>
    </div>
  );
};

function formatTranscript(t) {
  const s = String(t || "").trim();
  if (!s) return "";

  return s
    .replace(/\s+(AGENT:)/g, "\n$1")
    .replace(/\s+(LEAD:)/g, "\n$1")
    .trim();
}

const overlay = {
  position: "fixed",
  inset: 0,
  background: "rgba(255,255,255,0.75)", // ✅ light overlay instead of black
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 2000,
  backdropFilter: "blur(8px)",
  padding: 20,
};

const card = {
  background: "#FFFFFF",              // ✅ white card
  border: "1px solid rgba(15, 23, 42, 0.12)",
  borderRadius: 16,
  padding: 22,
  width: "100%",
  maxWidth: 820,
  boxShadow: "0 20px 80px rgba(2, 6, 23, 0.18)",
};

const title = {
  color: "#0F172A",
  fontWeight: 900,
  letterSpacing: ".08em",
};

const topRow = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: 12,
};

const statusRow = {
  color: "#334155",
  fontSize: 13,
  marginBottom: 10,
};

const statusPill = {
  display: "inline-block",
  marginLeft: 6,
  padding: "4px 10px",
  borderRadius: 999,
  background: "rgba(14, 165, 233, 0.10)",
  border: "1px solid rgba(14, 165, 233, 0.25)",
  color: "#0369A1",
  fontWeight: 800,
};

const iconBtn = {
  background: "transparent",
  border: "1px solid rgba(15, 23, 42, 0.15)",
  color: "#0F172A",
  cursor: "pointer",
  padding: 8,
  borderRadius: 10,
};

const linkBtn = {
  display: "flex",
  gap: 8,
  alignItems: "center",
  background: "rgba(14, 165, 233, 0.10)",
  border: "1px solid rgba(14, 165, 233, 0.25)",
  color: "#0369A1",
  cursor: "pointer",
  padding: "8px 12px",
  borderRadius: 10,
  fontSize: 12,
  fontWeight: 800,
  letterSpacing: ".06em",
};

const transcriptHeader = {
  display: "flex",
  gap: 10,
  alignItems: "center",
  marginTop: 10,
  marginBottom: 8,
};

const transcriptTitle = {
  color: "#0F172A",
  fontSize: 12,
  letterSpacing: ".12em",
  fontWeight: 900,
};

const transcriptBox = {
  minHeight: 260,
  maxHeight: "55vh",
  overflowY: "auto",
  background: "#F8FAFC",
  border: "1px solid rgba(15, 23, 42, 0.10)",
  borderRadius: 12,
  padding: 12,
  color: "#0F172A",
  fontSize: 13,
  lineHeight: 1.55,
  whiteSpace: "pre-wrap",
  fontFamily:
    "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
};

export default CallMonitor;
