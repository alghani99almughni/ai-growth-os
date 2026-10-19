"""Provider adapters for evidence-based AEO/GEO visibility observations.

This module deliberately uses official provider APIs and records only observable
answers/citations. It does not claim to reproduce consumer-app rankings.
"""
from __future__ import annotations

import re
from typing import Any

import httpx


PROVIDER_ORDER = ("gemini", "perplexity", "grok", "claude")
TIMEOUT = httpx.Timeout(35.0, connect=8.0)


def _citations(value: Any) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []
    if isinstance(value, str) and value.startswith(("https://", "http://")):
        found.append({"url": value[:2048], "title": ""})
    elif isinstance(value, dict):
        uri = value.get("uri") or value.get("url")
        title = value.get("title") or value.get("name") or ""
        if isinstance(uri, str) and uri.startswith(("https://", "http://")):
            found.append({"url": uri[:2048], "title": str(title)[:300]})
        for child in value.values():
            found.extend(_citations(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_citations(child))
    # Keep stable order and cap response payload size.
    unique = []
    seen = set()
    for item in found:
        if item["url"] not in seen:
            unique.append(item)
            seen.add(item["url"])
        if len(unique) >= 30:
            break
    return unique


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_text(x) for x in value)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        return "".join(_text(x) for x in value.get("parts", []) or [])
    return ""


def _extract(provider: str, data: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    if provider == "gemini":
        candidates = data.get("candidates") or []
        answer = _text((candidates[0].get("content") or {}).get("parts") or []) if candidates else ""
        citations = _citations(data.get("groundingMetadata") or (candidates[0].get("groundingMetadata") if candidates else {}))
        return answer, citations
    if provider == "perplexity":
        choices = data.get("choices") or []
        answer = _text((choices[0].get("message") or {}).get("content")) if choices else ""
        return answer, _citations(data.get("citations") or data.get("search_results") or [])
    if provider == "grok":
        choices = data.get("choices") or []
        answer = _text((choices[0].get("message") or {}).get("content")) if choices else ""
        return answer, _citations(data.get("citations") or data.get("sources") or [])
    if provider == "claude":
        answer = _text(data.get("content") or [])
        return answer, _citations(data.get("citations") or [])
    raise ValueError("Unsupported visibility provider")


async def run_provider(provider: str, api_key: str, model: str, prompt: str) -> dict[str, Any]:
    """Call a supported provider and return answer plus citations when supplied."""
    provider = provider.lower()
    if provider not in PROVIDER_ORDER:
        raise ValueError("Unsupported visibility provider")
    if not api_key or not model:
        raise ValueError(f"{provider} provider is not configured")

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
        if provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            response = await client.post(
                url, params={"key": api_key},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "tools": [{"google_search": {}}]},
            )
        elif provider == "perplexity":
            response = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            )
        elif provider == "grok":
            response = await client.post(
                "https://api.x.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            )
        else:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": model, "max_tokens": 900,
                      "messages": [{"role": "user", "content": prompt}]},
            )

        if response.status_code >= 400:
            # Do not persist or return response bodies: they can contain provider details.
            raise RuntimeError(f"{provider} provider returned HTTP {response.status_code}")
        data = response.json()
        answer, citations = _extract(provider, data)
        if not answer.strip():
            raise RuntimeError(f"{provider} provider returned an empty answer")
        return {"provider": provider, "model": model, "answer": answer[:12000],
                "citations": citations, "method": "search_grounded" if provider in ("gemini", "perplexity") else "model_sampled"}


def observation_match(answer: str, brand_name: str, domain: str, citations: list[dict[str, str]]) -> dict[str, Any]:
    """A transparent lexical observation, not a semantic ranking or guaranteed score."""
    text = (answer or "").casefold()
    name = (brand_name or "").strip().casefold()
    host = re.sub(r"^https?://", "", (domain or "").strip().casefold()).split("/")[0].removeprefix("www.")
    mentioned = bool(name and name in text)
    cited = False
    for item in citations or []:
        url_host = re.sub(r"^https?://", "", (item.get("url") or "").casefold()).split("/")[0].removeprefix("www.")
        if host and (url_host == host or url_host.endswith("." + host)):
            cited = True
            break
    return {"brand_mentioned": mentioned, "website_cited": cited,
            "evidence_quality": "provider_citations" if citations else "answer_text_only"}
