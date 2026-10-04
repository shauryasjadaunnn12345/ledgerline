import { useState } from "react";
import { createDispute } from "../api";

function DisputeForm({ onCreated }) {
  const [form, setForm] = useState({
    customer_id: "",
    amount: "",
    description: "",
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const dispute = await createDispute({
        customer_id: form.customer_id,
        amount: parseFloat(form.amount),
        description: form.description,
      });
      onCreated(dispute);
      setForm((f) => ({ ...f, amount: "" }));
    } catch (err) {
      setError(err.response?.data?.detail || "Failed to create dispute.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dispute-form-card">
      <div className="mb-5">
        <p className="eyebrow">New case</p>
        <h2 className="mt-1 text-lg font-semibold tracking-tight text-gray-950">Open an invoice dispute</h2>
        <p className="mt-1 text-sm text-gray-500">Start with the account and amount shown on the invoice.</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Customer ID
          </label>
          <input
            name="customer_id"
            value={form.customer_id}
            onChange={handleChange}
            required
            className="app-input w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm"
            placeholder="customer-123"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Disputed invoice amount ($)</label>
          <input
            name="amount"
            type="number"
            step="0.01"
            min="0"
            value={form.amount}
            onChange={handleChange}
            required
            className="app-input w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm"
            placeholder="89.99"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Customer dispute description</label>
          <textarea
            name="description"
            value={form.description}
            onChange={handleChange}
            rows={3}
            className="app-input w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm"
            placeholder="Describe the disputed invoice charge or unexpected balance"
          />
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={loading}
          className="app-button w-full bg-emerald-700 text-white text-sm font-semibold rounded-lg px-4 py-3 hover:bg-emerald-800 disabled:opacity-50 transition-colors"
        >
          {loading ? "Creating..." : "Open invoice case"}
        </button>
      </form>
    </div>
  );
}

export default DisputeForm;
