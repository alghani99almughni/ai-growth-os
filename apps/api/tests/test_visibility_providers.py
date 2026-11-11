"""Regression tests for provider evidence parsing and conservative mention matching."""
import app.main  # noqa: F401
import pytest
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

def test_brand_mention_uses_phrase_boundaries_not_substrings():
    result = observation_match(
        "ABC Fitness is mentioned, but ABCDEF is a different name.",
        "ABC", "example.com", [],
    )
    assert result["brand_mentioned"] is True
    assert observation_match("ABCDEF is here.", "ABC", "example.com", [])["brand_mentioned"] is False


def test_website_citation_normalizes_ports_and_subdomains():
    result = observation_match(
        "Example Gym is mentioned.",
        "Example Gym", "https://www.example.com/",
        [{"url": "https://booking.example.com:8443/path", "title": "Booking"}],
    )
    assert result["website_cited"] is True


def test_lookalike_domain_does_not_count_as_website_citation():
    result = observation_match(
        "Example Gym is mentioned.",
        "Example Gym", "example.com",
        [{"url": "https://example.com.attacker.test/path", "title": "Lookalike"}],
    )
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


@pytest.mark.parametrize("url", [
    "javascript:alert(1)",
    "https://user:password@example.com/private",
    "https:///missing-host",
    "https://example.com:99999/path",
    "https://example.com/path with spaces",
])
def test_citation_parser_rejects_malformed_or_credentialed_urls(url):
    assert _citations({"url": url}) == []


def test_citation_parser_rejects_oversized_url():
    assert _citations({"url": "https://example.com/" + ("a" * 2100)}) == []


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


def test_provider_requests_use_expected_official_endpoints_and_auth(monkeypatch):
    import asyncio
    import app.visibility_providers as providers

    cases = [
        ("gemini", "https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent", "x-goog-api-key"),
        ("perplexity", "https://api.perplexity.ai/chat/completions", "Authorization"),
        ("grok", "https://api.x.ai/v1/chat/completions", "Authorization"),
        ("claude", "https://api.anthropic.com/v1/messages", "x-api-key"),
    ]

    for provider, expected_url, auth_header in cases:
        captured = {}

        class FakeResponse:
            status_code = 200
            def json(self):
                if provider == "gemini":
                    return {"candidates": [{"content": {"parts": [{"text": "A grounded answer."}]}}]}
                if provider == "claude":
                    return {"content": [{"type": "text", "text": "A model answer."}]}
                return {"choices": [{"message": {"content": "A provider answer."}}]}

        class FakeClient:
            def __init__(self, *args, **kwargs):
                assert kwargs.get("follow_redirects") is False
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                return False
            async def post(self, url, **kwargs):
                captured["url"] = url
                captured["kwargs"] = kwargs
                return FakeResponse()

        monkeypatch.setattr(providers.httpx, "AsyncClient", FakeClient)
        result = asyncio.run(providers.run_provider(provider, "secret-test-key", "gemini-test" if provider == "gemini" else provider + "-test-model", "test prompt"))
        assert captured["url"] == expected_url
        assert auth_header in captured["kwargs"]["headers"]
        assert "secret-test-key" in captured["kwargs"]["headers"][auth_header]
        assert result["answer"]
        assert result["method"] == "model_sampled"  # No provider-supplied sources in this fixture.


def test_provider_http_error_does_not_expose_response_body(monkeypatch):
    import asyncio
    import app.visibility_providers as providers

    class FakeResponse:
        status_code = 401
        text = "sensitive provider diagnostic"
        def json(self):
            return {"error": "sensitive provider diagnostic"}

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
    with pytest.raises(RuntimeError) as error:
        asyncio.run(providers.run_provider("perplexity", "secret-test-key", "test-model", "test prompt"))
    assert "HTTP 401" in str(error.value)
    assert "sensitive provider diagnostic" not in str(error.value)


@pytest.mark.parametrize("provider", ["gemini", "perplexity", "grok", "claude"])
def test_provider_requires_both_key_and_model(provider):
    import asyncio
    import app.visibility_providers as providers
    with pytest.raises(ValueError, match="not configured"):
        asyncio.run(providers.run_provider(provider, "", "test-model", "test prompt"))
    with pytest.raises(ValueError, match="not configured"):
        asyncio.run(providers.run_provider(provider, "test-key", "", "test prompt"))


@pytest.mark.parametrize("provider,payload", [
    ("gemini", {"candidates": [{"content": {"parts": [{"text": "An answer without grounding metadata."}]}}]}),
    ("perplexity", {"choices": [{"message": {"content": "An answer without citations."}}]}),
])
def test_search_capable_provider_without_returned_sources_is_model_sampled(monkeypatch, provider, payload):
    """Do not claim grounding merely because a provider supports a search feature."""
    import asyncio
    import app.visibility_providers as providers

    class FakeResponse:
        status_code = 200
        def json(self):
            return payload

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
    model = "gemini-test" if provider == "gemini" else "sonar-test"
    result = asyncio.run(providers.run_provider(provider, "test-key", model, "test prompt"))
    assert result["method"] == "model_sampled"
    assert result["citations"] == []


def test_search_capable_provider_with_sources_is_search_grounded(monkeypatch):
    import asyncio
    import app.visibility_providers as providers

    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "choices": [{"message": {"content": "A sourced answer."}}],
                "citations": ["https://example.com/source"],
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
    result = asyncio.run(providers.run_provider("perplexity", "test-key", "sonar-test", "test prompt"))
    assert result["method"] == "search_grounded"
    assert result["citations"] == [{"url": "https://example.com/source", "title": ""}]


def test_gemini_with_grounding_sources_is_search_grounded(monkeypatch):
    import asyncio
    import app.visibility_providers as providers

    class FakeResponse:
        status_code = 200
        def json(self):
            return {
                "candidates": [{"content": {"parts": [{"text": "A sourced Gemini answer."}]}}],
                "groundingMetadata": {
                    "groundingChunks": [{"web": {"uri": "https://example.com/source", "title": "Source"}}]
                },
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
    result = asyncio.run(providers.run_provider("gemini", "test-key", "gemini-test", "test prompt"))
    assert result["method"] == "search_grounded"
    assert result["citations"] == [{"url": "https://example.com/source", "title": "Source"}]
