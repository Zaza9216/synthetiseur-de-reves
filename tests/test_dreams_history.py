"""Tests du modèle ``Dream`` et de l'historique des rêves."""

import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from dreams.models import (
    EMOTION_STYLES,
    UNKNOWN_EMOTION_STYLE,
    Dream,
    Emotion,
    Status,
    audio_upload_path,
)
from tests.conftest import STRONG_PASSWORD, fake_audio

MakeDream = Callable[..., Dream]


# --- Modèle ------------------------------------------------------------------------


def test_title_uses_first_words_of_transcription(user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user, transcription="un deux trois quatre cinq six sept huit neuf dix")

    assert dream.title == "un deux trois quatre cinq six sept huit…"
    assert str(dream) == dream.title


def test_title_falls_back_to_date_without_transcription(user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user, transcription="")
    dream.created_at = timezone.make_aware(datetime(2026, 11, 13, 8, 0))

    assert dream.title == "Rêve du 13 novembre 2026"


def test_title_of_unsaved_dream() -> None:
    assert Dream().title == "Nouveau rêve"


def test_every_emotion_has_a_style() -> None:
    assert set(EMOTION_STYLES) == set(Emotion.values)


def test_emotion_style_and_percent(user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user, emotion=Emotion.STRESSANT, emotion_score=0.734)

    assert dream.emotion_style == EMOTION_STYLES[Emotion.STRESSANT]
    assert dream.emotion_percent == 73


def test_unknown_emotion_style_and_missing_score(user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user, emotion="", emotion_score=None)

    assert dream.emotion_style == UNKNOWN_EMOTION_STYLE
    assert dream.emotion_percent is None


@pytest.mark.parametrize(
    ("status", "processing"),
    [
        (Status.EN_ATTENTE, True),
        (Status.TRANSCRIPTION, True),
        (Status.GENERATION, True),
        (Status.TERMINE, False),
        (Status.ECHEC, False),
    ],
)
def test_is_processing(user: Any, make_dream: MakeDream, status: str, processing: bool) -> None:
    assert make_dream(user, status=status).is_processing is processing


def test_audio_path_is_anonymous() -> None:
    path = audio_upload_path(Dream(), "Rêve de Bob - secret.MP3")

    assert re.fullmatch(r"dreams/audio/\d{4}/\d{2}/[0-9a-f]{32}\.mp3", path)
    assert "Bob" not in path


def test_dreams_are_ordered_newest_first(user: Any, make_dream: MakeDream) -> None:
    old = make_dream(user)
    new = make_dream(user)
    Dream.objects.filter(pk=old.pk).update(created_at=timezone.now() - timezone.timedelta(days=1))

    assert list(Dream.objects.all()) == [new, old]


# --- Liste ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_requires_login(client: Client) -> None:
    response = client.get(reverse("dreams:list"))

    assert response.status_code == 302
    assert reverse("accounts:login") in response.url


def test_list_shows_only_my_dreams(
    client: Client, user: Any, other_user: Any, make_dream: MakeDream
) -> None:
    mine = make_dream(user, transcription="Mon rêve à moi")
    make_dream(other_user, transcription="Le rêve secret de quelqu'un d'autre")
    client.force_login(user)

    response = client.get(reverse("dreams:list"))

    assert list(response.context["dreams"]) == [mine]
    assert "Le rêve secret" not in response.content.decode()


def test_list_empty_state(client: Client, user: Any) -> None:
    client.force_login(user)

    response = client.get(reverse("dreams:list"))

    assert "Vous n'avez encore raconté aucun rêve." in response.content.decode()


def test_list_is_paginated(client: Client, user: Any, make_dream: MakeDream) -> None:
    for _ in range(10):
        make_dream(user)
    client.force_login(user)

    first = client.get(reverse("dreams:list"))
    second = client.get(reverse("dreams:list"), {"page": 2})

    assert len(first.context["dreams"]) == 9
    assert len(second.context["dreams"]) == 1
    assert "Page 1 / 2" in first.content.decode()


def test_list_shows_emotion_and_processing_status(
    client: Client, user: Any, make_dream: MakeDream
) -> None:
    make_dream(user, emotion=Emotion.STRESSANT, emotion_score=0.9)
    make_dream(user, emotion="", status=Status.TRANSCRIPTION)
    client.force_login(user)

    html = client.get(reverse("dreams:list")).content.decode()

    assert "Stressant · 90 %" in html
    assert "Transcription en cours" in html


def test_login_redirects_to_dream_list(client: Client, user: Any) -> None:
    response = client.post(
        reverse("accounts:login"), {"username": "bob", "password": STRONG_PASSWORD}
    )

    assert response.url == reverse("dreams:list")


# --- Détail --------------------------------------------------------------------------


def test_detail_shows_my_dream(client: Client, user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user, audio=fake_audio())
    client.force_login(user)

    response = client.get(reverse("dreams:detail", args=[dream.pk]))
    html = response.content.decode()

    assert response.status_code == 200
    assert "ville de verre" in html
    assert "<audio" in html


def test_detail_of_someone_elses_dream_returns_404(
    client: Client, user: Any, other_user: Any, make_dream: MakeDream
) -> None:
    dream = make_dream(other_user)
    client.force_login(user)

    response = client.get(reverse("dreams:detail", args=[dream.pk]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_detail_requires_login(client: Client, user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user)

    response = client.get(reverse("dreams:detail", args=[dream.pk]))

    assert response.status_code == 302


def test_detail_shows_error_message_on_failure(
    client: Client, user: Any, make_dream: MakeDream
) -> None:
    dream = make_dream(
        user, status=Status.ECHEC, transcription="", error_message="Service indisponible"
    )
    client.force_login(user)

    html = client.get(reverse("dreams:detail", args=[dream.pk])).content.decode()

    assert "Service indisponible" in html
    assert "La transcription n'est pas encore disponible." in html
