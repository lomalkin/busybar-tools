"""Outbound update-server requests must send a non-default User-Agent.

The update mirror's CDN returns 403 for the default "Python-urllib/x.y" UA, so every
request to the server must set a custom User-Agent. These tests mock urlopen and assert
the header without any real network access.
"""
import io
import os

import busybar_tools.helpers as helpers
from busybar_tools.config import HTTP_USER_AGENT


class _FakeResponse(io.BytesIO):
    def __init__(self, data=b"", headers=None):
        super().__init__(data)
        self.headers = headers or {}
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _install_fake_urlopen(monkeypatch, data=b"body", headers=None):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["ua"] = req.get_header("User-agent")
        return _FakeResponse(data, headers)

    monkeypatch.setattr(helpers.request, "urlopen", fake_urlopen)
    return seen


def test_fetch_url_sends_custom_user_agent(monkeypatch):
    seen = _install_fake_urlopen(monkeypatch, data=b"index-body")
    out = helpers.fetch_url("https://example/idx.txt")
    assert out == "index-body"
    assert seen["ua"] == HTTP_USER_AGENT
    assert "python-urllib" not in (seen["ua"] or "").lower()


def test_file_download_sends_custom_user_agent_and_writes_file(monkeypatch, tmp_path):
    payload = b"BUNDLE-CONTENT"
    seen = _install_fake_urlopen(monkeypatch, data=payload, headers={"Content-Length": str(len(payload))})
    path = helpers.file_download("https://example/bundle.tgz", "bundle.tgz", str(tmp_path), progress=True)
    assert path == os.path.join(str(tmp_path), "bundle.tgz")
    assert open(path, "rb").read() == payload
    assert seen["ua"] == HTTP_USER_AGENT
    assert "python-urllib" not in (seen["ua"] or "").lower()
