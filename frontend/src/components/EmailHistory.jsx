// frontend/src/components/EmailHistory.jsx
import { useState, useEffect } from "react";
import {
  Mail,
  Send,
  Eye,
  MousePointer,
  Clock,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RefreshCw,
  Edit3,
  Trash2,
  ChevronDown,
  ChevronUp,
  ExternalLink,
} from "lucide-react";

/**
 * EmailHistory - Displays all emails for a lead with status indicators
 * and actions (view, edit, resend, delete).
 */
const EmailHistory = ({
  leadId,
  emails,
  loading,
  onRefresh,
  onEdit,
  onSend,
  onDelete,
  onView,
}) => {
  const [expandedId, setExpandedId] = useState(null);
  const [sortOrder, setSortOrder] = useState("desc"); // "asc" | "desc"

  if (!leadId) {
    return (
      <div style={containerStyle}>
        <div style={{ textAlign: "center", padding: "40px", color: "#666" }}>
          Select a lead to view email history
        </div>
      </div>
    );
  }

  const sortedEmails = [...(emails || [])].sort((a, b) => {
    const dateA = new Date(a.created_at || 0);
    const dateB = new Date(b.created_at || 0);
    return sortOrder === "desc" ? dateB - dateA : dateA - dateB;
  });

  const getStatusIcon = (email) => {
    const status = (email.status || "").toLowerCase();
    if (status === "sent" && email.opened_at) {
      return <Eye size={14} style={{ color: "#00CC66" }} />;
    }
    if (status === "sent" && email.clicked_at) {
      return <MousePointer size={14} style={{ color: "#00FF88" }} />;
    }
    if (status === "sent") {
      return <CheckCircle size={14} style={{ color: "#41FFFF" }} />;
    }
    if (status === "failed") {
      return <XCircle size={14} style={{ color: "#FF4444" }} />;
    }
    if (status === "draft") {
      return <Clock size={14} style={{ color: "#FF9500" }} />;
    }
    return <Mail size={14} style={{ color: "#666" }} />;
  };

  const getStatusText = (email) => {
    const status = (email.status || "").toLowerCase();
    if (status === "sent" && email.clicked_at) return "Clicked";
    if (status === "sent" && email.opened_at) return "Opened";
    if (status === "sent") return "Sent";
    if (status === "failed") return "Failed";
    if (status === "draft") return "Draft";
    return status || "Unknown";
  };

  const getStatusColor = (email) => {
    const status = (email.status || "").toLowerCase();
    if (status === "sent" && email.clicked_at) return "#00FF88";
    if (status === "sent" && email.opened_at) return "#00CC66";
    if (status === "sent") return "#41FFFF";
    if (status === "failed") return "#FF4444";
    if (status === "draft") return "#FF9500";
    return "#666";
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return "-";
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  const toggleExpand = (id) => {
    setExpandedId(expandedId === id ? null : id);
  };

  // Analytics summary
  const stats = {
    total: emails?.length || 0,
    sent: emails?.filter((e) => e.status === "sent").length || 0,
    opened: emails?.filter((e) => e.opened_at).length || 0,
    clicked: emails?.filter((e) => e.clicked_at).length || 0,
    failed: emails?.filter((e) => e.status === "failed").length || 0,
    draft: emails?.filter((e) => e.status === "draft").length || 0,
  };

  return (
    <div style={containerStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <Mail size={20} style={{ color: "#41FFFF" }} />
          <h3 style={{ margin: 0, fontSize: "16px", color: "#F0F3F8" }}>
            Email History
          </h3>
          <span style={{ color: "#666", fontSize: "13px" }}>
            ({stats.total} emails)
          </span>
        </div>

        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
          <button
            onClick={() => setSortOrder(sortOrder === "desc" ? "asc" : "desc")}
            style={smallButtonStyle}
            title={sortOrder === "desc" ? "Newest first" : "Oldest first"}
          >
            {sortOrder === "desc" ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
          </button>
          <button
            onClick={onRefresh}
            disabled={loading}
            style={smallButtonStyle}
            title="Refresh"
          >
            <RefreshCw size={14} style={{ animation: loading ? "spin 1s linear infinite" : "none" }} />
          </button>
        </div>
      </div>

      {/* Stats Bar */}
      <div style={statsBarStyle}>
        <div style={statItemStyle}>
          <span style={{ color: "#41FFFF" }}>{stats.sent}</span>
          <span>Sent</span>
        </div>
        <div style={statItemStyle}>
          <span style={{ color: "#00CC66" }}>{stats.opened}</span>
          <span>Opened</span>
        </div>
        <div style={statItemStyle}>
          <span style={{ color: "#00FF88" }}>{stats.clicked}</span>
          <span>Clicked</span>
        </div>
        <div style={statItemStyle}>
          <span style={{ color: "#FF9500" }}>{stats.draft}</span>
          <span>Drafts</span>
        </div>
        <div style={statItemStyle}>
          <span style={{ color: "#FF4444" }}>{stats.failed}</span>
          <span>Failed</span>
        </div>
      </div>

      {/* Email List */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {loading && emails?.length === 0 ? (
          <div style={{ textAlign: "center", padding: "40px", color: "#666" }}>
            Loading emails...
          </div>
        ) : sortedEmails.length === 0 ? (
          <div style={{ textAlign: "center", padding: "40px", color: "#666" }}>
            No emails found for this lead
          </div>
        ) : (
          sortedEmails.map((email) => (
            <div key={email.id} style={emailItemStyle(expandedId === email.id)}>
              {/* Email Row */}
              <div
                style={emailRowStyle}
                onClick={() => toggleExpand(email.id)}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "12px", flex: 1 }}>
                  {getStatusIcon(email)}
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: "13px",
                        fontWeight: "500",
                        color: "#F0F3F8",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {email.subject || "(No subject)"}
                    </div>
                    <div
                      style={{
                        fontSize: "11px",
                        color: "#666",
                        marginTop: "2px",
                      }}
                    >
                      {email.email_type || "unknown"} • {formatDate(email.created_at)}
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span
                    style={{
                      fontSize: "10px",
                      fontWeight: "700",
                      color: getStatusColor(email),
                      textTransform: "uppercase",
                    }}
                  >
                    {getStatusText(email)}
                  </span>
                  {expandedId === email.id ? (
                    <ChevronUp size={14} style={{ color: "#666" }} />
                  ) : (
                    <ChevronDown size={14} style={{ color: "#666" }} />
                  )}
                </div>
              </div>

              {/* Expanded Details */}
              {expandedId === email.id && (
                <div style={expandedStyle}>
                  {/* Tracking Info */}
                  <div style={trackingInfoStyle}>
                    {email.sent_at && (
                      <div style={trackingItemStyle}>
                        <Send size={12} />
                        Sent: {formatDate(email.sent_at)}
                      </div>
                    )}
                    {email.opened_at && (
                      <div style={trackingItemStyle}>
                        <Eye size={12} style={{ color: "#00CC66" }} />
                        Opened: {formatDate(email.opened_at)}
                      </div>
                    )}
                    {email.clicked_at && (
                      <div style={trackingItemStyle}>
                        <MousePointer size={12} style={{ color: "#00FF88" }} />
                        Clicked: {formatDate(email.clicked_at)}
                      </div>
                    )}
                    {email.error_category && (
                      <div style={{ ...trackingItemStyle, color: "#FF6666" }}>
                        <AlertTriangle size={12} />
                        Error: {email.error_category}
                        {email.retry_count > 0 && ` (${email.retry_count} retries)`}
                      </div>
                    )}
                  </div>

                  {/* Preview */}
                  <div style={previewStyle}>
                    <div
                      style={{
                        fontSize: "12px",
                        color: "#333",
                        lineHeight: "1.5",
                        maxHeight: "100px",
                        overflow: "hidden",
                      }}
                      dangerouslySetInnerHTML={{
                        __html: email.body_html?.substring(0, 500) + "...",
                      }}
                    />
                  </div>

                  {/* Actions */}
                  <div style={actionsStyle}>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onView?.(email);
                      }}
                      style={actionButtonStyle}
                    >
                      <ExternalLink size={12} /> View
                    </button>
                    {email.status === "draft" && (
                      <>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onEdit?.(email);
                          }}
                          style={actionButtonStyle}
                        >
                          <Edit3 size={12} /> Edit
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSend?.(email.id);
                          }}
                          style={{ ...actionButtonStyle, color: "#41FFFF" }}
                        >
                          <Send size={12} /> Send
                        </button>
                      </>
                    )}
                    {email.status === "failed" && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSend?.(email.id);
                        }}
                        style={{ ...actionButtonStyle, color: "#FF9500" }}
                      >
                        <RefreshCw size={12} /> Retry
                      </button>
                    )}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        if (window.confirm("Delete this email?")) {
                          onDelete?.(email.id);
                        }
                      }}
                      style={{ ...actionButtonStyle, color: "#FF6666" }}
                    >
                      <Trash2 size={12} /> Delete
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* CSS for spinner animation */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

