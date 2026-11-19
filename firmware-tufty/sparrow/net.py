# Minimal HTTPS GET with certificate verification (MicroPython on the Tufty 2350).
#
# Pimoroni's bundled fetch helper turns verification off (CERT_NONE). Sparrow sends an access
# token, so this module verifies the server against the Let's Encrypt roots in roots.py.
# HTTP/1.0 keeps the response simple: no chunked encoding, the server closes when done.
import json
import socket

try:
    import binascii
except ImportError:  # older MicroPython
    import ubinascii as binascii

MAX_BYTES = 16384  # the device payload is ~350 bytes; refuse anything absurd


def split_url(url):
    """'https://host:port/path?q' -> (is_https, host, port, '/path?q')."""
    if url.startswith("https://"):
        https, rest = True, url[8:]
    elif url.startswith("http://"):
        https, rest = False, url[7:]
    else:
        raise ValueError("URL must start with http:// or https://")
    hostport, slash, path = rest.partition("/")
    host, colon, port = hostport.partition(":")
    if not host:
        raise ValueError("URL has no host")
    return https, host, int(port) if colon else (443 if https else 80), "/" + path


def build_request(host, path, headers):
    lines = ["GET %s HTTP/1.0" % path, "Host: %s" % host, "Connection: close"]
    for key in headers:
        lines.append("%s: %s" % (key, headers[key]))
    return ("\r\n".join(lines) + "\r\n\r\n").encode()


def parse_response(data):
    """Return the decoded JSON body of a 200 response, else raise OSError/ValueError."""
    head, sep, body = data.partition(b"\r\n\r\n")
    if not sep:
        raise ValueError("incomplete response")
    status_line = head.split(b"\r\n", 1)[0].split(b" ")
    if len(status_line) < 2:
        raise ValueError("bad status line")
    status = int(status_line[1])
    if status != 200:
        raise OSError("HTTP %d" % status)
    return json.loads(body)


def _der(pem):
    b64 = "".join(line for line in pem.strip().split("\n") if not line.startswith("-----"))
    return binascii.a2b_base64(b64)


_context = None


def _tls_context():
    global _context
    if _context is None:
        import tls  # MicroPython's TLS module (mbedTLS)
        from roots import ROOTS_PEM

        ctx = tls.SSLContext(tls.PROTOCOL_TLS_CLIENT)
        ctx.verify_mode = tls.CERT_REQUIRED
        for pem in ROOTS_PEM:
            ctx.load_verify_locations(cadata=_der(pem))
        _context = ctx
    return _context


def get_json(url, headers=None, timeout=8):
    https, host, port, path = split_url(url)
    addr = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)[0]
    sock = socket.socket(addr[0], socket.SOCK_STREAM, addr[2])
    sock.settimeout(timeout)
    try:
        sock.connect(addr[-1])
        if https:
            sock = _tls_context().wrap_socket(sock, server_hostname=host)
        sock.write(build_request(host, path, headers or {}))
        data = b""
        while True:
            chunk = sock.read(1024)
            if not chunk:
                break
            data += chunk
            if len(data) > MAX_BYTES:
                raise ValueError("response too large")
    finally:
        sock.close()
    return parse_response(data)
