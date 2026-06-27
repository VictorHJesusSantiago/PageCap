"""Load cookies from browser profiles or raw cookie strings."""
from __future__ import annotations

import http.cookiejar
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import BrowserContext


def _browser_cookies(browser_name: str, domain: str, profile: Optional[str] = None) -> list[dict]:
    """Extract cookies from an installed browser for a given domain."""
    try:
        import browser_cookie3
    except ImportError:
        raise RuntimeError("browser-cookie3 is not installed. Run: pip install browser-cookie3")

    loaders = {
        "chrome": browser_cookie3.chrome,
        "firefox": browser_cookie3.firefox,
        "edge": browser_cookie3.edge,
        "brave": browser_cookie3.brave,
        "opera": browser_cookie3.opera,
        "safari": browser_cookie3.safari,
    }
    loader = loaders.get(browser_name.lower())
    if not loader:
        raise ValueError(f"Unsupported browser: {browser_name}")

    kwargs = {}
    if profile:
        kwargs["cookie_file"] = profile

    jar: http.cookiejar.CookieJar = loader(domain_name=domain, **kwargs)
    cookies = []
    for c in jar:
        cookies.append({
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "secure": c.secure,
            "httpOnly": False,
            "sameSite": "None",
        })
    return cookies


def _parse_raw_cookies(raw: str, domain: str) -> list[dict]:
    """Parse a Netscape cookie file string or plain `key=value; key2=value2` header."""
    cookies = []
    raw = raw.strip()

    if raw.startswith("#") or "\t" in raw:
        # Netscape format
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies.append({
                    "name": parts[5],
                    "value": parts[6],
                    "domain": parts[0],
                    "path": parts[2],
                    "secure": parts[3].upper() == "TRUE",
                    "httpOnly": False,
                    "sameSite": "None",
                })
    else:
        # key=value; key2=value2 (HTTP header style)
        for pair in raw.split(";"):
            pair = pair.strip()
            if "=" in pair:
                k, _, v = pair.partition("=")
                cookies.append({
                    "name": k.strip(),
                    "value": v.strip(),
                    "domain": domain,
                    "path": "/",
                    "secure": False,
                    "httpOnly": False,
                    "sameSite": "None",
                })
    return cookies


async def load_cookies(
    context: BrowserContext,
    url: str,
    raw: Optional[str] = None,
    browser_name: Optional[str] = None,
    profile: Optional[str] = None,
) -> int:
    """Add cookies to a Playwright context. Returns number of cookies added."""
    parsed = urlparse(url)
    domain = parsed.netloc.lstrip("www.")

    cookies: list[dict] = []

    if raw:
        cookies = _parse_raw_cookies(raw, domain)
    elif browser_name:
        cookies = _browser_cookies(browser_name, domain, profile)

    if cookies:
        await context.add_cookies(cookies)
    return len(cookies)
