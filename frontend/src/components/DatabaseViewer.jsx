import { useEffect, useMemo, useState } from "react";
import { Database, X, RefreshCw, ChevronLeft, ChevronRight } from "lucide-react";
import api from "../utils/api";

const DatabaseViewer = ({ onClose }) => {
  const [tables, setTables] = useState([]);
  const [activeTable, setActiveTable] = useState("");
  const [columns, setColumns] = useState([]);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);

  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);

  const [loadingTables, setLoadingTables] = useState(false);
  const [loadingTable, setLoadingTable] = useState(false);
  const [error, setError] = useState("");

  const [quickStats, setQuickStats] = useState({
    leads: 0,
    calls: 0,
    emails: 0,
    dataPackets: 0,
  });

  const canPrev = offset > 0;
  const canNext = offset + limit < total;

  const visibleRows = useMemo(
    () => (Array.isArray(rows) ? rows : []),
    [rows]
  );

  const fetchTables = async () => {
    setLoadingTables(true);
    setError("");
    try {
      const res = await api.get("/api/database/tables");
      const list = res?.data?.tables || [];
      setTables(Array.isArray(list) ? list : []);

      if (!activeTable && list?.length) {
        setActiveTable(list[0]);
        setOffset(0);
      }
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Failed to load tables");
      setTables([]);
    } finally {
      setLoadingTables(false);
    }
  };

  const fetchQuickStats = async () => {
    try {
      const res = await api.get("/api/reports/dashboard");
      const d = res?.data || {};
      setQuickStats({
        leads: d?.leads?.total ?? 0,
        calls: d?.calls?.total ?? 0,
        emails: d?.emails?.sent ?? d?.emails?.total ?? 0,
        dataPackets: d?.leads?.data_packets_created ?? 0,
      });
    } catch {}
  };

  const fetchTableRows = async (tableName, opts = {}) => {
    if (!tableName) return;

    const nextLimit = opts.limit ?? limit;
    const nextOffset = opts.offset ?? offset;

    setLoadingTable(true);
    setError("");

    try {
      const res = await api.get(`/api/database/table/${tableName}`, {
        params: { limit: nextLimit, offset: nextOffset },
      });

      const payload = res?.data || {};
      const incomingRows = payload.rows ?? payload.data ?? [];
      const incomingCols = payload.columns ?? [];

      setColumns(Array.isArray(incomingCols) ? incomingCols : []);
      setRows(Array.isArray(incomingRows) ? incomingRows : []);
      setTotal(Number.isFinite(payload.total) ? payload.total : incomingRows.length || 0);
    } catch (e) {
      setError(e?.response?.data?.detail || e?.message || "Failed to load table");
      setColumns([]);
      setRows([]);
      setTotal(0);
    } finally {
      setLoadingTable(false);
    }
  };

  const refreshAll = async () => {
    await Promise.allSettled([fetchTables(), fetchQuickStats()]);
    if (activeTable) {
      await fetchTableRows(activeTable, { offset: 0 });
      setOffset(0);
    }
  };

  useEffect(() => {
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!activeTable) return;
    setOffset(0);
    fetchTableRows(activeTable, { offset: 0 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeTable]);

  useEffect(() => {
    if (!activeTable) return;
    fetchTableRows(activeTable, { offset, limit });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [offset, limit]);

  return (
    <div className="modal-overlay">
      <div className="modal-panel" style={{ width: "min(1200px,100%)", maxHeight: "94vh", display: "flex", flexDirection: "column" }}>

        {/* HEADER */}
        <div className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Database size={24} color="#9333EA" />
            <div>
              <div className="modal-title">Database Viewer</div>
              <div className="modal-subtitle">
                View actual table rows (SELECT * …)
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn" onClick={refreshAll}>
              <RefreshCw size={14} /> REFRESH
            </button>

            <button className="icon-btn" onClick={onClose}>
              ✕
            </button>
          </div>
        </div>

        {/* BODY */}
        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "300px 1fr", gap: 16 }}>

          {/* LEFT SIDEBAR */}
          <div className="card" style={{ overflow: "auto" }}>
            <div className="label">Tables ({tables.length})</div>

            {loadingTables ? (
              <div className="panel-body">Loading tables…</div>
            ) : (
              <div style={{ display: "grid", gap: 8 }}>
                {tables.map((t) => {
                  const active = t === activeTable;
                  return (
                    <button
                      key={t}
                      className="btn-secondary"
                      style={{
                        textAlign: "left",
                        background: active ? "rgba(147,51,234,0.12)" : "transparent",
                        borderColor: active ? "var(--accent-purple)" : "rgba(147,51,234,0.25)",
                        color: active ? "var(--accent-purple)" : "var(--text-bright)",
                        fontWeight: 700,
                      }}
                      onClick={() => setActiveTable(t)}
                    >
                      {String(t).toUpperCase()}
                    </button>
                  );
                })}
              </div>
            )}

            <div style={{ height: 16 }} />

            {/* QUICK STATS */}
            <div className="card">
              <div className="label">Quick Stats</div>
              <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: 13 }}>
                Leads: {quickStats.leads}
                <br />
                Calls: {quickStats.calls}
                <br />
                Emails: {quickStats.emails}
                <br />
                Data Packets: {quickStats.dataPackets}
              </div>
            </div>

            {error && <div className="alert-error">{error}</div>}
          </div>

          {/* RIGHT CONTENT */}
          <div className="card" style={{ display: "flex", flexDirection: "column" }}>
            {!activeTable ? (
              <div className="panel-body">Select a table from the left.</div>
            ) : (
              <>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <div className="panel-title">TABLE: {activeTable}</div>

                  <div style={{ display: "flex", gap: 8 }}>
                    <select
                      className="input"
                      value={limit}
                      onChange={(e) => {
                        setOffset(0);
                        setLimit(Number(e.target.value));
                      }}
                      style={{ width: 120 }}
                    >
                      {[25, 50, 100, 200].map((n) => (
                        <option key={n} value={n}>{n} / page</option>
                      ))}
                    </select>

                    <button className="btn-secondary" disabled={!canPrev} onClick={() => setOffset(o => Math.max(0, o - limit))}>
                      <ChevronLeft size={14} /> Prev
                    </button>

                    <button className="btn-secondary" disabled={!canNext} onClick={() => setOffset(o => o + limit)}>
                      Next <ChevronRight size={14} />
                    </button>
                  </div>
                </div>

                <div style={{ height: 10 }} />

                <div className="table-wrap" style={{ flex: 1 }}>
                  <table className="table">
                    <thead>
                      <tr>
                        {columns.map(c => <th key={c}>{c}</th>)}
                      </tr>
                    </thead>

                    <tbody>
                      {visibleRows.length === 0 ? (
                        <tr>
                          <td colSpan={columns.length}>No rows in table.</td>
                        </tr>
                      ) : (
                        visibleRows.map((r, i) => (
                          <tr key={i}>
                            {columns.map(c => (
                              <td key={c}>
                                {r?.[c] == null ? "" : String(r[c])}
                              </td>
                            ))}
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default DatabaseViewer;
