// frontend/src/components/ManualCallForm.jsx
import { useEffect, useMemo, useState } from "react";
import { manualCallAPI, leadsAPI } from "../utils/api";

const ManualCallForm = ({ onClose }) => {
  const [formData, setFormData] = useState({
    contact_name: "",
    email: "",
    phone_number: "",
    company_name: "",
    title: "",
    industry: "",
    company_description: "",
  });

  const [createdLeadId, setCreatedLeadId] = useState(null);
  const [loadingCreate, setLoadingCreate] = useState(false);
  const [loadingCall, setLoadingCall] = useState(false);
  const [error, setError] = useState("");

  const normalizePhone = (p) => (p || "").trim().replace(/\s+/g, "");
  const normalizeEmail = (e) => (e || "").trim().toLowerCase();

  const isEmailOk = (email) => {
    const e = normalizeEmail(email);
    return e.includes("@") && e.split("@")?.[1]?.includes(".");
  };

  const canCreate = useMemo(() => {
    return Boolean(
      formData.contact_name.trim() &&
      isEmailOk(formData.email) &&
      normalizePhone(formData.phone_number) &&
      formData.company_name.trim() &&
      formData.title.trim()
    );
  }, [formData]);

  const openTranscriptTab = (callId, leadId) => {
    sessionStorage.setItem("aados_last_call_id", String(callId));
    if (leadId) sessionStorage.setItem("aados_last_lead_id", String(leadId));
    window.open(`/transcript?call_id=${encodeURIComponent(callId)}`, "_blank");
  };

  const payloadFromForm = () => ({
    contact_name: formData.contact_name.trim(),
    email: normalizeEmail(formData.email),
    phone_number: normalizePhone(formData.phone_number),
    company_name: formData.company_name.trim(),
    title: formData.title.trim(),
    industry: formData.industry.trim() || null,
    company_description: formData.company_description.trim() || null,
  });

  const handleCreateLead = async () => {
    setError("");

    if (!canCreate) {
      setError("Please fill required fields: Name, Email, Phone, Company, Role/Title.");
      return;
    }

    setLoadingCreate(true);
    try {
      const res = await leadsAPI.createManual(payloadFromForm());
      const lead = res?.data?.lead;

      if (lead?.id) setCreatedLeadId(lead.id);
      else setError("Lead created but response shape unexpected.");
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "Failed to create lead");
    } finally {
      setLoadingCreate(false);
    }
  };

  const handleCallLead = async () => {
    setError("");

    if (!canCreate) {
      setError("Please fill required fields before calling.");
      return;
    }

    setLoadingCall(true);
    try {
      const res = await manualCallAPI.initiate({
        ...payloadFromForm(),
        lead_id: createdLeadId || undefined,
      });

      const data = res?.data || {};

      if (data?.status !== "success" || !data?.call_id) {
        setError(data?.detail || data?.twilio_error || "Call initiation failed");
        return;
      }

      if (data?.lead_id && !createdLeadId) setCreatedLeadId(data.lead_id);

      openTranscriptTab(data.call_id, data.lead_id);
    } catch (err) {
      setError(err?.response?.data?.detail || err?.message || "Failed to initiate call");
    } finally {
      setLoadingCall(false);
    }
  };

  useEffect(() => {
    setCreatedLeadId(null);
  }, [normalizeEmail(formData.email)]);

  return (
    <div className="modal-overlay">
      <div className="modal-panel">

        {/* HEADER */}
        <div className="modal-header">
          <div>
            <div className="modal-title">Create Lead (Manual) / Call Lead</div>
            <div className="modal-subtitle">
              Create lead → call → view transcript
            </div>

            <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text-mid)" }}>
              {createdLeadId
                ? `Lead selected: #${createdLeadId}`
                : "No lead selected yet (Create Lead or Call Lead will create it)"}
            </div>
          </div>

          <button className="icon-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        {/* ERRORS */}
        {error && <div className="alert-error">{error}</div>}

        {/* FORM */}
        <div className="form-grid-2">
          <Field
            label="Name *"
            value={formData.contact_name}
            onChange={(v) => setFormData({ ...formData, contact_name: v })}
            requiredMsg={!formData.contact_name.trim() && "Name is required"}
            placeholder="e.g. Vaishnavi M"
          />

          <Field
            label="Email *"
            value={formData.email}
            onChange={(v) => setFormData({ ...formData, email: v })}
            requiredMsg={!isEmailOk(formData.email) && "Email is required"}
            placeholder="e.g. user@company.com"
          />
        </div>

        <div className="form-grid-2">
          <Field
            label="Phone *"
            value={formData.phone_number}
            onChange={(v) => setFormData({ ...formData, phone_number: v })}
            requiredMsg={!normalizePhone(formData.phone_number) && "Phone number is required"}
            placeholder="e.g. +91XXXXXXXXXX"
          />

          <Field
            label="Company *"
            value={formData.company_name}
            onChange={(v) => setFormData({ ...formData, company_name: v })}
            requiredMsg={!formData.company_name.trim() && "Company is required"}
            placeholder="e.g. ABC"
          />
        </div>

        <div className="form-grid-2">
          <Field
            label="Role/Title *"
            value={formData.title}
            onChange={(v) => setFormData({ ...formData, title: v })}
            requiredMsg={!formData.title.trim() && "Role/Title is required"}
            placeholder="e.g. Head of Sales"
          />

          <Field
            label="Industry (optional)"
            value={formData.industry}
            onChange={(v) => setFormData({ ...formData, industry: v })}
            placeholder="e.g. SaaS"
          />
        </div>

        <Field
          label="Company description (optional for now)"
          textarea
          value={formData.company_description}
          onChange={(v) => setFormData({ ...formData, company_description: v })}
          placeholder="If empty, backend will populate a generic description…"
        />

        {/* BUTTONS */}
        <div className="btn-row">
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>

          <button
            className="btn-primary"
            onClick={handleCreateLead}
            disabled={loadingCreate || !canCreate}
          >
            {loadingCreate ? "Creating..." :
              createdLeadId ? "Update / Recreate Lead" : "Create Lead"}
          </button>

          <button
            className="btn-call"
            onClick={handleCallLead}
            disabled={loadingCall || !canCreate}
          >
            {loadingCall ? "Calling..." : "Call Lead (opens transcript tab)"}
          </button>
        </div>
      </div>
    </div>
  );
};

const Field = ({ label, value, onChange, placeholder, requiredMsg, textarea }) => (
  <div>
    <label className="label">{label}</label>

    {textarea ? (
      <textarea
        className="textarea"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    ) : (
      <input
        className="input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
    )}

    {requiredMsg && <div className="req">{requiredMsg}</div>}
  </div>
);

export default ManualCallForm;
