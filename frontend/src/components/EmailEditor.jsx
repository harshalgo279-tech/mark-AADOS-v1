// frontend/src/components/EmailEditor.jsx
import { useState, useEffect } from "react";
import { Mail, Send, Save, X, Eye, Code, AlertCircle } from "lucide-react";

/**
 * EmailEditor - Allows editing email subject and body before sending.
 * Supports both HTML preview and source editing modes.
 */
const EmailEditor = ({ email, onClose, onSave, onSend, saving, sending }) => {
  const [subject, setSubject] = useState("");
  const [bodyHtml, setBodyHtml] = useState("");
  const [bodyText, setBodyText] = useState("");
  const [previewText, setPreviewText] = useState("");
  const [viewMode, setViewMode] = useState("preview"); // "preview" | "html" | "text"
  const [hasChanges, setHasChanges] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (email) {
      setSubject(email.subject || "");
      setBodyHtml(email.body_html || "");
      setBodyText(email.body_text || "");
      setPreviewText(email.preview_text || "");
      setHasChanges(false);
    }
  }, [email]);

  if (!email) return null;

  const isSent = String(email.status || "").toLowerCase() === "sent";
  const isFailed = String(email.status || "").toLowerCase() === "failed";

  const handleSubjectChange = (e) => {
    setSubject(e.target.value);
    setHasChanges(true);
  };

  const handleBodyHtmlChange = (e) => {
    setBodyHtml(e.target.value);
    setHasChanges(true);
  };

  const handleBodyTextChange = (e) => {
    setBodyText(e.target.value);
    setHasChanges(true);
  };

  const handlePreviewTextChange = (e) => {
    setPreviewText(e.target.value);
    setHasChanges(true);
  };

  const handleSave = async () => {
    if (!onSave) return;
    setError(null);
    try {
      await onSave({
        id: email.id,
        subject,
        body_html: bodyHtml,
        body_text: bodyText,
        preview_text: previewText,
      });
      setHasChanges(false);
    } catch (err) {
      setError(err.message || "Failed to save email");
    }
  };

  const handleSend = async () => {
    if (!onSend) return;
    setError(null);
    // Save first if there are changes
    if (hasChanges && onSave) {
      try {
        await onSave({
          id: email.id,
          subject,
          body_html: bodyHtml,
          body_text: bodyText,
          preview_text: previewText,
        });
        setHasChanges(false);
      } catch (err) {
        setError("Failed to save before sending: " + (err.message || ""));
        return;
      }
    }
    try {
      await onSend(email.id);
    } catch (err) {
      setError(err.message || "Failed to send email");
    }
  };

  const handleClose = () => {
    if (hasChanges) {
      if (!window.confirm("You have unsaved changes. Discard them?")) {
        return;
      }
    }
    onClose();
  };

  // Styles
  const overlayStyle = {
    position: "fixed",
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: "rgba(0, 0, 0, 0.85)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
    backdropFilter: "blur(8px)",
    padding: "20px",
  };

  const modalStyle = {
    background: "#FFFFFF",
    borderRadius: "12px",
    maxWidth: "900px",
    width: "100%",
    maxHeight: "95vh",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
    boxShadow: "0 0 60px rgba(0, 0, 0, 0.5)",
  };

  const headerStyle = {
    background: "linear-gradient(135deg, #0A0D10 0%, #0E1116 100%)",
    padding: "20px 24px",
    borderBottom: "2px solid #41FFFF",
  };

  const buttonStyle = (primary = false, disabled = false) => ({
    padding: "8px 14px",
    border: primary ? "1px solid rgba(65,255,255,0.6)" : "1px solid rgba(255, 255, 255, 0.3)",
    background: disabled
      ? "rgba(0,0,0,0.2)"
      : primary
      ? "rgba(65,255,255,0.15)"
      : "transparent",
    color: "#F0F3F8",
    cursor: disabled ? "not-allowed" : "pointer",
    borderRadius: "6px",
    fontSize: "12px",
    display: "flex",
    alignItems: "center",
    gap: 6,
    opacity: disabled ? 0.5 : 1,
  });

  const tabButtonStyle = (active) => ({
    padding: "6px 12px",
    border: "none",
    background: active ? "rgba(65,255,255,0.2)" : "transparent",
    color: active ? "#41FFFF" : "#A2A7AF",
    cursor: "pointer",
    borderRadius: "4px",
    fontSize: "12px",
    display: "flex",
    alignItems: "center",
    gap: 4,
  });

  const inputStyle = {
    width: "100%",
    padding: "10px 12px",
    border: "1px solid #E0E0E0",
    borderRadius: "6px",
    fontSize: "14px",
    outline: "none",
    transition: "border-color 0.2s",
  };

  const textareaStyle = {
    ...inputStyle,
    minHeight: "300px",
    fontFamily: viewMode === "html" ? "monospace" : "inherit",
    fontSize: viewMode === "html" ? "13px" : "14px",
    resize: "vertical",
  };

  return (
    <div style={overlayStyle}>
      <div style={modalStyle}>
        {/* Header */}
        <div style={headerStyle}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
              <Mail size={24} style={{ color: "#41FFFF" }} />
              <h3 style={{ fontSize: "18px", color: "#F0F3F8", fontWeight: "600", margin: 0 }}>
                Edit Email Draft
              </h3>
              {hasChanges && (
                <span
                  style={{
                    background: "#FF9500",
                    color: "#000",
                    padding: "2px 8px",
                    borderRadius: "4px",
                    fontSize: "10px",
                    fontWeight: "700",
                  }}
                >
                  UNSAVED
                </span>
              )}
            </div>

            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              {/* View Mode Tabs */}
              <div
                style={{
                  display: "flex",
                  gap: 2,
                  background: "rgba(255,255,255,0.1)",
                  borderRadius: "6px",
                  padding: "2px",
                }}
              >
                <button style={tabButtonStyle(viewMode === "preview")} onClick={() => setViewMode("preview")}>
                  <Eye size={12} /> Preview
                </button>
                <button style={tabButtonStyle(viewMode === "html")} onClick={() => setViewMode("html")}>
                  <Code size={12} /> HTML
                </button>
                <button style={tabButtonStyle(viewMode === "text")} onClick={() => setViewMode("text")}>
                  Text
                </button>
              </div>

              {/* Action Buttons */}
              <button
                onClick={handleSave}
                disabled={!hasChanges || saving || isSent}
                style={buttonStyle(false, !hasChanges || saving || isSent)}
              >
                <Save size={14} />
                {saving ? "SAVING..." : "SAVE"}
              </button>

              <button
                onClick={handleSend}
                disabled={sending || isSent}
                style={buttonStyle(true, sending || isSent)}
              >
                <Send size={14} />
                {isSent ? "SENT" : sending ? "SENDING..." : "SEND"}
              </button>

              <button onClick={handleClose} style={buttonStyle(false, false)}>
                <X size={14} />
              </button>
            </div>
          </div>

          {/* Status Bar */}
          <div
            style={{
              marginTop: "12px",
              padding: "8px 12px",
              background: "rgba(65, 255, 255, 0.1)",
              borderRadius: "6px",
              display: "flex",
              gap: "16px",
              fontSize: "12px",
              color: "#A2A7AF",
              flexWrap: "wrap",
            }}
          >
            <span>
              Type: <strong style={{ color: "#F0F3F8" }}>{email.email_type || "unknown"}</strong>
            </span>
            <span>
              Status:{" "}
              <strong
                style={{
                  color: isSent ? "#00FF88" : isFailed ? "#FF4444" : "#FF9500",
                }}
              >
                {email.status || "draft"}
              </strong>
            </span>
            {email.sent_at && (
              <span>
                Sent: <strong style={{ color: "#F0F3F8" }}>{new Date(email.sent_at).toLocaleString()}</strong>
              </span>
            )}
            {email.opened_at && (
              <span>
                Opened: <strong style={{ color: "#00FF88" }}>{new Date(email.opened_at).toLocaleString()}</strong>
              </span>
            )}
          </div>

          {/* Error Message */}
          {error && (
            <div
              style={{
                marginTop: "12px",
                padding: "10px 12px",
                background: "rgba(255, 68, 68, 0.2)",
                border: "1px solid rgba(255, 68, 68, 0.4)",
                borderRadius: "6px",
                display: "flex",
                alignItems: "center",
                gap: "8px",
                fontSize: "13px",
                color: "#FF6666",
              }}
            >
              <AlertCircle size={16} />
              {error}
            </div>
          )}
        </div>

        {/* Body */}
        <div style={{ padding: "24px", overflowY: "auto", flex: 1 }}>
          {/* Subject */}
          <div style={{ marginBottom: "16px" }}>
            <label style={{ display: "block", fontSize: "12px", color: "#666", marginBottom: "6px", fontWeight: "600" }}>
              SUBJECT
            </label>
            <input
              type="text"
              value={subject}
              onChange={handleSubjectChange}
              disabled={isSent}
              style={{
                ...inputStyle,
                fontWeight: "600",
                background: isSent ? "#f5f5f5" : "#fff",
              }}
              placeholder="Enter email subject..."
            />
          </div>

          {/* Preview Text */}
          <div style={{ marginBottom: "16px" }}>
            <label style={{ display: "block", fontSize: "12px", color: "#666", marginBottom: "6px", fontWeight: "600" }}>
              PREVIEW TEXT <span style={{ fontWeight: "400", color: "#999" }}>(shown in inbox preview)</span>
            </label>
            <input
              type="text"
              value={previewText}
              onChange={handlePreviewTextChange}
              disabled={isSent}
              maxLength={255}
              style={{
                ...inputStyle,
                background: isSent ? "#f5f5f5" : "#fff",
              }}
              placeholder="Optional preview text for email clients..."
            />
            <div style={{ fontSize: "11px", color: "#999", marginTop: "4px" }}>
              {previewText.length}/255 characters
            </div>
          </div>

          {/* Body Content */}
          <div>
            <label style={{ display: "block", fontSize: "12px", color: "#666", marginBottom: "6px", fontWeight: "600" }}>
              {viewMode === "preview" ? "BODY PREVIEW" : viewMode === "html" ? "BODY HTML" : "BODY PLAIN TEXT"}
            </label>

            {viewMode === "preview" ? (
              <div
                style={{
                  border: "1px solid #E0E0E0",
                  borderRadius: "6px",
                  padding: "20px",
                  minHeight: "300px",
                  lineHeight: "1.7",
                  fontSize: "14px",
                  color: "#333",
                  background: "#fafafa",
                }}
                dangerouslySetInnerHTML={{ __html: bodyHtml }}
              />
            ) : viewMode === "html" ? (
              <textarea
                value={bodyHtml}
                onChange={handleBodyHtmlChange}
                disabled={isSent}
                style={{
                  ...textareaStyle,
                  background: isSent ? "#f5f5f5" : "#fff",
                }}
                placeholder="<p>Your email HTML content...</p>"
              />
            ) : (
              <textarea
                value={bodyText}
                onChange={handleBodyTextChange}
                disabled={isSent}
                style={{
                  ...textareaStyle,
                  fontFamily: "inherit",
                  background: isSent ? "#f5f5f5" : "#fff",
                }}
                placeholder="Plain text version of your email..."
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default EmailEditor;
