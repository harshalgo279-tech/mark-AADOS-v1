// frontend/src/components/EmailIntelligenceDashboard.jsx
import { useState, useEffect } from "react";
import {
  Brain,
  TrendingUp,
  Users,
  Mail,
  Clock,
  Target,
  AlertTriangle,
  CheckCircle,
  Zap,
  BarChart3,
  RefreshCw,
  ChevronRight,
  Flame,
  Thermometer,
  Snowflake,
} from "lucide-react";

/**
 * EmailIntelligenceDashboard - AI-powered email analytics and insights
 *
 * Features:
 * - Engagement level breakdown (hot/warm/cold leads)
 * - Deliverability health monitoring
 * - Top engaged leads
 * - A/B test results
 * - Real-time recommendations
 */
const EmailIntelligenceDashboard = ({ onSelectLead }) => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [healthData, setHealthData] = useState(null);
  const [engagementSummary, setEngagementSummary] = useState(null);
  const [abTests, setAbTests] = useState([]);
  const [throttleStatus, setThrottleStatus] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    setLoading(true);
    setError(null);

    try {
      const [healthRes, engagementRes, testsRes, throttleRes] = await Promise.all([
        fetch("/api/email-intelligence/health").then((r) => r.json()),
        fetch("/api/email-intelligence/engagement-summary").then((r) => r.json()),
        fetch("/api/email-intelligence/ab-tests?status=active").then((r) => r.json()),
        fetch("/api/emails/throttle/status").then((r) => r.json()),
      ]);

      setHealthData(healthRes);
      setEngagementSummary(engagementRes);
      setAbTests(testsRes.tests || []);
      setThrottleStatus(throttleRes);
    } catch (err) {
      console.error("Failed to load dashboard data:", err);
      setError("Failed to load dashboard data");
    } finally {
      setLoading(false);
    }
  };

  const refreshEngagement = async () => {
    setRefreshing(true);
    try {
      await fetch("/api/email-intelligence/refresh-all-engagement", { method: "POST" });
      await loadDashboardData();
    } catch (err) {
      console.error("Failed to refresh:", err);
    } finally {
      setRefreshing(false);
    }
  };

  if (loading) {
    return (
      <div style={containerStyle}>
        <div style={{ textAlign: "center", padding: "60px", color: "#666" }}>
          <Brain size={48} style={{ marginBottom: "16px", opacity: 0.5 }} />
          <div>Loading email intelligence...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={containerStyle}>
        <div style={{ textAlign: "center", padding: "60px", color: "#FF6666" }}>
          <AlertTriangle size={48} style={{ marginBottom: "16px" }} />
          <div>{error}</div>
          <button onClick={loadDashboardData} style={retryButtonStyle}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  const healthStatus = healthData?.health_status || "unknown";
  const healthColor =
    healthStatus === "healthy" ? "#00FF88" : healthStatus === "warning" ? "#FF9500" : "#FF4444";

  return (
    <div style={containerStyle}>
      {/* Header */}
      <div style={headerStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <Brain size={24} style={{ color: "#41FFFF" }} />
          <h2 style={{ margin: 0, fontSize: "18px", color: "#F0F3F8" }}>
            Email Intelligence
          </h2>
        </div>
        <button
          onClick={refreshEngagement}
          disabled={refreshing}
          style={refreshButtonStyle}
        >
          <RefreshCw
            size={14}
            style={{ animation: refreshing ? "spin 1s linear infinite" : "none" }}
          />
          {refreshing ? "Refreshing..." : "Refresh Scores"}
        </button>
      </div>

      {/* Health Status Banner */}
      <div style={{ ...healthBannerStyle, borderColor: healthColor }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          {healthStatus === "healthy" ? (
            <CheckCircle size={20} style={{ color: healthColor }} />
          ) : (
            <AlertTriangle size={20} style={{ color: healthColor }} />
          )}
          <div>
            <div style={{ fontWeight: "600", color: "#F0F3F8" }}>
              Deliverability: {healthStatus.toUpperCase()}
            </div>
            <div style={{ fontSize: "12px", color: "#A2A7AF", marginTop: "2px" }}>
              {healthData?.health_message}
            </div>
          </div>
        </div>
        <div style={{ display: "flex", gap: "24px", fontSize: "12px" }}>
          <div style={metricStyle}>
            <span style={{ color: "#A2A7AF" }}>Sent (7d)</span>
            <span style={{ color: "#F0F3F8", fontWeight: "600" }}>
              {healthData?.metrics?.emails_sent_7d || 0}
            </span>
          </div>
          <div style={metricStyle}>
            <span style={{ color: "#A2A7AF" }}>Open Rate</span>
            <span style={{ color: "#41FFFF", fontWeight: "600" }}>
              {healthData?.metrics?.open_rate || 0}%
            </span>
          </div>
          <div style={metricStyle}>
            <span style={{ color: "#A2A7AF" }}>Bounce Rate</span>
            <span
              style={{
                color: (healthData?.metrics?.bounce_rate || 0) > 2 ? "#FF4444" : "#00FF88",
                fontWeight: "600",
              }}
            >
              {healthData?.metrics?.bounce_rate || 0}%
            </span>
          </div>
        </div>
      </div>

      {/* Main Grid */}
      <div style={gridStyle}>
        {/* Engagement Breakdown */}
        <div style={cardStyle}>
          <div style={cardHeaderStyle}>
            <Users size={16} style={{ color: "#41FFFF" }} />
            <span>Lead Engagement</span>
          </div>
          <div style={{ padding: "16px" }}>
            <div style={engagementGridStyle}>
              <EngagementTile
                icon={<Flame size={20} />}
                label="Hot"
                count={engagementSummary?.by_level?.hot || 0}
                color="#FF4444"
                description="Ready to close"
              />
              <EngagementTile
                icon={<Thermometer size={20} />}
                label="Warm"
                count={engagementSummary?.by_level?.warm || 0}
                color="#FF9500"
                description="High interest"
              />
              <EngagementTile
                icon={<Zap size={20} />}
                label="Lukewarm"
                count={engagementSummary?.by_level?.lukewarm || 0}
                color="#FFCC00"
                description="Some interest"
              />
              <EngagementTile
                icon={<Snowflake size={20} />}
                label="Cold"
                count={engagementSummary?.by_level?.cold || 0}
                color="#41FFFF"
                description="No engagement"
              />
            </div>
            <div style={{ marginTop: "16px", fontSize: "12px", color: "#666" }}>
              Total active leads: {engagementSummary?.total_active || 0}
            </div>
          </div>
        </div>

        {/* Top Engaged Leads */}
        <div style={cardStyle}>
          <div style={cardHeaderStyle}>
            <Target size={16} style={{ color: "#41FFFF" }} />
            <span>Top Engaged Leads</span>
          </div>
          <div style={{ padding: "0" }}>
            {(engagementSummary?.top_engaged_leads || []).length === 0 ? (
              <div style={{ padding: "24px", textAlign: "center", color: "#666" }}>
                No highly engaged leads yet
              </div>
            ) : (
              (engagementSummary?.top_engaged_leads || []).slice(0, 5).map((lead) => (
                <div
                  key={lead.id}
                  style={leadRowStyle}
                  onClick={() => onSelectLead?.(lead.id)}
                >
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: "500", color: "#F0F3F8" }}>{lead.name}</div>
                    <div style={{ fontSize: "11px", color: "#666" }}>{lead.company}</div>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                    <span
                      style={{
                        ...levelBadgeStyle,
                        background:
                          lead.level === "hot"
                            ? "rgba(255,68,68,0.2)"
                            : "rgba(255,149,0,0.2)",
                        color: lead.level === "hot" ? "#FF4444" : "#FF9500",
                      }}
                    >
                      {lead.level?.toUpperCase()}
                    </span>
                    <span style={{ color: "#41FFFF", fontWeight: "600" }}>{lead.score}</span>
                    <ChevronRight size={14} style={{ color: "#666" }} />
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Warmup Status */}
        <div style={cardStyle}>
          <div style={cardHeaderStyle}>
            <TrendingUp size={16} style={{ color: "#41FFFF" }} />
            <span>Domain Warmup</span>
          </div>
          <div style={{ padding: "16px" }}>
            <div style={warmupStatusStyle}>
              <div>
                <div style={{ fontSize: "24px", fontWeight: "700", color: "#F0F3F8" }}>
                  {healthData?.warmup?.daily_average || 0}
                </div>
                <div style={{ fontSize: "11px", color: "#666" }}>avg emails/day</div>
              </div>
              <div
                style={{
                  ...warmupBadgeStyle,
                  background:
                    healthData?.warmup?.status === "warmed"
                      ? "rgba(0,255,136,0.2)"
                      : "rgba(255,149,0,0.2)",
                  color:
                    healthData?.warmup?.status === "warmed" ? "#00FF88" : "#FF9500",
                }}
              >
                {healthData?.warmup?.status?.toUpperCase() || "UNKNOWN"}
              </div>
            </div>
            <div style={{ marginTop: "12px", fontSize: "12px", color: "#A2A7AF" }}>
              {healthData?.warmup?.message}
            </div>
          </div>
        </div>

        {/* Throttle Status */}
        <div style={cardStyle}>
          <div style={cardHeaderStyle}>
            <Clock size={16} style={{ color: "#41FFFF" }} />
            <span>Send Capacity</span>
          </div>
          <div style={{ padding: "16px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
              <span style={{ fontSize: "12px", color: "#A2A7AF" }}>Hourly limit</span>
              <span style={{ fontSize: "12px", color: "#F0F3F8" }}>
                {throttleStatus?.sent_this_hour || 0} / {throttleStatus?.max_per_hour || 50}
              </span>
            </div>
            <div style={progressBarContainerStyle}>
              <div
                style={{
                  ...progressBarStyle,
                  width: `${Math.min(
                    100,
                    ((throttleStatus?.sent_this_hour || 0) / (throttleStatus?.max_per_hour || 50)) *
                      100
                  )}%`,
                  background:
                    (throttleStatus?.sent_this_hour || 0) > (throttleStatus?.max_per_hour || 50) * 0.8
                      ? "#FF9500"
                      : "#41FFFF",
                }}
              />
            </div>
            <div style={{ marginTop: "12px", fontSize: "11px", color: "#666" }}>
              {throttleStatus?.can_send
                ? "Ready to send"
                : `Reset in ${throttleStatus?.seconds_until_reset || 0}s`}
            </div>
          </div>
        </div>

        {/* Active A/B Tests */}
        <div style={{ ...cardStyle, gridColumn: "span 2" }}>
          <div style={cardHeaderStyle}>
            <BarChart3 size={16} style={{ color: "#41FFFF" }} />
            <span>Active A/B Tests</span>
          </div>
          <div style={{ padding: "0" }}>
            {abTests.length === 0 ? (
              <div style={{ padding: "24px", textAlign: "center", color: "#666" }}>
                No active A/B tests
              </div>
            ) : (
              abTests.map((test) => (
                <div key={test.id} style={testRowStyle}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: "500", color: "#F0F3F8" }}>{test.name}</div>
                    <div style={{ fontSize: "11px", color: "#666" }}>
                      {test.test_type} • {test.email_type}
                    </div>
                  </div>
                  <span style={testBadgeStyle}>{test.status}</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Recommendations */}
        <div style={{ ...cardStyle, gridColumn: "span 2" }}>
          <div style={cardHeaderStyle}>
            <Brain size={16} style={{ color: "#41FFFF" }} />
            <span>AI Recommendations</span>
          </div>
          <div style={{ padding: "16px" }}>
            {(healthData?.recommendations || []).map((rec, i) => (
              <div key={i} style={recommendationStyle}>
                <Zap size={14} style={{ color: "#41FFFF", flexShrink: 0 }} />
                <span>{rec}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* CSS Animation */}
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
};

// Engagement Tile Component
const EngagementTile = ({ icon, label, count, color, description }) => (
  <div style={{ ...engagementTileStyle, borderColor: color }}>
    <div style={{ color }}>{icon}</div>
    <div style={{ fontSize: "24px", fontWeight: "700", color: "#F0F3F8" }}>{count}</div>
    <div style={{ fontSize: "12px", fontWeight: "600", color }}>{label}</div>
    <div style={{ fontSize: "10px", color: "#666" }}>{description}</div>
  </div>
);

// Styles
const containerStyle = {
  background: "linear-gradient(135deg, #0A0D10 0%, #0E1116 100%)",
  borderRadius: "12px",
  border: "1px solid rgba(65, 255, 255, 0.2)",
  overflow: "hidden",
};

const headerStyle = {
  padding: "16px 20px",
  borderBottom: "1px solid rgba(65, 255, 255, 0.1)",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const refreshButtonStyle = {
  padding: "8px 12px",
  border: "1px solid rgba(65, 255, 255, 0.4)",
  background: "rgba(65, 255, 255, 0.1)",
  color: "#41FFFF",
  cursor: "pointer",
  borderRadius: "6px",
  fontSize: "12px",
  display: "flex",
  alignItems: "center",
  gap: "6px",
};

const retryButtonStyle = {
  marginTop: "16px",
  padding: "8px 16px",
  border: "1px solid rgba(255, 255, 255, 0.3)",
  background: "transparent",
  color: "#F0F3F8",
  cursor: "pointer",
  borderRadius: "6px",
};

const healthBannerStyle = {
  margin: "16px",
  padding: "16px",
  background: "rgba(0, 0, 0, 0.3)",
  borderRadius: "8px",
  border: "1px solid",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  flexWrap: "wrap",
  gap: "16px",
};

const metricStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "2px",
};

const gridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(2, 1fr)",
  gap: "16px",
  padding: "0 16px 16px",
};

const cardStyle = {
  background: "rgba(0, 0, 0, 0.2)",
  borderRadius: "8px",
  border: "1px solid rgba(255, 255, 255, 0.1)",
  overflow: "hidden",
};

const cardHeaderStyle = {
  padding: "12px 16px",
  borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
  display: "flex",
  alignItems: "center",
  gap: "8px",
  fontSize: "13px",
  fontWeight: "600",
  color: "#A2A7AF",
};

const engagementGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(4, 1fr)",
  gap: "12px",
};

const engagementTileStyle = {
  textAlign: "center",
  padding: "12px 8px",
  borderRadius: "8px",
  border: "1px solid",
  background: "rgba(0, 0, 0, 0.2)",
};

const leadRowStyle = {
  padding: "12px 16px",
  borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
  display: "flex",
  alignItems: "center",
  cursor: "pointer",
  transition: "background 0.2s",
};

const levelBadgeStyle = {
  padding: "2px 8px",
  borderRadius: "4px",
  fontSize: "10px",
  fontWeight: "700",
};

const warmupStatusStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
};

const warmupBadgeStyle = {
  padding: "4px 12px",
  borderRadius: "4px",
  fontSize: "11px",
  fontWeight: "700",
};

const progressBarContainerStyle = {
  height: "6px",
  background: "rgba(255, 255, 255, 0.1)",
  borderRadius: "3px",
  overflow: "hidden",
};

const progressBarStyle = {
  height: "100%",
  borderRadius: "3px",
  transition: "width 0.3s",
};

const testRowStyle = {
  padding: "12px 16px",
  borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
  display: "flex",
  alignItems: "center",
};

const testBadgeStyle = {
  padding: "2px 8px",
  background: "rgba(65, 255, 255, 0.2)",
  color: "#41FFFF",
  borderRadius: "4px",
  fontSize: "10px",
  fontWeight: "700",
  textTransform: "uppercase",
};

const recommendationStyle = {
  display: "flex",
  alignItems: "flex-start",
  gap: "8px",
  padding: "8px 0",
  fontSize: "13px",
  color: "#A2A7AF",
  borderBottom: "1px solid rgba(255, 255, 255, 0.05)",
};

export default EmailIntelligenceDashboard;
