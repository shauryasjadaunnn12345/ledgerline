import { useEffect, useState } from "react";
import { getDisputeStatus } from "../api";

const POLL_INTERVAL_MS = 4000;

const STATUS_LABELS = {
  open: "Open",
  resolved: "Resolved",
  pending_review: "Pending Human Review",
  awaiting_information: "Awaiting Information",
  reopened: "Reopened",
  reviewed: "Reviewed",
  rejected: "Rejected",
  adjusted: "Adjustment Approved",
};

const STATUS_STYLES = {
  open: "bg-gray-100 text-gray-700",
  resolved: "bg-emerald-50 text-emerald-800",
  pending_review: "bg-amber-50 text-amber-800",
  awaiting_information: "bg-orange-50 text-orange-800",
  reopened: "bg-sky-50 text-sky-800",
  reviewed: "bg-emerald-50 text-emerald-800",
  rejected: "bg-rose-50 text-rose-800",
  adjusted: "bg-emerald-50 text-emerald-800",
};

function StatusTracker({ disputeId, refreshKey }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!disputeId) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const data = await getDisputeStatus(disputeId);
        if (!cancelled) {
          setStatus(data);
          setError(null);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.response?.data?.detail || "Could not fetch status.");
        }
      }
    };

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [disputeId, refreshKey]);

  if (!disputeId) return null;

  return (
    <div className="status-card">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Case overview</p>
          <h2 className="mt-1 text-base font-semibold text-gray-950">Invoice case status</h2>
        </div>
        <span className="status-live"><span />Live</span>
      </div>
      {error && <p className="mb-2 text-sm text-red-600">{error}</p>}
      {status ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-sm font-medium text-gray-600">Dispute <strong className="font-semibold text-gray-900">#{status.dispute_id}</strong></span>
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-sm text-gray-500">
              <strong className="font-semibold text-gray-900">{status.billing_evidence_count}</strong> billing records
            </span>
            <span
              className={`rounded-full px-3 py-1.5 text-xs font-semibold ${
                STATUS_STYLES[status.status] || "bg-gray-100 text-gray-700"
              }`}
            >
              {STATUS_LABELS[status.status] || status.status}
            </span>
          </div>
        </div>
      ) : (
        <p className="text-sm text-gray-500">Loading case status…</p>
      )}
    </div>
  );
}

export default StatusTracker;
