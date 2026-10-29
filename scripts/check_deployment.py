"""Validate public hostnames and optionally probe the public TLS endpoints."""

import argparse
import ipaddress
import json
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def validate_domain(value: str) -> str:
    """Accept a public DNS hostname, never Caddyfile syntax or an IP address."""
    if len(value) > 253 or "." not in value:
        raise ValueError("Use a public DNS hostname without a scheme, port or path")
    if any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in value.split(".")):
        raise ValueError("Use a public DNS hostname without a scheme, port or path")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value.lower()
    raise ValueError("A public DNS hostname is required; IP addresses are not supported")


def deployment_urls(environ: dict[str, str]) -> tuple[str, str]:
    api = validate_domain(environ["API_DOMAIN"])
    images = urlsplit(environ["MINIO_PUBLIC_URL"])
    image_domain = validate_domain(images.netloc)
    if images.scheme != "https" or images.path or images.query or images.fragment:
        raise ValueError("MINIO_PUBLIC_URL must be an HTTPS root URL with no path")
    if api == image_domain:
        raise ValueError("API_DOMAIN and IMAGES_DOMAIN must be different hostnames")
    return f"https://{api}", f"https://{image_domain}"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe(api: str, images: str) -> None:
    # Default TLS verification is intentional: never accept an invalid certificate.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    for root, path in ((api, "/health"), (images, "/minio/health/live")):
        url = root + path
        with opener.open(url, timeout=5) as response:
            if response.status != 200:
                raise ValueError(f"Unexpected HTTPS status for {url}: {response.status}")
            if root == api:
                body = json.load(response)
                if body.get("code") != 0 or (body.get("data") or {}).get("status") != "ok":
                    raise ValueError("Public API health payload is invalid")
        try:
            opener.open("http://" + root.removeprefix("https://") + path, timeout=5).close()
        except urllib.error.HTTPError as redirect:
            if redirect.code not in (301, 308) or redirect.headers.get("Location") != url:
                raise ValueError(f"HTTP must redirect to {url}") from redirect
        else:
            raise ValueError(f"HTTP must redirect to {url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--https", action="store_true", help="also verify public HTTPS and HTTP redirects")
    parser.add_argument("--timeout", type=int, default=180, help="seconds to wait for initial certificate issuance")
    args = parser.parse_args()
    api, images = deployment_urls(dict(os.environ))
    print(f"Deployment hostnames valid: {api}, {images}", flush=True)
    if not args.https:
        return
    deadline = time.monotonic() + args.timeout
    while True:
        try:
            probe(api, images)
            print("Public API, image HTTPS and HTTP redirects verified.", flush=True)
            return
        except (OSError, ValueError) as error:
            if time.monotonic() >= deadline:
                raise SystemExit(f"Public HTTPS verification failed: {error}") from error
            time.sleep(3)


if __name__ == "__main__":
    main()
