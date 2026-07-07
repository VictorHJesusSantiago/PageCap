"""Best-effort paywall/login-wall detection: a heuristic keyword scan over
the rendered page text. This never blocks extraction — PageCap's job is to
fetch what's reachable — it only surfaces a warning so the user understands
why a job returned little or nothing (the content may be sitting behind a
subscription/login wall the crawler correctly didn't try to bypass)."""
from __future__ import annotations

from typing import Optional

from playwright.async_api import Page

_PAYWALL_KEYWORDS = [
    "subscribe to continue", "subscribe to read", "become a member",
    "unlock this article", "this content is for subscribers",
    "sign in to continue reading", "log in to continue reading",
    "assine para continuar", "torne-se assinante", "conteúdo exclusivo para assinantes",
    "faça login para continuar", "acesso restrito a assinantes",
]


async def detect_paywall(page: Page) -> Optional[str]:
    """Returns a short warning message if paywall/login-wall language is
    found in the page's visible text, or None if nothing matched."""
    try:
        text = (await page.inner_text("body"))[:8000].lower()
    except Exception:
        return None

    for keyword in _PAYWALL_KEYWORDS:
        if keyword in text:
            return f'Possível paywall/login-wall detectado (trecho: "{keyword}").'
    return None
