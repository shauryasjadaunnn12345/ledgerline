import { useCallback, useEffect, useState } from "react";
import {
  approveMockAdjustment,
  getBillingEvidence,
  getCaseHistory,
  getReconciliation,
  reconcileBilling,
  reopenCase,
  reviewCase,
  submitBillingEvidence,
} from "../api";

const EVIDENCE_OPTIONS = [
  { value: "invoice_line_item", label: "Invoice line item" },
  { value: "contract_rule", label: "Pricing or contract rule" },
  { value: "usage_event", label: "Usage event" },
  { value: "payment_adjustment", label: "Payment or adjustment" },
];

const EMPTY_FORM = {
  line_id: "",
  description: "",
  quantity: "",
  unit_price: "",
  billed_amount: "",
  allowed_unit_price: "",
  quantity_source: "invoice",
  kind: "payment",
  amount: "",
  reference: "",
};

const FIELD_STYLE = "app-input w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm";
const BUTTON_STYLE = "app-button rounded-lg px-3.5 py-2.5 text-sm font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50";

function money(value) {
  if (value == null) return "Not available";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value));
}

function BillingWorkspace({ disputeId, submittedBy = "customer", canReview = true, canSubmitEvidence = true, onChanged }) {
  const [evidenceType, setEvidenceType] = useState(EVIDENCE_OPTIONS[0].value);
  const [form, setForm] = useState(EMPTY_FORM);
  const [evidence, setEvidence] = useState([]);
  const [reconciliation, setReconciliation] = useState(null);
  const [history, setHistory] = useState(null);
  const [adjustmentAmount, setAdjustmentAmount] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [editedFindings, setEditedFindings] = useState("[]");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const loadCase = useCallback(async () => {
    setLoading(true);
    setError(null);
    const [evidenceResult, reconciliationResult, historyResult] = await Promise.allSettled([
      getBillingEvidence(disputeId),
      getReconciliation(disputeId),
      getCaseHistory(disputeId),
    ]);
    if (evidenceResult.status === "fulfilled") setEvidence(evidenceResult.value);
    else setError(evidenceResult.reason.response?.data?.detail || "Could not load billing evidence.");

    if (reconciliationResult.status === "fulfilled") {
      setReconciliation(reconciliationResult.value);
      setEditedFindings(JSON.stringify(reconciliationResult.value.analysis.findings, null, 2));
      const credit = reconciliationResult.value.analysis.resolution_options.find(
        (option) => option.action === "credit_difference",
      );
      setAdjustmentAmount(credit?.amount || "");
    } else if (reconciliationResult.reason.response?.status === 404) {
      setReconciliation(null);
      setEditedFindings("[]");
      setAdjustmentAmount("");
    } else {
      setError(reconciliationResult.reason.response?.data?.detail || "Could not load the latest reconciliation.");
    }

    if (historyResult.status === "fulfilled") setHistory(historyResult.value);
    else setError(historyResult.reason.response?.data?.detail || "Could not load case history.");
    setLoading(false);
  }, [disputeId]);

  useEffect(() => {
    setEvidence([]);
    setReconciliation(null);
    setHistory(null);
    setError(null);
    loadCase();
  }, [disputeId, loadCase]);

  const updateField = (event) => {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  };

  const toEvidenceData = () => {
    if (evidenceType === "invoice_line_item") {
      return {
        line_id: form.line_id,
        description: form.description,
        quantity: Number(form.quantity),
        unit_price: Number(form.unit_price),
        billed_amount: Number(form.billed_amount),
      };
    }
    if (evidenceType === "contract_rule") {
      return {
        line_id: form.line_id,
        description: form.description,
        allowed_unit_price: Number(form.allowed_unit_price),
        quantity_source: form.quantity_source,
      };
    }
    if (evidenceType === "usage_event") {
      return {
        line_id: form.line_id,
        description: form.description,
        quantity: Number(form.quantity),
      };
    }
    return {
      kind: form.kind,
      amount: Number(form.amount),
      reference: form.reference,
      description: form.description || form.kind.replaceAll("_", " "),
    };
  };

  const handleEvidenceSubmit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await submitBillingEvidence(disputeId, {
        evidence_type: evidenceType,
        data: toEvidenceData(),
        submitted_by: submittedBy,
      });
      setForm(EMPTY_FORM);
      await loadCase();
      onChanged?.();
      setNotice(result.duplicate_ignored
        ? `That invoice line was already recorded as BE-${result.id}; the duplicate was ignored.`
        : "Billing evidence added. Reconcile again if the current conclusion is marked stale.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Billing evidence could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const handleReconcile = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await reconcileBilling(disputeId);
      setReconciliation(result);
      setEditedFindings(JSON.stringify(result.analysis.findings, null, 2));
      const credit = result.analysis.resolution_options.find((option) => option.action === "credit_difference");
      setAdjustmentAmount(credit?.amount || "");
      await loadCase();
      onChanged?.();
      setNotice("Invoice recalculated. The calculation and case analysis were saved separately.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Invoice reconciliation failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleReview = async (action) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      let findings;
      if (action === "edit") {
        findings = JSON.parse(editedFindings);
        if (!Array.isArray(findings)) throw new Error("Edited findings must be a JSON array.");
      }
      await reviewCase(disputeId, {
        action,
        note: reviewNote,
        ...(action === "edit" ? { edited_findings: findings } : {}),
      });
      await loadCase();
      onChanged?.();
      setNotice(`Review action recorded: ${action.replaceAll("_", " ")}.`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || requestError.message || "Review action failed.");
    } finally {
      setBusy(false);
    }
  };

  const handleAdjustment = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await approveMockAdjustment(disputeId, {
        amount: adjustmentAmount,
        reason: "Reviewer-approved invoice adjustment",
        approved_by: submittedBy,
      });
      await loadCase();
      onChanged?.();
      setNotice("Mock adjustment approved and recorded.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Mock adjustment could not be approved.");
    } finally {
      setBusy(false);
    }
  };

  const handleReopen = async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await reopenCase(disputeId, reviewNote || "Reviewer reopened the case");
      await loadCase();
      onChanged?.();
      setNotice("Case reopened. Reconcile it again after reviewing the evidence.");
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Case could not be reopened.");
    } finally {
      setBusy(false);
    }
  };

  const renderField = (name, label, type = "text", required = true) => (
    <label key={name} className="block text-sm text-gray-700">
      <span className="mb-1 block font-medium">{label}</span>
      <input
        className={FIELD_STYLE}
        name={name}
        type={type}
        value={form[name]}
        onChange={updateField}
        required={required}
        min={type === "number" ? "0" : undefined}
        step={name.includes("amount") || name.includes("price") ? "0.01" : type === "number" ? "any" : undefined}
      />
    </label>
  );

  const stale = Boolean(reconciliation?.is_stale);
  const canDecideFindings = Boolean(reconciliation?.calculation.complete && !stale);
  const approvedAdjustment = history?.adjustments?.[0];
  const hasVerifiedOvercharge = reconciliation
    && reconciliation.calculation.complete
    && Number(reconciliation.calculation.invoice_total) > Number(reconciliation.calculation.recalculated_total);
  const caseEvents = history
    ? [
        ...(history.reviewer_actions || []).map((item) => ({ kind: "review", label: item.action.replaceAll("_", " "), detail: item.edited_findings ? `${item.note || ""} ${JSON.stringify(item.edited_findings)}`.trim() : item.note, at: item.created_at })),
        ...(history.calculations || []).map((item) => ({ kind: "calculation", label: "Invoice recalculated", detail: `Invoice ${money(item.result.invoice_total)}; recalculated ${money(item.result.recalculated_total)}`, at: item.created_at })),
        ...(history.analyses || []).map((item) => ({ kind: "analysis", label: "Case analysis saved", detail: item.summary, at: item.created_at })),
        ...(history.adjustments || []).map((item) => ({ kind: "adjustment", label: `Mock adjustment approved: ${money(item.amount_cents / 100)}`, detail: item.reason, at: item.created_at })),
      ].sort((left, right) => new Date(right.at) - new Date(left.at))
    : [];

  if (loading && !history && evidence.length === 0) {
    return <section className="border-y border-gray-200 py-6 text-sm text-gray-500">Loading billing case…</section>;
  }

  return (
    <section className="workspace-card space-y-6" aria-label="Invoice investigation">
      <div className="workspace-heading flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Evidence &amp; resolution</p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-gray-950">Invoice investigation</h2>
          <p className="mt-1 text-sm text-gray-500">Review billing records and verify the invoice calculation.</p>
        </div>
        <button
          className={`${BUTTON_STYLE} bg-emerald-700 text-white shadow-sm hover:bg-emerald-800`}
          type="button"
          disabled={busy}
          onClick={handleReconcile}
        >
          {busy ? "Working…" : "Recalculate invoice"}
        </button>
      </div>

      {stale && (
        <div role="alert" className="border-l-4 border-amber-500 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          New evidence was added after this conclusion. Recalculate before reviewer actions.
        </div>
      )}
      {error && <p role="alert" className="feedback-message feedback-error text-sm">{error}</p>}
      {notice && <p role="status" className="feedback-message feedback-success text-sm">{notice}</p>}

      {canSubmitEvidence && <div>
        <h3 className="section-heading mb-3">Add billing evidence</h3>
        <form onSubmit={handleEvidenceSubmit} className="space-y-3">
          <label className="block max-w-sm text-sm text-gray-700">
            <span className="mb-1 block font-medium">Evidence type</span>
            <select className={FIELD_STYLE} value={evidenceType} onChange={(event) => setEvidenceType(event.target.value)}>
              {EVIDENCE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>

          {evidenceType === "invoice_line_item" && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {renderField("line_id", "Invoice line ID")}
              {renderField("description", "Line description")}
              {renderField("quantity", "Billed quantity", "number")}
              {renderField("unit_price", "Invoice unit price ($)", "number")}
              {renderField("billed_amount", "Billed amount ($)", "number")}
            </div>
          )}
          {evidenceType === "contract_rule" && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {renderField("line_id", "Matching invoice line ID")}
              {renderField("description", "Contract rule")}
              {renderField("allowed_unit_price", "Allowed unit price ($)", "number")}
              <label className="block text-sm text-gray-700">
                <span className="mb-1 block font-medium">Quantity basis</span>
                <select className={FIELD_STYLE} name="quantity_source" value={form.quantity_source} onChange={updateField}>
                  <option value="invoice">Invoice quantity</option>
                  <option value="usage">Usage events</option>
                </select>
              </label>
            </div>
          )}
          {evidenceType === "usage_event" && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {renderField("line_id", "Matching invoice line ID")}
              {renderField("description", "Usage event")}
              {renderField("quantity", "Recorded quantity", "number")}
            </div>
          )}
          {evidenceType === "payment_adjustment" && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <label className="block text-sm text-gray-700">
                <span className="mb-1 block font-medium">Record type</span>
                <select className={FIELD_STYLE} name="kind" value={form.kind} onChange={updateField}>
                  <option value="payment">Payment</option>
                  <option value="credit">Credit</option>
                  <option value="debit_adjustment">Debit adjustment</option>
                </select>
              </label>
              {renderField("amount", "Amount ($)", "number")}
              {renderField("reference", "Reference")}
              {renderField("description", "Description", "text", false)}
            </div>
          )}
          <button className={`${BUTTON_STYLE} border border-gray-300 bg-white text-gray-800 hover:bg-gray-50`} type="submit" disabled={busy}>
            Add evidence
          </button>
        </form>
      </div>}

      <div>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">Submitted billing evidence</h3>
        {evidence.length === 0 ? (
          <p className="text-sm text-gray-500">No structured billing evidence yet.</p>
        ) : (
          <ul className="evidence-list divide-y divide-gray-200">
            {(() => {
              const seenLineIds = new Set();
              return evidence.map((item) => {
                const isInvoiceLine = item.evidence_type === "invoice_line_item";
                const lineId = item.payload.line_id;
                const repeatedLineId = isInvoiceLine && seenLineIds.has(lineId);
                if (isInvoiceLine) seenLineIds.add(lineId);
                return (
                  <li key={item.id} className="flex flex-wrap justify-between gap-x-4 gap-y-1.5 px-4 py-3 text-sm">
                    <span className="font-semibold text-gray-800"><span className="evidence-id">BE-{item.id}</span>{EVIDENCE_OPTIONS.find((option) => option.value === item.evidence_type)?.label}</span>
                    <span className="text-gray-500">{item.payload.description || item.payload.reference || lineId || item.payload.kind}{repeatedLineId ? " · Repeated line ID; counted once" : ""}</span>
                  </li>
                );
              });
            })()}
          </ul>
        )}
      </div>

      {reconciliation && (
        <div className="space-y-5">
          <div>
            <h3 className="section-heading mb-3">Invoice totals</h3>
            <dl className="metric-grid grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              <div className="metric-card"><dt>Original total</dt><dd>{money(reconciliation.calculation.invoice_total)}</dd></div>
              <div className="metric-card"><dt>Invoice line math</dt><dd>{money(reconciliation.calculation.invoice_extension_total)}</dd><dd className="metric-caption">Quantity × unit price</dd></div>
              <div className="metric-card metric-highlight"><dt>Recalculated total</dt><dd>{money(reconciliation.calculation.recalculated_total)}</dd></div>
              <div className="metric-card"><dt>Original balance</dt><dd>{money(reconciliation.calculation.original_balance)}</dd></div>
              <div className="metric-card"><dt>Recalculated balance</dt><dd>{money(reconciliation.calculation.recalculated_balance)}</dd></div>
            </dl>
            <div className="mt-3 overflow-x-auto">
              <table className="invoice-table w-full min-w-[560px] border-collapse text-left text-sm">
                <thead><tr className="border-b border-gray-200 text-xs uppercase text-gray-500"><th className="py-2 pr-3">Line</th><th className="py-2 pr-3">Billed</th><th className="py-2 pr-3">Invoice line math</th><th className="py-2 pr-3">Contract recalculated</th><th className="py-2">Sources</th></tr></thead>
                <tbody>
                  {reconciliation.calculation.lines.map((line) => (
                    <tr key={`${line.line_id}-${line.citations[0]}`} className="border-b border-gray-100">
                      <td className="py-2 pr-3 text-gray-800">{line.description}<span className="block text-xs text-gray-500">{line.line_id} · {line.billed_quantity} × {money(line.unit_price)} per unit</span></td>
                      <td className="py-2 pr-3">{money(line.billed_amount)}</td>
                      <td className="py-2 pr-3">{money(line.invoice_calculated_amount)}<span className="block text-xs text-gray-500">Billed variance: {money(line.invoice_amount_variance)}</span></td>
                      <td className="py-2 pr-3">{money(line.expected_amount)}</td>
                      <td className="py-2 text-xs text-gray-600">{line.citations.join(", ")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="analysis-panel">
            <h3 className="section-heading mb-2">Case analysis</h3>
            <p className="text-sm leading-6 text-gray-700">{reconciliation.analysis.summary}</p>
            <div className="ai-panel mt-4">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <h4 className="text-sm font-semibold text-gray-900">AI interpretation</h4>
                <span className={`ai-status ${reconciliation.analysis.agent_interpretation ? "ai-status-ready" : "ai-status-muted"}`}>
                  {reconciliation.analysis.agent_status || "unavailable"}
                </span>
              </div>
              {reconciliation.analysis.agent_interpretation ? (
                <>
                  {reconciliation.analysis.agent_status === "cached" && (
                    <p className="feedback-message feedback-warning mt-2 text-xs">
                      OpenRouter did not return a new interpretation. Showing the last successful result for unchanged evidence.
                    </p>
                  )}
                  <p className="mt-2 text-sm leading-6 text-gray-700">{reconciliation.analysis.agent_interpretation.summary}</p>
                  <p className="mt-1 text-xs text-gray-500">Sources: {reconciliation.analysis.agent_interpretation.summary_citations.join(", ")}</p>
                  <ul className="mt-2 space-y-2 text-sm text-gray-700">
                    {reconciliation.analysis.agent_interpretation.possible_causes.map((cause, index) => (
                      <li key={`${cause.category}-${index}`}>
                        <span className="font-medium">{cause.category.replaceAll("_", " ")}: </span>{cause.explanation}
                        <span className="mt-1 block text-xs text-gray-500">Sources: {cause.citations.join(", ")}</span>
                      </li>
                    ))}
                  </ul>
                  {reconciliation.analysis.agent_interpretation.follow_up_questions.length > 0 && (
                    <ul className="mt-2 list-disc pl-5 text-sm text-gray-700">
                      {reconciliation.analysis.agent_interpretation.follow_up_questions.map((question, index) => <li key={index}>{question}</li>)}
                    </ul>
                  )}
                </>
              ) : (
                <p className="mt-1 text-sm text-gray-600">Status: {reconciliation.analysis.agent_status || "unavailable"}</p>
              )}
            </div>
            <ul className="finding-list mt-4 space-y-2">
              {reconciliation.analysis.findings.map((finding, index) => (
                <li key={`${finding.kind}-${index}`} className="rounded-lg border border-gray-100 bg-white px-3.5 py-3 text-sm">
                  <p className="text-gray-800">{finding.text}</p>
                  <p className="mt-1 text-xs text-gray-500">Sources: {finding.citations.length ? finding.citations.join(", ") : "None supplied"}</p>
                </li>
              ))}
            </ul>
            {reconciliation.analysis.missing_evidence.length > 0 && (
              <div className="mt-4 border-l-2 border-amber-500 pl-3">
                <h4 className="text-sm font-semibold text-amber-900">Missing evidence</h4>
                <ul className="mt-1 space-y-1 text-sm text-amber-900">
                  {reconciliation.analysis.missing_evidence.map((item, index) => <li key={`${item.item}-${index}`}>{item.reason}</li>)}
                </ul>
              </div>
            )}
            <div className="mt-4">
              <h4 className="text-sm font-semibold text-gray-800">Resolution options</h4>
              <ul className="mt-1 space-y-1 text-sm text-gray-700">
                {reconciliation.analysis.resolution_options.map((option) => <li key={option.action}>{option.label}{option.amount != null ? ` (${money(option.amount)})` : ""}</li>)}
              </ul>
            </div>
          </div>

          {canReview && (
            <div className="review-panel">
              <h3 className="section-heading">Reviewer actions</h3>
              <label className="mt-3 block text-sm text-gray-700">
                <span className="mb-1 block font-medium">Reviewer note</span>
                <textarea className={FIELD_STYLE} rows={2} value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} />
              </label>
              <label className="mt-3 block text-sm text-gray-700">
                <span className="mb-1 block font-medium">Findings to edit</span>
                <textarea className={`${FIELD_STYLE} font-mono text-xs`} rows={5} value={editedFindings} onChange={(event) => setEditedFindings(event.target.value)} />
              </label>
              <div className="mt-3 flex flex-wrap gap-2">
                <button className={`${BUTTON_STYLE} bg-emerald-700 text-white hover:bg-emerald-800`} type="button" disabled={busy || !canDecideFindings} onClick={() => handleReview("accept")}>Accept findings</button>
                <button className={`${BUTTON_STYLE} border border-gray-300 bg-white text-gray-800 hover:bg-gray-50`} type="button" disabled={busy || !canDecideFindings} onClick={() => handleReview("edit")}>Save edited findings</button>
                <button className={`${BUTTON_STYLE} border border-red-300 bg-white text-red-800 hover:bg-red-50`} type="button" disabled={busy || !canDecideFindings} onClick={() => handleReview("reject")}>Reject findings</button>
                <button className={`${BUTTON_STYLE} border border-gray-300 bg-white text-gray-800 hover:bg-gray-50`} type="button" disabled={busy} onClick={() => handleReview("request_information")}>Request information</button>
                <button className={`${BUTTON_STYLE} border border-gray-300 bg-white text-gray-800 hover:bg-gray-50`} type="button" disabled={busy} onClick={handleReopen}>Reopen case</button>
              </div>
              {!reconciliation.calculation.complete && (
                <p className="mt-2 text-sm text-amber-900">
                  Add the missing invoice and pricing or usage evidence before accepting, editing, or rejecting findings.
                </p>
              )}
              {approvedAdjustment ? (
                <p className="mt-4 text-sm text-emerald-800">Mock adjustment already approved: {money(approvedAdjustment.amount_cents / 100)}.</p>
              ) : hasVerifiedOvercharge ? (
                <div className="mt-4 flex flex-wrap items-end gap-2">
                  <label className="block text-sm text-gray-700">
                    <span className="mb-1 block font-medium">Mock credit ($)</span>
                    <input className={FIELD_STYLE} type="number" min="0.01" step="0.01" max={reconciliation.calculation.invoice_total - reconciliation.calculation.recalculated_total} value={adjustmentAmount} onChange={(event) => setAdjustmentAmount(event.target.value)} />
                  </label>
                  <button className={`${BUTTON_STYLE} bg-gray-900 text-white hover:bg-gray-800`} type="button" disabled={busy || stale || !adjustmentAmount} onClick={handleAdjustment}>Approve mock adjustment</button>
                </div>
              ) : (
                <p className="mt-4 text-sm text-gray-600">No verified overcharge is available for a mock credit.</p>
              )}
            </div>
          )}
        </div>
      )}

      <details className="border-t border-gray-200 pt-3">
        <summary className="cursor-pointer text-sm font-semibold text-gray-800">Case history ({caseEvents.length})</summary>
        {caseEvents.length === 0 ? <p className="mt-3 text-sm text-gray-500">No decisions or reviewer actions recorded.</p> : (
          <ol className="mt-3 divide-y divide-gray-100">
            {caseEvents.map((event, index) => (
              <li key={`${event.kind}-${event.at}-${index}`} className="py-2">
                <div className="flex flex-wrap justify-between gap-x-3 text-sm"><span className="font-medium text-gray-800">{event.label}</span><time className="text-xs text-gray-500">{new Date(event.at).toLocaleString()}</time></div>
                {event.detail && <p className="mt-1 text-sm text-gray-600">{event.detail}</p>}
              </li>
            ))}
          </ol>
        )}
      </details>
    </section>
  );
}

export default BillingWorkspace;