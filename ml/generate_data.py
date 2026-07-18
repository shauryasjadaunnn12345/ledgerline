"""
generate_data.py

Generates a synthetic dataset of credit card disputes for training/testing
downstream models. Outcomes are produced by a rule-based function that mixes
strong heuristics (e.g. missing tracking + no signature -> refund) with
weighted randomness so the data has realistic overlap and noise rather than
perfectly separable classes.

Usage:
    python generate_data.py
"""

import numpy as np
import pandas as pd

# Fix the seed so the dataset is reproducible across runs.
# Remove/change this if you want a different sample each time.
SEED = 42
rng = np.random.default_rng(SEED)

N_ROWS = 1500
REASON_CODES = ["not_received", "not_as_described", "duplicate_charge", "unauthorized"]
OUTCOMES = np.array(["refund", "deny", "partial"])
LABEL_NOISE_FRAC = 0.10


def generate_features(n: int, rng: np.random.Generator) -> pd.DataFrame:
    """Generate the raw feature columns for n dispute cases."""

    reason_code = rng.choice(
        REASON_CODES, size=n, p=[0.30, 0.25, 0.20, 0.25]
    )
    has_tracking = rng.choice([True, False], size=n, p=[0.55, 0.45])
    has_signature_confirmation = rng.choice([True, False], size=n, p=[0.35, 0.65])

    # Response times skew short with a long tail out to 200 hours.
    merchant_response_time_hours = rng.exponential(scale=40, size=n)
    merchant_response_time_hours = np.clip(merchant_response_time_hours, 0, 200)
    merchant_response_time_hours = np.round(merchant_response_time_hours, 1)

    merchant_policy_compliance = rng.choice([True, False], size=n, p=[0.6, 0.4])

    card_member_dispute_history_count = rng.poisson(lam=1.5, size=n)
    card_member_dispute_history_count = np.clip(card_member_dispute_history_count, 0, 10)

    evidence_completeness_pct = rng.normal(loc=60, scale=25, size=n)
    evidence_completeness_pct = np.clip(evidence_completeness_pct, 0, 100)
    evidence_completeness_pct = np.round(evidence_completeness_pct, 1)

    return pd.DataFrame(
        {
            "reason_code": reason_code,
            "has_tracking": has_tracking,
            "has_signature_confirmation": has_signature_confirmation,
            "merchant_response_time_hours": merchant_response_time_hours,
            "merchant_policy_compliance": merchant_policy_compliance,
            "card_member_dispute_history_count": card_member_dispute_history_count,
            "evidence_completeness_pct": evidence_completeness_pct,
        }
    )


