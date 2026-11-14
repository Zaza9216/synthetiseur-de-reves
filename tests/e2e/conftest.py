"""Configuration des tests de bout en bout (vrais navigateurs, Playwright).

Lancement : ``uv run pytest -m e2e --no-cov`` (navigateurs installés une fois avec
``uv run playwright install chromium webkit``).
"""

import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from playwright.sync_api import Browser, ConsoleMessage, Page, Playwright, sync_playwright
from pytest_django.fixtures import Settings

# L'API synchrone de Playwright fait tourner une boucle asyncio dans le fil principal :
# Django refuserait sinon les accès à la base depuis les tests.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

# Messages internes des navigateurs, sans rapport avec l'application :
# WebKit sans affichage ne trouve pas les icônes de ses propres contrôles audio.
BROWSER_NOISE = ("Button failed to load, iconName",)

PROFILES: dict[str, dict[str, Any]] = {
    "chromium-ordinateur": {"engine": "chromium", "device": None},
    "chromium-android": {"engine": "chromium", "device": "Pixel 7"},
    "webkit-iphone": {"engine": "webkit", "device": "iPhone 13"},
}


@dataclass
class BrowserSession:
    """Une page de navigateur et les problèmes relevés dans sa console."""

    page: Page
    profile: str
    errors: list[str] = field(default_factory=list)

    def assert_no_errors(self) -> None:
        """Échoue si une erreur JavaScript ou une violation CSP a été relevée."""
        assert not self.errors, "Erreurs dans la console :\n" + "\n".join(self.errors)


@pytest.fixture(autouse=True)
def _e2e_settings(settings: Settings) -> None:
    """Traitement immédiat avec l'IA simulée, cookies utilisables en HTTP."""
    settings.DREAM_PROCESSING_MODE = "sync"
    settings.AI_BACKEND = "fake"
    settings.AI_FAKE_LATENCY_SCALE = 0
    settings.SESSION_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SECURE = False


@pytest.fixture(scope="session")
def playwright_instance() -> Iterator[Playwright]:
    """Instance Playwright partagée par toute la session de tests."""
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def browsers(playwright_instance: Playwright) -> Iterator[dict[str, Browser]]:
    """Chromium (avec micro simulé) et WebKit, lancés une seule fois."""
    launched = {
        "chromium": playwright_instance.chromium.launch(
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"]
        ),
        "webkit": playwright_instance.webkit.launch(),
    }
    yield launched
    for browser in launched.values():
        browser.close()


def _open_session(
    playwright: Playwright, browsers: dict[str, Browser], profile: str
) -> BrowserSession:
    config = PROFILES[profile]
    options: dict[str, Any] = {"locale": "fr-FR"}
    if config["device"]:
        options.update(playwright.devices[config["device"]])
    if config["engine"] == "chromium":
        options["permissions"] = ["microphone"]
    context = browsers[config["engine"]].new_context(**options)
    context.set_default_timeout(15_000)
    page = context.new_page()
    session = BrowserSession(page=page, profile=profile)

    def on_console(message: ConsoleMessage) -> None:
        text = message.text
        if any(noise in text for noise in BROWSER_NOISE):
            return
        if message.type == "error" or "Content Security Policy" in text or "Refused to" in text:
            session.errors.append(f"[{message.type}] {text}")

    page.on("console", on_console)
    page.on("pageerror", lambda error: session.errors.append(f"[exception] {error}"))
    return session


@pytest.fixture(params=list(PROFILES))
def browser_session(
    request: pytest.FixtureRequest, playwright_instance: Playwright, browsers: dict[str, Browser]
) -> Iterator[BrowserSession]:
    """Session de navigation, répétée pour chaque profil (ordinateur, Android, iPhone)."""
    session = _open_session(playwright_instance, browsers, request.param)
    yield session
    session.page.context.close()


@pytest.fixture
def chromium_session(
    playwright_instance: Playwright, browsers: dict[str, Browser]
) -> Iterator[BrowserSession]:
    """Session Chromium seule (micro simulé disponible)."""
    session = _open_session(playwright_instance, browsers, "chromium-ordinateur")
    yield session
    session.page.context.close()
