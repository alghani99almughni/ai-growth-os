import pytest
from fastapi import HTTPException

from app.industry_templates import available_industries
from app.routes_onboarding import _validated_template_key


def test_onboarding_accepts_only_available_starter_templates():
    supported = {item["key"] for item in available_industries()}
    assert supported
    for key in supported:
        assert _validated_template_key(key) == key


@pytest.mark.parametrize("value", ["", "   ", "hospital", "unknown-template", "../cafe"])
def test_onboarding_rejects_unknown_starter_template(value):
    with pytest.raises(HTTPException) as exc:
        _validated_template_key(value)
    assert exc.value.status_code == 400
    assert "starter template" in exc.value.detail.lower()
