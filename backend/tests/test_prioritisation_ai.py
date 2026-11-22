import httpx
import pytest

from app.config import Settings
from app.schemas import PrioritisationWeights
from app.services import ai
from app.services.prioritisation import normalise, priority_score


class Opp:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def test_normalise_bounds():
    assert normalise(1) == 0.2 and normalise(5) == 1.0
    with pytest.raises(ValueError):
        normalise(0)


def test_formula_matches_documented_default():
    o = Opp(customer_value=4, data_importance=3, strategic_relevance=5, commercial_opportunity=2,
            technical_effort=2, access_complexity=4)
    expected = (0.8 * 0.6 * 1.0) / (0.4 * 0.8)
    assert priority_score(o, PrioritisationWeights()) == pytest.approx(expected, abs=1e-4)


def test_ai_uses_header_key_and_parses_text():
    seen = {}

    def handler(req):
        seen["key"] = req.headers.get("x-goog-api-key")
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Summary"}]}}]})

    out = ai.generate(Settings(gemini_api_key="k"), "summarise_errors", "err", transport=httpx.MockTransport(handler))
    assert out == "Summary" and seen["key"] == "k" and "key=" not in seen["url"]


def test_ai_rate_limit_is_reported():
    with pytest.raises(ai.AIUnavailable, match="rate limit"):
        ai.generate(Settings(gemini_api_key="k"), "summarise_errors", "e", transport=httpx.MockTransport(lambda r: httpx.Response(429)))
