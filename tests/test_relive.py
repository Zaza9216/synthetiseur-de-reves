"""Tests du mode immersif « Revivre mon rêve » (bonus : micro-vidéo et ambiance sonore)."""

from collections.abc import Callable
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from dreams.models import Dream, Status

MakeDream = Callable[..., Dream]


def detail_html(client: Client, dream: Dream) -> str:
    return client.get(reverse("dreams:detail", args=[dream.pk])).content.decode()


def test_finished_dream_offers_relive_mode(
    client: Client, user: Any, make_dream: MakeDream
) -> None:
    dream = make_dream(user, emotion="stressant", transcription="Je tombais. Puis je volais.")
    client.force_login(user)

    html = detail_html(client, dream)

    assert 'id="relive-button"' in html
    assert 'id="relive-overlay"' in html
    assert 'data-emotion="stressant"' in html
    assert 'data-story="Je tombais. Puis je volais."' in html
    assert "js/ambience.js" in html


@pytest.mark.parametrize(
    "fields",
    [{"status": Status.TRANSCRIPTION}, {"status": Status.ECHEC}, {"transcription": ""}],
)
def test_no_relive_mode_before_the_dream_is_ready(
    client: Client, user: Any, make_dream: MakeDream, fields: dict[str, Any]
) -> None:
    dream = make_dream(user, **fields)
    client.force_login(user)

    html = detail_html(client, dream)

    assert 'id="relive-button"' not in html
    assert "js/ambience.js" not in html


def test_story_is_escaped_in_relive_overlay(
    client: Client, user: Any, make_dream: MakeDream
) -> None:
    dream = make_dream(user, transcription='Un rêve "étrange" <script>alert(1)</script>')
    client.force_login(user)

    html = detail_html(client, dream)

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_relive_without_image_uses_placeholder(
    client: Client, user: Any, make_dream: MakeDream
) -> None:
    dream = make_dream(user)
    client.force_login(user)

    html = detail_html(client, dream)
    overlay = html.split('id="relive-overlay"', 1)[1]

    assert "relive-image dream-placeholder" in overlay
