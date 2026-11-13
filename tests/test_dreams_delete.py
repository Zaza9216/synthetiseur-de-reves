"""Tests de la suppression d'un rêve et de ses fichiers (droit à l'effacement)."""

import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client
from django.urls import reverse

from dreams.models import Dream
from tests.conftest import fake_audio

MakeDream = Callable[..., Dream]


@pytest.fixture
def dream_with_files(user: Any, make_dream: MakeDream) -> Dream:
    """Rêve possédant un fichier audio et une image sur le disque."""
    dream = make_dream(user, audio=fake_audio())
    dream.image.save("image.png", ContentFile(b"fake-png"), save=True)
    assert default_storage.exists(dream.audio.name)
    assert default_storage.exists(dream.image.name)
    return dream


def test_confirmation_page_is_shown_before_deleting(
    client: Client, user: Any, dream_with_files: Dream
) -> None:
    client.force_login(user)

    response = client.get(reverse("dreams:delete", args=[dream_with_files.pk]))

    assert response.status_code == 200
    assert "Supprimer ce rêve ?" in response.content.decode()
    assert Dream.objects.filter(pk=dream_with_files.pk).exists()


def test_delete_removes_dream_and_its_files(
    client: Client, user: Any, dream_with_files: Dream
) -> None:
    audio_name, image_name = dream_with_files.audio.name, dream_with_files.image.name
    client.force_login(user)

    response = client.post(reverse("dreams:delete", args=[dream_with_files.pk]), follow=True)

    assert response.redirect_chain[-1][0] == reverse("dreams:list")
    assert "supprimés définitivement" in response.content.decode()
    assert not Dream.objects.filter(pk=dream_with_files.pk).exists()
    assert not default_storage.exists(audio_name)
    assert not default_storage.exists(image_name)


def test_cannot_delete_someone_elses_dream(
    client: Client, other_user: Any, dream_with_files: Dream
) -> None:
    client.force_login(other_user)

    response = client.post(reverse("dreams:delete", args=[dream_with_files.pk]))

    assert response.status_code == 404
    assert Dream.objects.filter(pk=dream_with_files.pk).exists()
    assert default_storage.exists(dream_with_files.audio.name)


def test_delete_requires_login(client: Client, dream_with_files: Dream) -> None:
    response = client.post(reverse("dreams:delete", args=[dream_with_files.pk]))

    assert response.status_code == 302
    assert Dream.objects.filter(pk=dream_with_files.pk).exists()


def test_deleting_user_account_removes_dream_files(user: Any, dream_with_files: Dream) -> None:
    audio_name = dream_with_files.audio.name

    user.delete()

    assert not Dream.objects.exists()
    assert not default_storage.exists(audio_name)


def test_dream_without_files_can_be_deleted(user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user)

    dream.delete()

    assert not Dream.objects.exists()


def test_storage_error_is_logged_and_does_not_block_deletion(
    user: Any, dream_with_files: Dream, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        patch.object(default_storage, "delete", side_effect=OSError("disque plein")),
        caplog.at_level(logging.ERROR),
    ):
        dream_with_files.delete()

    assert not Dream.objects.exists()
    assert "Impossible de supprimer le fichier" in caplog.text


def test_detail_page_offers_delete_button(
    client: Client, user: Any, dream_with_files: Dream
) -> None:
    client.force_login(user)

    html = client.get(reverse("dreams:detail", args=[dream_with_files.pk])).content.decode()

    assert reverse("dreams:delete", args=[dream_with_files.pk]) in html
    assert "Supprimer définitivement" in html
