"""CPython tests for the pure parts of the Tufty HTTPS helper (no network)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sparrow"))

import net  # noqa: E402
import roots  # noqa: E402


def test_split_url():
    assert net.split_url("https://sparrow.fly.dev/api/v1/device") == (
        True, "sparrow.fly.dev", 443, "/api/v1/device")
    assert net.split_url("http://192.168.1.23:8000/api/v1/device?sim=normal") == (
        False, "192.168.1.23", 8000, "/api/v1/device?sim=normal")
    assert net.split_url("https://h") == (True, "h", 443, "/")


@pytest.mark.parametrize("bad", ["ftp://x/y", "sparrow.fly.dev/api", "https:///path"])
def test_split_url_rejects(bad):
    with pytest.raises(ValueError):
        net.split_url(bad)


def test_build_request_sends_token_and_closes():
    req = net.build_request("h.example", "/api/v1/device", {"X-Sparrow-Token": "t0k"})
    assert req.startswith(b"GET /api/v1/device HTTP/1.0\r\nHost: h.example\r\n")
    assert b"X-Sparrow-Token: t0k\r\n" in req and b"Connection: close" in req
    assert req.endswith(b"\r\n\r\n")


def test_parse_response_ok_and_errors():
    ok = b'HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n\r\n{"v":1,"now":5}'
    assert net.parse_response(ok) == {"v": 1, "now": 5}
    with pytest.raises(OSError, match="401"):
        net.parse_response(b"HTTP/1.1 401 Unauthorized\r\n\r\n{}")
    with pytest.raises(ValueError):
        net.parse_response(b"HTTP/1.1 200 OK\r\n")
    with pytest.raises(ValueError):
        net.parse_response(b"HTTP/1.1 200 OK\r\n\r\n<html>")


def test_root_certs_decode_to_der():
    import ssl
    for pem in roots.ROOTS_PEM:
        der = net._der(pem)
        assert der[:1] == b"\x30"  # ASN.1 SEQUENCE
        assert ssl.DER_cert_to_PEM_cert(der).strip().splitlines()[1] == pem.strip().splitlines()[1]