// Styles
const containerStyle = {
  background: "linear-gradient(135deg, #0A0D10 0%, #0E1116 100%)",
  borderRadius: "12px",
  border: "1px solid rgba(65, 255, 255, 0.2)",
  display: "flex",
  flexDirection: "column",
  height: "100%",
  overflow: "hidden",
};

const headerStyle = {
  padding: "16px 20px",
  borderBottom: "1px solid rgba(65, 255, 255, 0.1)",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const smallButtonStyle = {
  padding: "6px",
  border: "1px solid rgba(255, 255, 255, 0.2)",
  background: "transparent",
  color: "#A2A7AF",
  cursor: "pointer",
  borderRadius: "4px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
};

const statsBarStyle = {
  display: "flex",
  justifyContent: "space-around",
  padding: "12px 20px",
  borderBottom: "1px solid rgba(65, 255, 255, 0.1)",
  background: "rgba(0, 0, 0, 0.2)",
};

const statItemStyle = {
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: "2px",
  fontSize: "11px",
  color: "#666",
};

const emailItemStyle = (expanded) => ({
  borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
  background: expanded ? "rgba(65, 255, 255, 0.05)" : "transparent",
  transition: "background 0.2s",
});

const emailRowStyle = {
  padding: "12px 20px",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  cursor: "pointer",
  gap: "12px",
};

const expandedStyle = {
  padding: "0 20px 16px 46px",
};

const trackingInfoStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "12px",
  fontSize: "11px",
  color: "#A2A7AF",
  marginBottom: "12px",
};

const trackingItemStyle = {
  display: "flex",
  alignItems: "center",
  gap: "4px",
};

const previewStyle = {
  background: "#fff",
  borderRadius: "6px",
  padding: "12px",
  marginBottom: "12px",
};

const actionsStyle = {
  display: "flex",
  gap: "8px",
};

const actionButtonStyle = {
  padding: "6px 10px",
  border: "1px solid rgba(255, 255, 255, 0.2)",
  background: "rgba(255, 255, 255, 0.05)",
  color: "#A2A7AF",
  cursor: "pointer",
  borderRadius: "4px",
  fontSize: "11px",
  display: "flex",
  alignItems: "center",
  gap: "4px",
};

export default EmailHistory;
