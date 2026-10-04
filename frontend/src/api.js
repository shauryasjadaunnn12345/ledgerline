import axios from "axios";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const client = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

export async function createDispute({ customer_id, amount, description }) {
  const { data } = await client.post("/disputes", {
    customer_id,
    amount,
    description,
  });
  return data;
}

export async function getDisputeStatus(disputeId) {
  const { data } = await client.get(`/disputes/${disputeId}/status`);
  return data;
}

export async function submitBillingEvidence(disputeId, { evidence_type, data, submitted_by }) {
  const { data: result } = await client.post(`/disputes/${disputeId}/billing-evidence`, {
    evidence_type,
    data,
    submitted_by,
  });
  return result;
}

export async function getBillingEvidence(disputeId) {
  const { data } = await client.get(`/disputes/${disputeId}/billing-evidence`);
  return data;
}

export async function reconcileBilling(disputeId) {
  const { data } = await client.post(`/disputes/${disputeId}/reconcile`);
  return data;
}

export async function getReconciliation(disputeId) {
  const { data } = await client.get(`/disputes/${disputeId}/reconciliation`);
  return data;
}

export async function reviewCase(disputeId, payload) {
  const { data } = await client.post(`/disputes/${disputeId}/review`, payload);
  return data;
}

export async function approveMockAdjustment(disputeId, payload) {
  const { data } = await client.post(`/disputes/${disputeId}/adjustments`, payload);
  return data;
}

export async function reopenCase(disputeId, note) {
  const { data } = await client.post(`/disputes/${disputeId}/reopen`, null, { params: { note } });
  return data;
}

export async function getCaseHistory(disputeId) {
  const { data } = await client.get(`/disputes/${disputeId}/history`);
  return data;
}

export default client;
