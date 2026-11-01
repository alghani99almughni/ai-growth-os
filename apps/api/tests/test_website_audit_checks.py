"""Tests for pure website-audit checks; no network calls are allowed here."""
from app.website_audit_checks import analyze_security_headers


def test_missing_security_headers_are_reported_case_insensitively():
    findings = analyze_security_headers({"Content-Type": "text/html"}, is_https=True)
    missing = {item["evidence"] for item in findings}
    assert missing == {
        "content-security-policy",
        "strict-transport-security",
        "x-content-type-options",
        "referrer-policy",
        "permissions-policy",
    }
    assert all(item["category"] == "security_headers" for item in findings)


def test_present_headers_are_not_reported_as_missing():
    findings = analyze_security_headers(
        {
            "CONTENT-SECURITY-POLICY": "default-src 'self'",
            "Strict-Transport-Security": "max-age=31536000",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "camera=()",
        },
        is_https=True,
    )
    assert findings == []


def test_hsts_is_not_flagged_for_plain_http_response():
    findings = analyze_security_headers({}, is_https=False)
    assert "strict-transport-security" not in {item["evidence"] for item in findings}
    assert len(findings) == 4


def test_empty_header_values_are_treated_as_missing():
    findings = analyze_security_headers({"content-security-policy": "  "}, is_https=True)
    assert "content-security-policy" in {item["evidence"] for item in findings}


def test_header_analyzer_does_not_claim_present_policy_is_validated():
    # Deliberately permissive CSP is still considered present. A separate validator
    # must assess policy quality before any report describes it as safe.
    findings = analyze_security_headers({"Content-Security-Policy": "*"}, is_https=True)
    assert "content-security-policy" not in {item["evidence"] for item in findings}
