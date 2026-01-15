// frontend/src/components/LoginPage.jsx
import { useState } from "react";
import { authAPI } from "../utils/api";

/**
 * LoginPage - Handles user authentication
 * Stores JWT token in sessionStorage on successful login
 */
const LoginPage = ({ onLoginSuccess }) => {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const response = await authAPI.login(email.trim(), password);

      if (response.data && response.data.access_token) {
        onLoginSuccess?.();
      } else {
        setError("Login failed: No token received");
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail) {
        setError(detail);
      } else if (err?.message) {
        setError(err.message);
      } else {
        setError("Login failed. Please check your credentials.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="grid-background" />

      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "20px",
        }}
      >
        <div
          style={{
            background: "linear-gradient(135deg, #0A0D10 0%, #12151A 100%)",
            borderRadius: "16px",
            border: "1px solid rgba(147, 51, 234, 0.3)",
            padding: "40px",
            width: "100%",
            maxWidth: "420px",
            boxShadow: "0 0 60px rgba(147, 51, 234, 0.15)",
          }}
        >
          {/* Logo */}
          <div style={{ textAlign: "center", marginBottom: "32px" }}>
            <h1
              style={{
                fontSize: "28px",
                fontWeight: "800",
                letterSpacing: "0.1em",
                margin: "0 0 8px 0",
              }}
            >
              <span style={{ color: "#F0F3F8" }}>ALGONOX</span>{" "}
              <span style={{ color: "#9333EA" }}>AADOS</span>
            </h1>
            <p
              style={{
                color: "#6B7280",
                fontSize: "12px",
                letterSpacing: "0.15em",
                textTransform: "uppercase",
                margin: 0,
              }}
            >
              AI Agents Driven Outbound Sales
            </p>
          </div>

          {/* Login Form */}
          <form onSubmit={handleSubmit}>
            <div style={{ marginBottom: "20px" }}>
              <label
                style={{
                  display: "block",
                  color: "#9CA3AF",
                  fontSize: "11px",
                  fontWeight: "700",
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  marginBottom: "8px",
                }}
              >
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                autoFocus
                style={{
                  width: "100%",
                  padding: "12px 16px",
                  background: "rgba(255, 255, 255, 0.05)",
                  border: "1px solid rgba(147, 51, 234, 0.3)",
                  borderRadius: "8px",
                  color: "#F0F3F8",
                  fontSize: "14px",
                  outline: "none",
                  transition: "border-color 0.2s",
                  boxSizing: "border-box",
                }}
                placeholder="admin@example.com"
                onFocus={(e) => (e.target.style.borderColor = "#9333EA")}
                onBlur={(e) => (e.target.style.borderColor = "rgba(147, 51, 234, 0.3)")}
              />
            </div>

            <div style={{ marginBottom: "24px" }}>
              <label
                style={{
                  display: "block",
                  color: "#9CA3AF",
                  fontSize: "11px",
                  fontWeight: "700",
                  letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  marginBottom: "8px",
                }}
              >
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                style={{
                  width: "100%",
                  padding: "12px 16px",
                  background: "rgba(255, 255, 255, 0.05)",
                  border: "1px solid rgba(147, 51, 234, 0.3)",
                  borderRadius: "8px",
                  color: "#F0F3F8",
                  fontSize: "14px",
                  outline: "none",
                  transition: "border-color 0.2s",
                  boxSizing: "border-box",
                }}
                placeholder="Enter your password"
                onFocus={(e) => (e.target.style.borderColor = "#9333EA")}
                onBlur={(e) => (e.target.style.borderColor = "rgba(147, 51, 234, 0.3)")}
              />
            </div>

            {error && (
              <div
                style={{
                  padding: "12px 16px",
                  background: "rgba(239, 68, 68, 0.15)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  borderRadius: "8px",
                  color: "#F87171",
                  fontSize: "13px",
                  marginBottom: "20px",
                  textAlign: "center",
                }}
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: "100%",
                padding: "14px 20px",
                background: loading
                  ? "rgba(147, 51, 234, 0.3)"
                  : "linear-gradient(135deg, #9333EA 0%, #7C3AED 100%)",
                border: "none",
                borderRadius: "8px",
                color: "#FFFFFF",
                fontSize: "13px",
                fontWeight: "700",
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                cursor: loading ? "not-allowed" : "pointer",
                transition: "all 0.2s",
                boxShadow: loading ? "none" : "0 4px 20px rgba(147, 51, 234, 0.4)",
              }}
              onMouseEnter={(e) => {
                if (!loading) {
                  e.target.style.transform = "translateY(-1px)";
                  e.target.style.boxShadow = "0 6px 25px rgba(147, 51, 234, 0.5)";
                }
              }}
              onMouseLeave={(e) => {
                e.target.style.transform = "translateY(0)";
                e.target.style.boxShadow = loading ? "none" : "0 4px 20px rgba(147, 51, 234, 0.4)";
              }}
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </form>

          {/* Footer */}
          <div
            style={{
              marginTop: "32px",
              paddingTop: "20px",
              borderTop: "1px solid rgba(147, 51, 234, 0.15)",
              textAlign: "center",
            }}
          >
            <p
              style={{
                color: "#4B5563",
                fontSize: "11px",
                margin: 0,
              }}
            >
              Powered by Algonox AI Platform
            </p>
          </div>
        </div>
      </div>
    </>
  );
};

export default LoginPage;
