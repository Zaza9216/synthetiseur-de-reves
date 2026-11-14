"""Parcours utilisateurs testés dans de vrais navigateurs (Chromium et WebKit).

Chaque test vérifie aussi qu'aucune erreur JavaScript ni violation de la
politique de sécurité du contenu (CSP) n'apparaît dans la console.
"""

import re
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import Page, expect

from dreams.models import Dream, Status
from tests.conftest import STRONG_PASSWORD
from tests.e2e.conftest import BrowserSession

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

# Petit fichier WAV valide (en-tête RIFF/WAVE) : seule la signature est vérifiée.
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + bytes(2000)


def sign_up(page: Page, base: str, username: str) -> None:
    """Crée un compte depuis le formulaire d'inscription."""
    page.goto(f"{base}/comptes/inscription/")
    page.fill("#id_username", username)
    page.fill("#id_email", f"{username}@example.com")
    page.fill("#id_password1", STRONG_PASSWORD)
    page.fill("#id_password2", STRONG_PASSWORD)
    page.click("button[type=submit]")
    expect(page).to_have_url(re.compile(r"/reves/$"))


def log_in(page: Page, base: str, username: str) -> None:
    """Se connecte avec un compte existant."""
    page.goto(f"{base}/comptes/connexion/")
    page.fill("#id_username", username)
    page.fill("#id_password", STRONG_PASSWORD)
    page.click("button[type=submit]")
    expect(page).to_have_url(re.compile(r"/reves/$"))


def test_parcours_complet(live_server: Any, browser_session: BrowserSession) -> None:
    """Inscription → envoi d'un rêve → résultat → mode immersif → suppression."""
    page, base = browser_session.page, live_server.url

    page.goto(base)
    expect(page.locator("h1")).to_contain_text("Synthétiseur de rêves")
    sign_up(page, base, "reveur")
    expect(page.get_by_text("Vous n'avez encore raconté aucun rêve.")).to_be_visible()

    # Envoi d'un fichier audio (onglet « Importer »), traité immédiatement par l'IA simulée.
    page.goto(f"{base}/reves/nouveau/")
    page.click("#tab-upload")
    page.set_input_files("#id_audio", {"name": "reve.wav", "mimeType": "audio/wav", "buffer": WAV})
    page.click("#btn-upload")
    expect(page).to_have_url(re.compile(r"/reves/\d+/$"))
    expect(page.locator(".dream-quote")).to_be_visible()
    expect(page.locator(".emo-badge").first).to_be_visible()

    # Mode immersif « Revivre mon rêve ».
    page.click("#relive-button")
    expect(page.locator("#relive-overlay")).to_be_visible()
    expect(page.locator("#relive-caption")).not_to_be_empty()
    page.keyboard.press("Escape")
    expect(page.locator("#relive-overlay")).to_be_hidden()

    # Non-régression #23 : la fenêtre de suppression s'ouvre vraiment au clic.
    page.click("a[data-bs-target='#delete-modal']")
    expect(page.locator("#delete-modal")).to_be_visible()
    page.locator("#delete-modal button[type=submit]").click()
    expect(page).to_have_url(re.compile(r"/reves/$"))
    expect(page.get_by_text("supprimés définitivement")).to_be_visible()
    assert not Dream.objects.exists()

    browser_session.assert_no_errors()


def test_enregistrement_au_micro(live_server: Any, chromium_session: BrowserSession) -> None:
    """Enregistrement réel avec un micro simulé par Chromium, puis envoi."""
    page, base = chromium_session.page, live_server.url
    sign_up(page, base, "micro")

    page.goto(f"{base}/reves/nouveau/")
    page.click("#btn-start")
    expect(page.locator("#btn-stop")).to_be_visible()
    expect(page.locator("#recorder-waveform")).to_be_visible()
    page.wait_for_timeout(1800)  # au moins une seconde d'audio
    expect(page.locator("#recorder-timer")).not_to_have_text("00:00")
    page.click("#btn-stop")
    expect(page.locator("#recorder-preview")).to_be_visible()
    page.click("#btn-send")

    expect(page).to_have_url(re.compile(r"/reves/\d+/$"))
    dream = Dream.objects.get()
    assert dream.status == Status.TERMINE
    assert dream.audio_duration and dream.audio_duration >= 1
    chromium_session.assert_no_errors()


def test_tableau_de_bord_filtres_et_recherche(
    live_server: Any, browser_session: BrowserSession
) -> None:
    """Statistiques, graphique, filtre par émotion et recherche."""
    page, base = browser_session.page, live_server.url
    user = get_user_model().objects.create_user("stats", "stats@example.com", STRONG_PASSWORD)
    for text, emotion in [
        ("Un chat volant", "heureux"),
        ("Un examen raté", "stressant"),
        ("Un autre examen", "stressant"),
    ]:
        Dream.objects.create(user=user, transcription=text, emotion=emotion, status=Status.TERMINE)
    log_in(page, base, "stats")

    expect(page.locator("[data-testid=stat-total]")).to_have_text("3")
    expect(page.locator("[data-testid=stat-dominant]")).to_contain_text("Stressant")
    expect(page.locator("#timeline-chart")).to_be_visible()

    page.select_option("#id_emotion", "heureux")
    page.click("button:has-text('Filtrer')")
    expect(page.locator(".dream-card")).to_have_count(1)

    page.goto(f"{base}/reves/")
    page.fill("#id_q", "examen")
    page.press("#id_q", "Enter")
    expect(page.locator(".dream-card")).to_have_count(2)
    expect(page.get_by_text("Rêves contenant « examen »")).to_be_visible()

    browser_session.assert_no_errors()


def test_pages_sans_debordement_horizontal(
    live_server: Any, browser_session: BrowserSession
) -> None:
    """Aucune page ne dépasse la largeur de l'écran (bug mobile de la barre de navigation)."""
    page, base = browser_session.page, live_server.url
    sign_up(page, base, "mobile")

    for path in ["/", "/reves/", "/reves/nouveau/", "/comptes/mes-donnees/", "/confidentialite/"]:
        page.goto(base + path)
        overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"{path} déborde de {overflow} px ({browser_session.profile})"

    browser_session.assert_no_errors()


def test_export_et_suppression_du_compte(
    live_server: Any, chromium_session: BrowserSession
) -> None:
    """RGPD : téléchargement de l'archive puis suppression du compte."""
    page, base = chromium_session.page, live_server.url
    sign_up(page, base, "rgpd")

    page.goto(f"{base}/comptes/mes-donnees/")
    with page.expect_download() as download:
        page.get_by_role("link", name="Télécharger l'archive").click()
    assert download.value.suggested_filename.startswith("mes-reves-")

    page.fill("#id_password", STRONG_PASSWORD)
    page.click("button:has-text('Supprimer définitivement mon compte')")
    expect(page.get_by_text("toutes vos données ont été supprimés")).to_be_visible()
    assert not get_user_model().objects.filter(username="rgpd").exists()
    chromium_session.assert_no_errors()
