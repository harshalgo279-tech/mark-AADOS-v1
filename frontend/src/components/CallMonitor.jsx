// frontend/src/components/CallMonitor.jsx
import { Phone, Clock, FileText, X } from "lucide-react";

const CallMonitor = ({ callId, status, transcript, onClose }) => {
  return (
    <div style={overlay}>
      <div style={card}>
        <div style={topRow}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Phone size={22} style={{ color: "#41FFFF" }} />
            <div style={{ color: "#F0F3F8", fontWeight: 800, letterSpacing: ".12em" }}>
              CALL MONITOR {callId ? `#${callId}` : ""}
            </div>
          </div>
          <button onClick={onClose} style={iconBtn}>
            <X size={20} />
          </button>
        </div>

        <div style={{ color: "#A2A7AF", fontSize: 13, marginBottom: 10 }}>
          Status: <span style={{ color: "#41FFFF" }}>{status || "in_progress"}</span>
        </div>

        <div style={transcriptHeader}>
          <FileText size={16} style={{ color: "#41FFFF" }} />
          <div style={{ color: "#F0F3F8", fontSize: 12, letterSpacing: ".12em", fontWeight: 800 }}>
            LIVE TRANSCRIPT
          </div>
        </div>

        <div style={transcriptBox}>
          {transcript || "No transcript yet... keep this open while call completes."}
        </div>
      </div>
    </div>
  );
};

const overlay = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.85)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 2000,
  backdropFilter: "blur(8px)",
  padding: 20,
};

const card = {
  background: "linear-gradient(135deg, #0A0D10 0%, #0E1116 100%)",
  border: "2px solid #41FFFF",
  borderRadius: 16,
  padding: 22,
  width: "100%",
  maxWidth: 760,
  boxShadow: "0 0 60px rgba(65,255,255,0.3)",
};

const topRow = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: 12,
};

const iconBtn = {
  background: "transparent",
  border: "none",
  color: "#F0F3F8",
  cursor: "pointer",
  padding: 8,
};

const transcriptHeader = {
  display: "flex",
  gap: 10,
  alignItems: "center",
  marginTop: 10,
  marginBottom: 8,
};

const transcriptBox = {
  minHeight: 240,
  background: "rgba(14, 17, 22, 0.6)",
  border: "1px solid rgba(65, 255, 255, 0.25)",
  borderRadius: 10,
  padding: 12,
  color: "#E6EDF6",
  fontSize: 13,
  lineHeight: 1.55,
  whiteSpace: "pre-wrap",
  fontFamily:
    "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
};

export default CallMonitor;
