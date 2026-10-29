"""Real Caddy proxy checks. Set CADDY_BIN to a Caddy 2.11.7 executable."""

import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from scripts.check_deployment import deployment_urls, validate_domain


@pytest.mark.parametrize("value", ["https://api.example.com", "api.example.com/path", "api.example.com:443", "127.0.0.1", "api..example.com", "api.example.com\n}"])
def test_reject_unsafe_domain(value):
    with pytest.raises(ValueError):
        validate_domain(value)


def test_require_distinct_https_roots():
    assert deployment_urls({"API_DOMAIN": "API.example.com", "MINIO_PUBLIC_URL": "https://images.example.com"}) == ("https://api.example.com", "https://images.example.com")
    for url in ("http://images.example.com", "https://images.example.com/path", "https://api.example.com"):
        with pytest.raises(ValueError):
            deployment_urls({"API_DOMAIN": "api.example.com", "MINIO_PUBLIC_URL": url})


@pytest.mark.parametrize("peer,expected", [("172.30.88.2", "198.51.100.7"), ("172.30.88.3", "172.30.88.3")])
async def test_uvicorn_trusts_only_caddy(peer, expected):
    async def echo(scope, receive, send):
        request = Request(scope)
        await JSONResponse({"ip": request.client.host, "scheme": request.url.scheme})(scope, receive, send)

    app = ProxyHeadersMiddleware(echo, trusted_hosts=["172.30.88.2"])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app, client=(peer, 1234)), base_url="http://test") as client:
        response = await client.get("/", headers={"X-Forwarded-For": "198.51.100.7", "X-Forwarded-Proto": "https"})
    assert response.json() == {"ip": expected, "scheme": "https" if peer == "172.30.88.2" else "http"}


@pytest.fixture(scope="module")
def proxy(tmp_path_factory):
    binary = os.environ.get("CADDY_BIN") or shutil.which("caddy")
    if not binary:
        pytest.skip("Set CADDY_BIN to run real Caddy integration checks")

    release_stream = threading.Event()

    class Upstream(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path == "/api/v1/records/recognize/stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(b"data: first\n\n")
                self.wfile.flush()
                release_stream.wait(5)
                return
            body = json.dumps({"host": self.headers["Host"], "path": self.path, "ip": self.headers.get("X-Forwarded-For")}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            # Read the entire body to exercise Caddy's streaming size limit.
            if self.headers.get("Transfer-Encoding") == "chunked":
                while True:
                    line = self.rfile.readline()
                    if not line:
                        return
                    size = int(line.split(b";", 1)[0], 16)
                    if not size:
                        self.rfile.readline()
                        break
                    if len(self.rfile.read(size)) != size:
                        return
                    self.rfile.read(2)
            remaining = int(self.headers.get("Content-Length", "0"))
            while remaining:
                chunk = self.rfile.read(min(65536, remaining))
                if not chunk:
                    return
                remaining -= len(chunk)
            self.send_response(204)
            self.end_headers()

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    with socket.socket() as available:
        available.bind(("127.0.0.1", 0))
        port = available.getsockname()[1]
    directory = tmp_path_factory.mktemp("caddy")
    config = Path(__file__).resolve().parents[1].joinpath("caddy/Caddyfile").read_text(encoding="utf-8")
    config = config.replace("email {$ACME_EMAIL}", "admin off\n\tauto_https off")
    config = config.replace("{$API_DOMAIN}", f"http://api.example.test:{port}")
    config = config.replace("{$IMAGES_DOMAIN}", f"http://images.example.test:{port}")
    config = config.replace("app:8000", f"127.0.0.1:{upstream.server_port}")
    config = config.replace("minio:9000", f"127.0.0.1:{upstream.server_port}")
    config = config.replace("import /etc/caddy/tls/api/*.caddy", "").replace("import /etc/caddy/tls/images/*.caddy", "")
    path = directory / "Caddyfile"
    path.write_text(config, encoding="utf-8")
    with (directory / "caddy.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen([binary, "run", "--config", str(path), "--adapter", "caddyfile"], stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=10) as client:
                for _ in range(100):
                    try:
                        client.get("/health", headers={"Host": f"api.example.test:{port}"}).raise_for_status()
                        break
                    except httpx.HTTPError:
                        if process.poll() is not None:
                            pytest.fail((directory / "caddy.log").read_text(encoding="utf-8"))
                        time.sleep(0.05)
                else:
                    pytest.fail("Caddy did not start")
                yield client, port, release_stream
        finally:
            release_stream.set()
            process.terminate()
            process.wait(timeout=10)
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=5)


def test_image_signature_components_preserved(proxy):
    client, port, _ = proxy
    path = "/smartdiet/users/test/a%20photo.jpg?X-Amz-Signature=abc123&X-Amz-Credential=test%2Fregion"
    host = f"images.example.test:{port}"
    result = client.get(path, headers={"Host": host}).json()
    assert result["host"] == host
    assert result["path"] == path


def test_caddy_discards_spoofed_forwarded_ip(proxy):
    client, port, _ = proxy
    response = client.get("/health", headers={"Host": f"api.example.test:{port}", "X-Forwarded-For": "198.51.100.99"})
    assert response.json()["ip"] == "127.0.0.1"


@pytest.mark.parametrize("path,limit", [("/api/v1/upload", 11 * 1024 * 1024), ("/api/v1/upload/", 11 * 1024 * 1024), ("/api/v1/upload/images", 61 * 1024 * 1024), ("/api/v1/upload/images/", 61 * 1024 * 1024)])
def test_upload_body_limits(proxy, path, limit):
    client, port, _ = proxy
    headers = {"Host": f"api.example.test:{port}"}
    assert client.post(path, content=b"x" * limit, headers=headers).status_code == 204
    assert client.post(path, content=b"x" * (limit + 1), headers=headers).status_code == 413


def test_chunked_upload_cannot_bypass_body_limit(proxy):
    client, port, _ = proxy

    def chunks():
        for _ in range(176):
            yield b"x" * 65536
        yield b"x"

    response = client.post("/api/v1/upload", content=chunks(), headers={"Host": f"api.example.test:{port}"})
    assert response.status_code == 413


def test_sse_first_event_arrives_before_upstream_finishes(proxy):
    client, port, release = proxy
    started = time.monotonic()
    try:
        with client.stream("GET", "/api/v1/records/recognize/stream", headers={"Host": f"api.example.test:{port}"}) as response:
            assert response.status_code == 200
            assert next(response.iter_lines()) == "data: first"
            assert time.monotonic() - started < 3
            assert not release.is_set()
    finally:
        release.set()
