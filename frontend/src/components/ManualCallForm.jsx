// frontend/src/components/ManualCallForm.jsx
import { useState } from "react";
import api from "../utils/api";

const ManualCallForm = ({ onClose }) => {
  const [form, setForm] = useState({
    contact_name: "",
    email: "",
    phone_number: "",
    company_name: "",
    title: "",
    industry: "",
    company_description: "",
  });

  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const setField = (k, v) => setForm((s) => ({ ...s, [k]: v }));

  const submit = async () => {
    setLoading(true);
    setError("");
    setMsg("");

    try {
      const payload = {
        contact_name: form.contact_name.trim(),
        email: form.email.trim(),
        phone_number: form.phone_number.trim(),
        company_name: form.company_name.trim(),
        title: form.title.trim(),
        industry: form.industry.trim() || null,
        company_description: form.company_description.trim() || null,
      };

      const res = await api.post("/api/manual-call/initiate", payload);
      const d = res?.data || {};

      if (d?.status !== "success") {
        throw new Error(d?.detail || "Manual call initiate failed");
      }

      const callId = d?.call_id;
      if (!callId) throw new Error("call_id missing from response");

      // ✅ Only open the white transcript page
      window.open(`/transcript?call_id=${callId}`, "_blank", "noopener,noreferrer");

      // Close the Manual Call modal immediately (optional but recommended)
      onClose?.();

      setMsg(`Call initiated. lead_id=${d.lead_id}, call_id=${callId}, twilio_started=${String(d.twilio_started)}`);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Failed to initiate call");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay">
      <div className="modal-panel" style={{ width: "min(720px, 100%)" }}>
        <div className="modal-header">
          <div>
            <div className="modal-title">Manual Call</div>
            <div className="modal-subtitle">Create lead + start outbound call</div>
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <button className="icon-btn" onClick={onClose}>✕</button>
          </div>
        </div>

        <div className="card" style={{ padding: 16, display: "grid", gap: 12 }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <Field
              label="Contact Name"
              value={form.contact_name}
              onChange={(v) => setField("contact_name", v)}
            />
            <Field
              label="Email"
              value={form.email}
              onChange={(v) => setField("email", v)}
            />
            <Field
              label="Phone Number"
              value={form.phone_number}
              onChange={(v) => setField("phone_number", v)}
            />
            <Field
              label="Company Name"
              value={form.company_name}
              onChange={(v) => setField("company_name", v)}
            />
            <Field
              label="Title"
              value={form.title}
              onChange={(v) => setField("title", v)}
            />
            <Field
              label="Industry (optional)"
              value={form.industry}
              onChange={(v) => setField("industry", v)}
            />
          </div>

          <div>
            <div className="label">Company Description (optional)</div>
            <textarea
              className="input"
              value={form.company_description}
              onChange={(e) => setField("company_description", e.target.value)}
              rows={4}
              style={{ width: "100%", resize: "vertical" }}
              placeholder="Short company summary (optional)"
            />
          </div>

          {error && <div className="alert-error">{error}</div>}
          {msg && <div className="alert-success">{msg}</div>}

          <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
            <button className="btn-secondary" onClick={onClose} disabled={loading}>
              Cancel
            </button>
            <button className="btn" onClick={submit} disabled={loading}>
              {loading ? "CALLING..." : "CALL LEAD"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const Field = ({ label, value, onChange }) => (
  <div>
    <div className="label">{label}</div>
    <input
      className="input"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={label}
      style={{ width: "100%" }}
    />
  </div>
);

export default ManualCallForm;
