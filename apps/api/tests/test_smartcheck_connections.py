import json
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

import app.routes_smartcheck as smartcheck


def test_validate_script_url_accepts_deployed_apps_script_url():
    url = "https://script.google.com/macros/s/abc123/exec"
    assert smartcheck.validate_script_url(url) == url


@pytest.mark.parametrize("url", [
    "http://script.google.com/macros/s/abc/exec",
    "https://evil.example/macros/s/abc/exec",
    "https://script.google.com.evil.example/macros/s/abc/exec",
    "https://script.google.com/macros/s/abc/dev",
    "https://user:pass@script.google.com/macros/s/abc/exec",
    "https://script.google.com/macros/s/abc/exec?x=1",
])
def test_validate_script_url_rejects_untrusted_urls(url):
    with pytest.raises(HTTPException):
        smartcheck.validate_script_url(url)


def test_validate_drive_url_accepts_folder_url():
    url = "https://drive.google.com/drive/folders/folder-id"
    assert smartcheck.validate_drive_url(url) == url


@pytest.mark.parametrize("url", [
    "http://drive.google.com/drive/folders/id",
    "https://evil.example/drive/folders/id",
    "https://drive.google.com/file/d/id",
])
def test_validate_drive_url_rejects_invalid_urls(url):
    with pytest.raises(HTTPException):
        smartcheck.validate_drive_url(url)


def test_health_check_reports_ok_payload(monkeypatch):
    response = Mock()
    response.status = 200
    response.__enter__ = lambda self: self
    response.__exit__ = lambda *args: None
    response.read.return_value = json.dumps({"status": "ok"}).encode()
    monkeypatch.setattr(smartcheck, "urlopen", lambda *args, **kwargs: response)
    assert smartcheck.check_script_health("https://script.google.com/macros/s/id/exec")["status"] == "reachable"


def test_health_check_does_not_claim_ready_for_unrecognized_payload(monkeypatch):
    response = Mock()
    response.status = 200
    response.__enter__ = lambda self: self
    response.__exit__ = lambda *args: None
    response.read.return_value = json.dumps({"message": "hello"}).encode()
    monkeypatch.setattr(smartcheck, "urlopen", lambda *args, **kwargs: response)
    assert smartcheck.check_script_health("https://script.google.com/macros/s/id/exec")["status"] == "unverified"
