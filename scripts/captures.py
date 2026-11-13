"""Captures d'écran des pages principales, sur ordinateur et sur mobile (Playwright).

Prérequis : serveur local lancé et utilisateur de démonstration créé.
    uv run python manage.py seed_demo_dreams
    uv run python manage.py runserver 8765
    uv run playwright install chromium        # une seule fois
    uv run python scripts/captures.py docs/captures apres <id_rêve_avec_image>
"""

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("CAPTURE_BASE_URL", "http://127.0.0.1:8765")
USERNAME = os.environ.get("CAPTURE_USER", "demo")
PASSWORD = os.environ.get("CAPTURE_PASSWORD", "Demo-Reves-2026!")
VIEWPORTS = {"desktop": {"width": 1366, "height": 900}, "mobile": {"width": 390, "height": 844}}


def main(output: Path, prefix: str, dream_id: str) -> None:
    """Prend une capture de chaque page principale pour chaque taille d'écran."""
    output.mkdir(parents=True, exist_ok=True)
    pages = [
        ("accueil", "/", False),
        ("connexion", "/comptes/connexion/", False),
        ("tableau", "/reves/", True),
        ("detail", f"/reves/{dream_id}/", True),
        ("nouveau", "/reves/nouveau/", True),
        ("supervision", "/supervision/?fenetre=30j", True),
    ]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for device, viewport in VIEWPORTS.items():
            context = browser.new_context(viewport=viewport, locale="fr-FR")
            page = context.new_page()
            for name, url, needs_login in pages:
                logged_in = any(c["name"] == "sessionid" for c in context.cookies())
                if needs_login and not logged_in:
                    page.goto(f"{BASE_URL}/comptes/connexion/")
                    page.fill("#id_username", USERNAME)
                    page.fill("#id_password", PASSWORD)
                    page.click("button[type=submit]")
                    page.wait_for_load_state("networkidle")
                page.goto(BASE_URL + url)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(700)  # animations et graphique
                page.screenshot(
                    path=output / f"{prefix}-{device}-{name}.png",
                    full_page=device == "desktop" and name == "tableau",
                )
        browser.close()


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "1")
