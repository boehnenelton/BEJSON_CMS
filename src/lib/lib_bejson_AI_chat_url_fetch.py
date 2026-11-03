"""
Library:         lib_bejson_AI_chat_url_fetch.py
Family:          AI
Module Purpose:  Server-side URL proxy for chat "URL context": fetches pages (CORS-free), strips HTML to text, and refuses private/loopback/link-local targets (SSRF guard) including across redirects.
Architecture:    Stdlib only. Pure functions; limits are arguments (the app reads them from its BEJSON config). Each requested item yields {url, label, text, error}.
Version:         1.0.0
Release_Version: 300
Date:            2026-10-28
Author:          Elton Boehnen · boehnenelton2024@gmail.com · boehnenelton2024.pages.dev · github.com/boehnenelton
Format_Creator:  Elton Boehnen
RELATIONAL_ID:   ee32f853-12a2-4940-92e4-a9196c145c76

Changelog:
  1.0.0 (2026-10-28) -- Initial creation (extension of the AI family; no existing AI library modified).
"""

import ipaddress
import logging
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

logger = logging.getLogger("lib_bejson_AI_chat_url_fetch")

VERSION = "1.0.0"
USER_AGENT = "Mozilla/5.0 (compatible; BEJSON-Chat/4.1)"


# True when `host` resolves ONLY to public addresses.
def url_fetch_host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
            return False
    return True


def _check_url(url: str, block_private: bool) -> None:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Invalid URL")
    if block_private and not url_fetch_host_is_public(parts.hostname):
        raise ValueError("Blocked: private or local address")


class _GuardedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, block_private: bool) -> None:
        self._block_private = block_private

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl, self._block_private)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def url_fetch_html_to_text(decoded: str) -> str:
    decoded = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", decoded, flags=re.IGNORECASE)
    decoded = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", decoded, flags=re.IGNORECASE)
    decoded = re.sub(r"<[^>]+>", " ", decoded)
    return re.sub(r"\s{2,}", " ", decoded).strip()


def url_fetch_one(url: str, *, timeout: float = 8.0, max_bytes: int = 80_000, max_chars: int = 8000,
                  block_private: bool = True) -> str:
    _check_url(url, block_private)
    opener = urllib.request.build_opener(_GuardedRedirect(block_private))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener.open(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read(max_bytes)
    decoded = raw.decode("utf-8", errors="replace")
    if "html" in content_type.lower():
        decoded = url_fetch_html_to_text(decoded)
    return decoded[:max_chars]


def url_fetch_many(items: List[Dict[str, Any]], *, max_urls: int = 6, timeout: float = 8.0, max_bytes: int = 80_000,
                   max_chars: int = 8000, block_private: bool = True) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    for item in (items or [])[:max_urls]:
        url = str((item or {}).get("url") or "").strip()
        label = (item or {}).get("label") or url
        try:
            text = url_fetch_one(url, timeout=timeout, max_bytes=max_bytes, max_chars=max_chars, block_private=block_private)
            results.append({"url": url, "label": label, "text": text, "error": None})
        except Exception as e:
            logger.info("URL fetch failed for %s: %s", urllib.parse.urlsplit(url).netloc, e)
            results.append({"url": url, "label": label, "text": "", "error": str(e)[:120]})
    return results
