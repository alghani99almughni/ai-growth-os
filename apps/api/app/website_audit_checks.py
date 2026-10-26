"""Pure, deterministic website-audit checks that do not perform network access.

Keep this module independent from HTTP fetching so each check can be tested with
synthetic evidence. The live audit endpoint remains disabled until the separate
SSRF-safe fetch boundary is implemented and verified.
"""
from collections.abc import Mapping


_HEADER_CHECKS = (
    {
        "key": "content-security-policy",
        "header": "content-security-policy",
        "category": "security_headers",
        "title": "Content Security Policy is missing",
        "severity": "medium",
        "recommendation": "Add a Content-Security-Policy suited to the site; start with report-only mode if compatibility is uncertain.",
    },
    {
        "key": "strict-transport-security",
        "header": "strict-transport-security",
        "category": "security_headers",
        "title": "HTTP Strict Transport Security is missing",
        "severity": "medium",
        "recommendation": "For HTTPS sites, consider a carefully validated Strict-Transport-Security policy. Only include subdomains or preload after confirming they are ready.",
    },
    {
        "key": "x-content-type-options",
        "header": "x-content-type-options",
        "category": "security_headers",
        "title": "MIME-sniffing protection is missing",
        "severity": "low",
        "recommendation": "Set X-Content-Type-Options: nosniff where appropriate.",
    },
    {
        "key": "referrer-policy",
        "header": "referrer-policy",
        "category": "security_headers",
        "title": "Referrer Policy is missing",
        "severity": "low",
        "recommendation": "Set an explicit Referrer-Policy that limits unintended referrer information disclosure.",
    },
    {
        "key": "permissions-policy",
        "header": "permissions-policy",
        "category": "security_headers",
        "title": "Permissions Policy is missing",
        "severity": "low",
        "recommendation": "Set a Permissions-Policy that disables browser features the site does not need.",
    },
)


def analyze_security_headers(headers: Mapping[str, str], *, is_https: bool) -> list[dict[str, str]]:
    """Return missing-header findings only; this function never makes network calls.

    Header names are case-insensitive. Existing headers are not fully validated here,
    so presence is not represented as proof that a policy is secure or correct.
    """
    normalized = {str(name).strip().lower(): str(value).strip() for name, value in headers.items()}
    findings: list[dict[str, str]] = []
    for check in _HEADER_CHECKS:
        if check["key"] == "strict-transport-security" and not is_https:
            continue
        if not normalized.get(check["header"]):
            findings.append({
                "category": check["category"],
                "severity": check["severity"],
                "title": check["title"],
                "recommendation": check["recommendation"],
                "evidence": check["header"],
            })
    return findings
