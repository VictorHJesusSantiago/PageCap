"""
Apply username/password credentials via Playwright auto-login.
Supports manual CAPTCHA/2FA: opens a visible browser and waits for the
user to solve the challenge, then continues automatically.
"""
from __future__ import annotations

import asyncio
from typing import Callable, Optional

from playwright.async_api import Page


_USERNAME_SELECTORS = [
    'input[type="email"]',
    'input[autocomplete="username"]',
    'input[autocomplete="email"]',
    'input[name="username"]',
    'input[name="email"]',
    'input[name="user"]',
    'input[id="username"]',
    'input[id="email"]',
    'input[id="user"]',
    'input[type="text"][name*="user"]',
    'input[type="text"][name*="email"]',
    'input[type="text"][id*="user"]',
    'input[type="text"][id*="email"]',
    'input[type="text"]',  # last resort
]

_PASSWORD_SELECTORS = [
    'input[type="password"]',
    'input[name="password"]',
    'input[name="pass"]',
    'input[id="password"]',
    'input[autocomplete="current-password"]',
]

_SUBMIT_SELECTORS = [
    'button[type="submit"]',
    'input[type="submit"]',
    'button:has-text("Login")',
    'button:has-text("Sign in")',
    'button:has-text("Log in")',
    'button:has-text("Entrar")',
    'button:has-text("Acessar")',
    'button:has-text("Continue")',
    'button:has-text("Next")',
    '[role="button"]:has-text("Login")',
    '[role="button"]:has-text("Sign in")',
]


async def apply_credentials(
    page: Page,
    url: str,
    username: str,
    password: str,
    manual_captcha: bool = False,
    captcha_timeout: int = 120,
    on_captcha_detected: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Navigate to URL and attempt automated login.

    If `manual_captcha=True` and a CAPTCHA/2FA is detected (or login fails),
    the browser stays open and visible so the user can solve it manually.
    The function waits up to `captcha_timeout` seconds for the user to complete
    authentication, then continues.

    Returns True if login was attempted.
    """
    await page.goto(url, wait_until="networkidle", timeout=30000)

    username_field = await _find_first(page, _USERNAME_SELECTORS)
    password_field = await _find_first(page, _PASSWORD_SELECTORS)

    if not username_field or not password_field:
        if manual_captcha:
            # No standard form found — let user navigate manually
            if on_captcha_detected:
                on_captcha_detected("Formulário de login não encontrado. Faça login manualmente no browser.")
            await _wait_for_navigation(page, captcha_timeout)
        return False

    await username_field.fill(username)
    await asyncio.sleep(0.4)
    await password_field.fill(password)
    await asyncio.sleep(0.4)

    clicked = False
    for sel in _SUBMIT_SELECTORS:
        try:
            btn = await page.query_selector(sel)
            if btn:
                await btn.click()
                clicked = True
                break
        except Exception:
            continue

    if not clicked:
        await password_field.press("Enter")

    try:
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass

    # Detect CAPTCHA / 2FA challenges on resulting page via DOM selectors
    # (avoid full-page text scan which produces false positives from page copy/scripts)
    _challenge_selectors = [
        "iframe[src*='recaptcha']", "iframe[src*='hcaptcha']",
        ".g-recaptcha", ".h-captcha",
        "input[name='cf-turnstile-response']",
        "input[name='otp']", "input[autocomplete='one-time-code']",
    ]
    has_challenge = any(await page.query_selector(sel) for sel in _challenge_selectors)

    if has_challenge and manual_captcha:
        if on_captcha_detected:
            on_captcha_detected(
                "CAPTCHA ou 2FA detectado. Resolva no browser e aguarde continuar automaticamente."
            )
        # Wait until user passes the challenge (URL or DOM changes away from challenge)
        await _wait_for_challenge_done(page, captcha_timeout)

    return True


async def _find_first(page: Page, selectors: list[str]):
    for sel in selectors:
        try:
            el = await page.wait_for_selector(sel, timeout=1500, state="visible")
            if el:
                return el
        except Exception:
            continue
    return None


async def _wait_for_navigation(page: Page, timeout: int):
    """Wait for user to manually navigate (URL change or load)."""
    initial_url = page.url
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        await asyncio.sleep(2)
        if page.url != initial_url:
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            return


async def _wait_for_challenge_done(page: Page, timeout: int):
    """Wait until CAPTCHA/2FA indicators disappear from the page."""
    captcha_selectors = [
        "iframe[src*='recaptcha']", "iframe[src*='hcaptcha']",
        ".g-recaptcha", ".h-captcha",
        "input[name='cf-turnstile-response']",
    ]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        await asyncio.sleep(2)
        try:
            challenge_present = any(await page.query_selector(sel) for sel in captcha_selectors)
            if not challenge_present:
                await page.wait_for_load_state("networkidle", timeout=5000)
                return
        except Exception:
            continue
