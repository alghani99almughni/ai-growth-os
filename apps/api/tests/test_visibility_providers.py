"""Regression tests for provider evidence parsing and conservative mention matching."""
import app.main  # noqa: F401
from app.visibility_providers import _extract, _citations, observation_match


def test_gemini_extracts_grounded_answer_and_sources():
    answer, citations = _extract("gemini", {
        "candidates": [{
            "content": {"parts": [{"text": "Example Gym is nearby."}]},
            "groundingMetadata": {"groundingChunks": [
                {"web": {"uri": "https://example.com/about", "title": "Example Gym"}},
                {"web": {"uri": "https://directory.example.org/list", "title": "Directory"}},
            ]},
        }]
    })
    assert answer == "Example Gym is nearby."
    assert [item["url"] for item in citations] == [
        "https://example.com/about", "https://directory.example.org/list"
    ]


def test_perplexity_extracts_answer_and_citations():
    answer, citations = _extract("perplexity", {
        "choices": [{"message": {"content": "Try Example Gym."}}],
        "citations": ["https://example.com", "https://other.example.org"],
    })
    assert answer == "Try Example Gym."
    assert len(citations) == 2


def test_claude_answer_is_marked_as_model_text_not_search_evidence():
    answer, citations = _extract("claude", {
        "content": [{"type": "text", "text": "Example Gym is an option."}]
    })
    assert answer == "Example Gym is an option."
    assert citations == []


def test_brand_match_and_website_citation_are_distinct_signals():
    result = observation_match(
        "Example Gym is a local option.",
        "Example Gym", "www.example.com",
        [{"url": "https://example.com/services", "title": "Services"}],
    )
    assert result == {
        "brand_mentioned": True,
        "website_cited": True,
        "evidence_quality": "provider_citations",
    }


def test_competitor_citation_does_not_count_as_brand_website_citation():
    result = observation_match(
        "Example Gym is mentioned.",
        "Example Gym", "example.com",
        [{"url": "https://competitor.example.org", "title": "Competitor"}],
    )
    assert result["brand_mentioned"] is True
    assert result["website_cited"] is False


def test_citation_parser_deduplicates_and_ignores_non_urls():
    citations = _citations({
        "sources": [
            {"url": "https://example.com", "title": "One"},
            {"uri": "https://example.com", "title": "Duplicate"},
            {"url": "javascript:alert(1)", "title": "Unsafe"},
        ]
    })
    assert citations == [{"url": "https://example.com", "title": "One"}]


def test_grok_citations_are_not_mislabeled_as_search_grounded(monkeypatch):
    """Grok's ordinary chat-completions response is sampled model output, not verified search grounding."""
    import asyncio
    import app.visibility_providers as providers

    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "choices": [{"message": {"content": "Example Gym is nearby."}}],
                "citations": ["https://example.com"],
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)
    result = asyncio.run(providers.run_provider("grok", "test-key", "grok-test-model", "test prompt"))
    assert result["answer"] == "Example Gym is nearby."
    assert result["citations"] == [{"url": "https://example.com", "title": ""}]
    assert result["method"] == "model_sampled"
