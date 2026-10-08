"""Language and persona policy for natural Indian-language voice agents.

This layer deliberately keeps grammatical/persona guidance separate from WebRTC
and provider code. It is configuration-driven and safe when customer gender is
unknown.
"""
from __future__ import annotations

from typing import Any

SUPPORTED_INDIAN_LOCALES = {
    "en-IN", "hi-IN", "te-IN", "ta-IN", "kn-IN", "ml-IN", "mr-IN",
    "bn-IN", "gu-IN", "pa-IN", "or-IN", "ur-IN", "as-IN",
}

LANGUAGE_NAMES = {
    "en-IN": "Indian English",
    "hi-IN": "Hindi",
    "te-IN": "Telugu",
    "ta-IN": "Tamil",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "bn-IN": "Bengali",
    "gu-IN": "Gujarati",
    "pa-IN": "Punjabi",
    "or-IN": "Odia",
    "ur-IN": "Urdu",
    "as-IN": "Assamese",
}


def _first(*values: Any, default: str = "") -> str:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


def language_persona_policy(
    *,
    language: str | None = None,
    agent_gender: str | None = None,
    customer_gender: str | None = None,
    formality: str | None = None,
    region: str | None = None,
) -> dict[str, str]:
    locale = _first(language, default="en-IN")
    if locale.lower() in {"hi", "hindi"}:
        locale = "hi-IN"
    elif locale.lower() in {"te", "telugu"}:
        locale = "te-IN"
    if locale not in SUPPORTED_INDIAN_LOCALES:
        locale = "en-IN"

    gender = _first(agent_gender, default="neutral").lower()
    if gender not in {"male", "female", "neutral"}:
        gender = "neutral"

    customer = _first(customer_gender, default="unknown").lower()
    if customer not in {"male", "female", "unknown", "neutral"}:
        customer = "unknown"

    style = _first(formality, default="respectful").lower()
    if style not in {"respectful", "professional", "friendly"}:
        style = "respectful"

    return {
        "locale": locale,
        "language_name": LANGUAGE_NAMES.get(locale, locale),
        "agent_gender": gender,
        "customer_gender": customer,
        "formality": style,
        "region": _first(region, default="India"),
    }


def language_policy_prompt(policy: dict[str, str]) -> str:
    locale = policy["locale"]
    language_name = policy["language_name"]
    agent_gender = policy["agent_gender"]
    customer_gender = policy["customer_gender"]
    formality = policy["formality"]
    region = policy["region"]

    gender_rule = {
        "female": (
            "When speaking about yourself in grammatically gendered languages, "
            "use consistently feminine first-person forms. Do not randomly switch "
            "to masculine forms."
        ),
        "male": (
            "When speaking about yourself in grammatically gendered languages, "
            "use consistently masculine first-person forms. Do not randomly switch "
            "to feminine forms."
        ),
        "neutral": (
            "Prefer natural gender-neutral constructions when available; never "
            "invent awkward gender-neutral grammar. Keep any required self-reference "
            "grammatically consistent."
        ),
    }[agent_gender]

    return f"""
LANGUAGE & PERSONA POLICY:
- Preferred locale: {locale} ({language_name})
- Region: {region}
- Agent persona gender: {agent_gender}
- Customer gender: {customer_gender}
- Register: {formality}
- Speak naturally for customers in India; preserve the caller's current language
  and natural code-switching when appropriate.
- Address customers respectfully. Do not infer customer gender from a name.
- Customer gender is unknown unless explicitly/reliably supplied; never assume it.
- {gender_rule}
- For Hindi and other gendered Indian languages, grammatical agreement must be
  correct for the speaker/person being described, including verbs, adjectives,
  participles and honorific constructions.
- Do not mechanically replace suffixes such as "sakta/sakti" after generating a
  sentence; generate the complete sentence with correct grammar from the start.
- Prefer concise, conversational sentences over formal written-language phrasing.
- Never use gendered language to make assumptions about the customer's identity.
""".strip()
