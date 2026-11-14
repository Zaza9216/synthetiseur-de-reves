"""Tests de la recherche dans les rêves et de l'application installable (PWA)."""

import json
from collections.abc import Callable
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from dreams.models import Dream

MakeDream = Callable[..., Dream]


# --- Recherche ------------------------------------------------------------------------


def test_search_filters_dreams_by_text(client: Client, user: Any, make_dream: MakeDream) -> None:
    cat = make_dream(user, transcription="Mon chat parlait japonais.")
    make_dream(user, transcription="Je nageais dans la mer.")
    client.force_login(user)

    response = client.get(reverse("dreams:list"), {"q": "CHAT"})

    assert list(response.context["dreams"]) == [cat]
    assert "Rêves contenant « CHAT »" in response.content.decode()


def test_search_combines_with_emotion(client: Client, user: Any, make_dream: MakeDream) -> None:
    make_dream(user, transcription="Un chat heureux", emotion="heureux")
    sad_cat = make_dream(user, transcription="Un chat perdu", emotion="triste")
    client.force_login(user)

    response = client.get(reverse("dreams:list"), {"q": "chat", "emotion": "triste"})

    assert list(response.context["dreams"]) == [sad_cat]


def test_search_never_returns_other_users_dreams(
    client: Client, user: Any, other_user: Any, make_dream: MakeDream
) -> None:
    make_dream(other_user, transcription="Le chat d'Ève")
    client.force_login(user)

    assert list(client.get(reverse("dreams:list"), {"q": "chat"}).context["dreams"]) == []


def test_search_is_kept_in_pagination_and_presets(
    client: Client, user: Any, make_dream: MakeDream
) -> None:
    for _ in range(10):
        make_dream(user, transcription="Un rêve de chat")
    client.force_login(user)

    html = client.get(reverse("dreams:list"), {"q": "chat"}).content.decode()

    assert "q=chat&amp;page=2" in html
    assert "&amp;q=chat" in html


# --- Application installable ------------------------------------------------------------


@pytest.mark.django_db
def test_manifest(client: Client) -> None:
    response = client.get(reverse("core:manifest"))
    manifest = json.loads(response.content)

    assert response["Content-Type"] == "application/manifest+json"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/reves/"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(icon.get("purpose") == "maskable" for icon in manifest["icons"])


@pytest.mark.django_db
def test_service_worker_is_served_from_root_and_never_caches_private_pages(client: Client) -> None:
    response = client.get("/sw.js")
    script = response.content.decode()

    assert response["Content-Type"] == "application/javascript"
    assert response["Service-Worker-Allowed"] == "/"
    assert "no-cache" in response["Cache-Control"]
    assert "/hors-ligne/" in script
    assert "/reves/" not in script.split("PRECACHE = [", 1)[1].split("]", 1)[0]


@pytest.mark.django_db
def test_offline_page(client: Client) -> None:
    response = client.get(reverse("core:offline"))

    assert response.status_code == 200
    assert "Vous êtes hors ligne" in response.content.decode()


@pytest.mark.django_db
def test_pages_declare_pwa_and_ios_metadata(client: Client) -> None:
    html = client.get(reverse("core:home")).content.decode()

    assert 'rel="manifest"' in html
    assert "apple-touch-icon" in html
    assert 'name="apple-mobile-web-app-capable" content="yes"' in html
    assert "js/pwa.js" in html
