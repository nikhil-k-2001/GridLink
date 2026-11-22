"""Optional AI assistance via the Gemini Developer API (free tier). Never required by the pipeline.

The key is read from GEMINI_API_KEY. Only connector metadata/error text is sent - never credentials.
"""
from __future__ import annotations

import httpx

from app.config import Settings

PROMPTS = {
    "summarise_errors": "You are a data integration engineer. Summarise the following connector sync errors for a "
    "product manager: likely root causes, impact on data quality, and concrete next steps. Be concise; "
    "do not invent facts that are not in the logs.\n\n",
    "explain_dataset": "Explain this energy dataset to a non-specialist product manager: what it measures, its unit "
    "and granularity, and pitfalls when comparing it with similar datasets from other providers. Only use the "
    "metadata given.\n\n",
    "summarise_documentation": "Summarise this provider API documentation into: authentication, key endpoints, "
    "parameters, formats, limits, licensing. Mark anything uncertain as 'to verify'.\n\n",
}


class AIUnavailable(Exception):
    pass


def generate(settings: Settings, task: str, context: str, transport: httpx.BaseTransport | None = None) -> str:
    if not settings.gemini_api_key:
        raise AIUnavailable("AI assistance is disabled: set GEMINI_API_KEY (free tier) in backend/.env to enable it.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent"
    body = {"contents": [{"parts": [{"text": PROMPTS[task] + context[:15000]}]}]}
    with httpx.Client(timeout=30, transport=transport) as client:
        resp = client.post(url, json=body, headers={"x-goog-api-key": settings.gemini_api_key})
    if resp.status_code == 429:
        raise AIUnavailable("Gemini free-tier rate limit reached; try again later.")
    if resp.status_code >= 400:
        raise AIUnavailable(f"Gemini API error HTTP {resp.status_code}")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise AIUnavailable("Gemini returned no text") from exc