def assign_outcomes(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    """
    Rule-based outcome assignment.

    Strategy: build up unnormalized weights for [refund, deny, partial] per
    row, then sample from the resulting probability distribution. Two strong
    heuristics override/dominate the weights; everything else falls back to
    a softer, feature-weighted mix so outcomes aren't perfectly separable.
    """

    n = len(df)
    has_tracking = df["has_tracking"].to_numpy()
    has_signature = df["has_signature_confirmation"].to_numpy()
    policy_compliance = df["merchant_policy_compliance"].to_numpy()
    response_time = df["merchant_response_time_hours"].to_numpy()
    dispute_history = df["card_member_dispute_history_count"].to_numpy()
    evidence_pct = df["evidence_completeness_pct"].to_numpy()
    reason_code = df["reason_code"].to_numpy()

    strong_refund_mask = (~has_tracking) & (~has_signature)
    strong_deny_mask = policy_compliance & has_signature
    # A row could technically satisfy both masks depending on feature combos;
    # strong_deny takes priority if both trigger, since signature confirmation
    # is direct evidence for the merchant.
    strong_refund_mask &= ~strong_deny_mask
    other_mask = ~(strong_refund_mask | strong_deny_mask)

    refund = np.zeros(n)
    deny = np.zeros(n)
    partial = np.zeros(n)

    # --- Strong heuristic 1: missing tracking + no signature -> refund ---
    refund[strong_refund_mask] = 6.0
    deny[strong_refund_mask] = 1.0
    partial[strong_refund_mask] = 1.5

    # --- Strong heuristic 2: policy compliance + signature -> deny ---
    refund[strong_deny_mask] = 1.0
    deny[strong_deny_mask] = 6.0
    partial[strong_deny_mask] = 1.5

    # --- Everything else: weighted randomness from the remaining features ---
    idx = np.where(other_mask)[0]

    refund[idx] = 1.0
    deny[idx] = 1.0
    partial[idx] = 1.0

    # More complete evidence favors the merchant (deny); sparse evidence
    # favors the cardholder (refund).
    deny[idx] += (evidence_pct[idx] / 100) * 2.5
    refund[idx] += (1 - evidence_pct[idx] / 100) * 2.0

    # A slow merchant response reads as the merchant not engaging, which
    # nudges toward refund.
    refund[idx] += np.minimum(response_time[idx] / 200, 1.0) * 1.5

    # Frequent disputers draw a bit more scrutiny -> slightly more deny/partial.
    deny[idx] += (dispute_history[idx] / 10) * 1.0
    partial[idx] += (dispute_history[idx] / 10) * 0.5

    reason_subset = reason_code[idx]
    refund[idx] += np.where(reason_subset == "unauthorized", 1.5, 0.0)
    refund[idx] += np.where(reason_subset == "duplicate_charge", 1.2, 0.0)
    partial[idx] += np.where(reason_subset == "duplicate_charge", 0.5, 0.0)
    partial[idx] += np.where(reason_subset == "not_as_described", 1.0, 0.0)
    deny[idx] += np.where(reason_subset == "not_as_described", 0.5, 0.0)

    not_received_subset = reason_subset == "not_received"
    deny[idx] += np.where(not_received_subset & has_tracking[idx], 1.0, 0.0)
    refund[idx] += np.where(not_received_subset & ~has_tracking[idx], 1.0, 0.0)

    # Partial tracking without signature confirmation is the classic
    # "partial" gray area.
    partial[idx] += np.where(has_tracking[idx] & ~has_signature[idx], 0.8, 0.0)

    # Normalize weights into probabilities and sample via inverse-CDF.
    totals = refund + deny + partial
    p_refund = refund / totals
    p_deny = deny / totals
    # p_partial = partial / totals  (implied remainder)

    draw = rng.random(n)
    outcomes = np.where(
        draw < p_refund,
        "refund",
        np.where(draw < p_refund + p_deny, "deny", "partial"),
    )
    return outcomes


def apply_label_noise(outcomes: np.ndarray, frac: float, rng: np.random.Generator) -> np.ndarray:
    """Randomly reassign `frac` of labels to a different outcome to simulate
    mislabeled/ambiguous real-world cases."""

    n = len(outcomes)
    n_noisy = int(round(n * frac))
    noisy_idx = rng.choice(n, size=n_noisy, replace=False)

    noisy_outcomes = outcomes.copy()
    for i in noisy_idx:
        current = noisy_outcomes[i]
        alternatives = OUTCOMES[OUTCOMES != current]
        noisy_outcomes[i] = rng.choice(alternatives)

    return noisy_outcomes


def main():
    df = generate_features(N_ROWS, rng)
    clean_outcomes = assign_outcomes(df, rng)
    df["outcome"] = apply_label_noise(clean_outcomes, LABEL_NOISE_FRAC, rng)

    output_path = "disputes.csv"
    df.to_csv(output_path, index=False)

    print(f"Saved {len(df)} rows to {output_path}\n")
    print("Class balance (outcome):")
    counts = df["outcome"].value_counts()
    pct = df["outcome"].value_counts(normalize=True).round(4) * 100
    balance = pd.DataFrame({"count": counts, "pct": pct.map(lambda x: f"{x:.1f}%")})
    print(balance)


if __name__ == "__main__":
    main()
