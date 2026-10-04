"""
llm_parser.py

Uses the Mistral API's chat completions endpoint to extract structured
fields from free-text dispute evidence submissions, including
signature_confirmation and policy_compliance -- used by the resolve
pipeline's text evidence parser.

Uses OPENROUTER_API_KEY and OPENROUTER_MODEL when configured; otherwise falls
back to MISTRAL_API_KEY. Values may be set in the environment or backend/.env.
"""

import json
import logging
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

MISTRAL_API_URL = "https://api.mistral.ai/v1/chat/completions"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_MODEL = "openrouter/free"
MISTRAL_MODEL = "mistral-small-latest"
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a data extraction engine. Extract the following fields from the "
    "dispute evidence text: date, amount, tracking_number, delivery_status, "
    "invoice_present (bool), refund_policy_match (bool), signature_confirmation "
    "(bool -- true only if the text indicates a signature or delivery "
    "confirmation was actually obtained/on file; false if it explicitly says "
    "no signature was obtained; null if not mentioned), policy_compliance "
    "(bool -- true only if the text indicates the merchant complied with its "
    "own stated policy, e.g. return/refund policy; false if it indicates a "
    "policy violation; null if not mentioned). If a field cannot be found, "
    "return null for it. Return ONLY a valid JSON object, no explanation, no "
    "markdown formatting, no code fences."
)

JSON_ONLY_REMINDER = "Return valid JSON only, nothing else."


def _call_llm(messages: list[dict]) -> str:
    """Send a chat completion request to the configured provider."""
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    mistral_api_key = os.getenv("MISTRAL_API_KEY")
    if openrouter_api_key:
        api_key = openrouter_api_key
        api_url = OPENROUTER_API_URL
        model = os.getenv("OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
    elif mistral_api_key:
        api_key = mistral_api_key
        api_url = MISTRAL_API_URL
        model = MISTRAL_MODEL
    else:
        raise RuntimeError(
            "Set OPENROUTER_API_KEY or MISTRAL_API_KEY in the environment or backend/.env."
        )

    if not api_key:
        raise RuntimeError(
            "The configured LLM API key is empty."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
    }

    response = requests.post(api_url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()

    data = response.json()
    return data["choices"][0]["message"]["content"]


def _try_parse_json(text: str):
    """Return the parsed dict, or None if `text` isn't valid JSON."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None


def parse_evidence(raw_text: str) -> dict:
    """
    Extract structured fields (date, amount, tracking_number,
    delivery_status, invoice_present, refund_policy_match,
    signature_confirmation, policy_compliance) from raw dispute evidence
    text using the Mistral API.

    Retries once with an added JSON-only reminder if the first response
    isn't valid JSON. If it still isn't valid JSON, returns
    {"parse_error": True, "raw_response": <the text>}.
    """

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": raw_text},
    ]

    content = _call_llm(messages)
    parsed = _try_parse_json(content)
    if parsed is not None:
        return parsed

    # Retry once with an added reminder to return JSON only.
    retry_messages = messages + [
        {"role": "assistant", "content": content},
        {"role": "user", "content": JSON_ONLY_REMINDER},
    ]
    retry_content = _call_llm(retry_messages)
    parsed = _try_parse_json(retry_content)
    if parsed is not None:
        return parsed

    return {"parse_error": True, "raw_response": retry_content}


def interpret_billing_case(
    evidence: list, calculation: dict, dispute_description: str | None = None
) -> tuple[str, dict | None]:
    """Return optional, source-cited interpretation without doing arithmetic."""
    if os.getenv("BILLING_AI_ENABLED", "true").lower() not in {"1", "true", "yes", "on"}:
        return "disabled", None
    if not evidence:
        return "insufficient_evidence", None

    source_ids = {f"BE-{item.id}" for item in evidence}
    records = [
        {"source_id": f"BE-{item.id}", "type": item.evidence_type, "data": item.payload}
        for item in evidence
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "You investigate disputed invoices. Explain only possible causes supported by the supplied records. "
                "Do not calculate, recompute, or propose monetary amounts. Distinguish arithmetic discrepancies "
                "from unclear contract interpretation. Every summary and possible cause must cite one or more exact "
                "source_id values from the input. Ask concise questions for missing evidence. Return JSON only with "
                "keys summary, summary_citations, possible_causes (objects with category, explanation, citations), "
                "and follow_up_questions (strings). Categories are calculation_error, contract_interpretation, or other."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "customer_dispute_description": dispute_description,
                "billing_evidence": records,
                "deterministic_calculation": calculation,
            }),
        },
    ]
    try:
        response = _try_parse_json(_call_llm(messages))
    except (RuntimeError, requests.RequestException, KeyError, TypeError, ValueError) as error:
        if isinstance(error, requests.HTTPError) and error.response is not None:
            logger.warning("Billing AI request failed with HTTP %s", error.response.status_code)
        else:
            logger.warning("Billing AI request failed: %s", type(error).__name__)
        return "unavailable", None

    if not isinstance(response, dict):
        logger.warning("Billing AI response was not a JSON object")
        return "unavailable", None
    summary = response.get("summary")
    summary_citations = response.get("summary_citations")
    causes = response.get("possible_causes")
    questions = response.get("follow_up_questions")
    if not isinstance(summary, str) or not summary.strip() or not isinstance(summary_citations, list):
        logger.warning("Billing AI response is missing a valid summary or citations")
        return "unavailable", None
    if not summary_citations or any(
        not isinstance(source, str) or source not in source_ids for source in summary_citations
    ):
        logger.warning("Billing AI response contains missing or unknown summary citations")
        return "unavailable", None
    if not isinstance(causes, list) or not isinstance(questions, list):
        logger.warning("Billing AI response is missing causes or follow-up questions")
        return "unavailable", None
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("explanation"), str)
        or not item.get("explanation", "").strip()
        or item.get("category") not in {"calculation_error", "contract_interpretation", "other"}
        or not isinstance(item.get("citations"), list)
        or not item["citations"]
        or any(
            not isinstance(source, str) or source not in source_ids
            for source in item["citations"]
        )
        for item in causes
    ):
        logger.warning("Billing AI response contains an invalid cause or citation")
        return "unavailable", None
    if any(not isinstance(question, str) for question in questions):
        logger.warning("Billing AI response contains an invalid follow-up question")
        return "unavailable", None

    return "complete", {
        "summary": summary.strip(),
        "summary_citations": summary_citations,
        "possible_causes": causes,
        "follow_up_questions": questions,
    }


if __name__ == "__main__":
    sample_text = (
        "Order #4521 shipped on March 3rd for $89.99. Tracking number "
        "1Z999AA10123456784. Package marked delivered. No signature on file."
    )

    print("Input evidence text:")
    print(f"  {sample_text}\n")

    try:
        result = parse_evidence(sample_text)
        print("Parsed result:")
        print(json.dumps(result, indent=2))
    except RuntimeError as e:
        print(f"Could not call Mistral API: {e}")
