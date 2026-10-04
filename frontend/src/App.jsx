import { useState } from "react";
import RoleToggle from "./components/RoleToggle";
import DisputeForm from "./components/DisputeForm";
import StatusTracker from "./components/StatusTracker";
import BillingWorkspace from "./components/BillingWorkspace";

function CaseLookup({ value, onChange, onOpen, label }) {
  const canOpen = Number.isInteger(Number(value)) && Number(value) > 0;
  return (
    <form
      className="case-lookup flex flex-wrap items-end gap-3"
      onSubmit={(event) => {
        event.preventDefault();
        if (canOpen) onOpen(Number(value));
      }}
    >
      <label className="min-w-48 flex-1 text-sm text-gray-700">
        <span className="mb-1.5 block font-medium">{label}</span>
        <input
          className="app-input w-full rounded-lg border border-gray-300 px-3 py-2.5"
          type="number"
          min="1"
          required
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Enter case ID"
        />
      </label>
      <button
        className="app-button rounded-lg bg-gray-900 px-4 py-2.5 text-sm font-semibold text-white hover:bg-gray-800 disabled:opacity-50"
        type="submit"
        disabled={!canOpen}
      >
        Open case
      </button>
    </form>
  );
}

function CaseDetails({ dispute, canReview, onChanged, onNewCase }) {
  return (
    <div className="space-y-5">
      <div className="case-heading flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="eyebrow">Case workspace</p>
          <p className="mt-1 text-xl font-semibold tracking-tight text-gray-950">Invoice case <span className="text-emerald-700">#{dispute.id}</span></p>
        </div>
        {onNewCase && (
          <button className="app-button rounded-lg border border-gray-200 bg-white px-3.5 py-2 text-sm font-semibold text-gray-700 hover:border-gray-300 hover:bg-gray-50" type="button" onClick={onNewCase}>
            Open another case
          </button>
        )}
      </div>
      <StatusTracker disputeId={dispute.id} refreshKey={dispute.refreshKey} />
      <BillingWorkspace
        disputeId={dispute.id}
        submittedBy={canReview ? "reviewer" : "customer"}
        canReview={canReview}
        canSubmitEvidence={!canReview}
        onChanged={onChanged}
      />
    </div>
  );
}

function App() {
  const [role, setRole] = useState("customer");
  const [customerCase, setCustomerCase] = useState(null);
  const [customerLookup, setCustomerLookup] = useState("");
  const [reviewerLookup, setReviewerLookup] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const handleDisputeCreated = (dispute) => {
    setCustomerCase({ id: dispute.id, refreshKey: refreshKey + 1 });
    setRefreshKey((key) => key + 1);
  };

  const handleCustomerOpen = (id) => {
    setCustomerCase({ id, refreshKey: refreshKey + 1 });
    setRefreshKey((key) => key + 1);
  };

  return (
    <div className="app-shell min-h-screen">
      <header className="app-header">
        <div className="app-header-inner mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
          <div className="brand-lockup">
            <span className="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <path d="M7 3.75h7l4.25 4.3v11.2A1.75 1.75 0 0 1 16.5 21h-9A1.75 1.75 0 0 1 5.75 19.25v-13.75A1.75 1.75 0 0 1 7.5 3.75Z" stroke="currentColor" strokeWidth="1.6" />
                <path d="M14 4v4h4M8.5 12h7M8.5 15.5h4.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <div>
              <h1 className="text-base font-bold tracking-tight text-gray-950 sm:text-lg">Ledgerline</h1>
              <p className="text-xs font-medium text-gray-500">Invoice investigation workspace</p>
            </div>
          </div>
          <RoleToggle role={role} onChange={setRole} />
        </div>
      </header>

      <main className="app-main mx-auto max-w-6xl space-y-6 px-4 py-7 sm:px-6 sm:py-10">
        {role === "customer" ? (
          customerCase ? (
            <CaseDetails
              dispute={customerCase}
              canReview={false}
              onChanged={() => setRefreshKey((key) => key + 1)}
              onNewCase={() => setCustomerCase(null)}
            />
          ) : (
            <div className="mx-auto max-w-3xl space-y-5">
              <section className="welcome-panel">
                <p className="eyebrow">Dispute operations</p>
                <h2>Resolve invoice questions with clarity.</h2>
                <p>Bring invoice details, contract terms, and payment history together in one reviewable case.</p>
              </section>
              <DisputeForm onCreated={handleDisputeCreated} />
              <CaseLookup
                label="Or add evidence to an existing invoice case"
                value={customerLookup}
                onChange={setCustomerLookup}
                onOpen={handleCustomerOpen}
              />
            </div>
          )
        ) : (
          <div className="mx-auto max-w-4xl space-y-5">
            <section className="reviewer-welcome">
              <div>
                <p className="eyebrow">Reviewer workspace</p>
                <h2>Review a billing case</h2>
                <p>Open a case to inspect evidence, verify the calculation, and record a decision.</p>
              </div>
              <span aria-hidden="true" className="reviewer-symbol">✓</span>
            </section>
            <CaseLookup
              label="Review invoice case"
              value={reviewerLookup}
              onChange={setReviewerLookup}
              onOpen={setReviewerLookup}
            />
            {Number.isInteger(Number(reviewerLookup)) && Number(reviewerLookup) > 0 && (
              <CaseDetails
                dispute={{ id: Number(reviewerLookup), refreshKey }}
                canReview
                onChanged={() => setRefreshKey((key) => key + 1)}
              />
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
