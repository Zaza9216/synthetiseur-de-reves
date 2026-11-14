"""Tests RGPD : export des données, suppression du compte, page de confidentialité."""

import io
import json
import zipfile
from collections.abc import Callable
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client
from django.urls import reverse

from dreams.models import Dream
from tests.conftest import STRONG_PASSWORD, fake_audio

MakeDream = Callable[..., Dream]


@pytest.fixture
def dream_with_files(user: Any, make_dream: MakeDream) -> Dream:
    """Rêve complet, avec audio et image."""
    dream = make_dream(user, audio=fake_audio(), image_prompt="prompt", audio_duration=30.0)
    dream.image.save("image.webp", ContentFile(b"webp-image"), save=True)
    return dream


def open_export(response: Any) -> zipfile.ZipFile:
    """Ouvre l'archive ZIP renvoyée par la vue d'export."""
    return zipfile.ZipFile(io.BytesIO(b"".join(response.streaming_content)))


# --- Page « Mes données » ------------------------------------------------------------------


def test_my_data_page_summarises_account(
    client: Client, user: Any, dream_with_files: Dream, make_dream: MakeDream
) -> None:
    make_dream(user)
    client.force_login(user)

    response = client.get(reverse("accounts:my_data"))
    html = response.content.decode()

    assert response.status_code == 200
    assert response.context["dream_count"] == 2
    assert response.context["audio_count"] == 1
    assert response.context["image_count"] == 1
    assert reverse("accounts:export") in html
    assert "Supprimer définitivement mon compte" in html


@pytest.mark.django_db
def test_my_data_requires_login(client: Client) -> None:
    assert client.get(reverse("accounts:my_data")).status_code == 302
    assert client.get(reverse("accounts:export")).status_code == 302


# --- Export --------------------------------------------------------------------------------


def test_export_contains_json_audio_images_and_readme(
    client: Client, user: Any, dream_with_files: Dream
) -> None:
    client.force_login(user)

    response = client.get(reverse("accounts:export"))
    archive = open_export(response)
    data = json.loads(archive.read("donnees.json"))
    record = data["reves"][0]

    assert response["Content-Type"] == "application/zip"
    assert "attachment" in response["Content-Disposition"]
    assert ".zip" in response["Content-Disposition"]
    assert set(archive.namelist()) == {
        "donnees.json",
        "LISEZMOI.txt",
        f"audio/reve-{dream_with_files.pk}.webm",
        f"images/reve-{dream_with_files.pk}.webp",
    }
    assert data["compte"]["identifiant"] == "bob"
    assert data["compte"]["email"] == "bob@example.com"
    assert data["nombre_de_reves"] == 1
    assert record["recit"] == dream_with_files.transcription
    assert record["emotion"] == "Heureux"
    assert record["fichier_audio"] == f"audio/reve-{dream_with_files.pk}.webm"
    assert archive.read(record["fichier_audio"]) == b"fake-audio-bytes"
    assert archive.read(record["fichier_image"]) == b"webp-image"


def test_export_never_contains_other_users_dreams(
    client: Client, user: Any, other_user: Any, make_dream: MakeDream
) -> None:
    make_dream(other_user, transcription="Rêve secret d'Ève")
    client.force_login(user)

    archive = open_export(client.get(reverse("accounts:export")))

    assert json.loads(archive.read("donnees.json"))["nombre_de_reves"] == 0
    assert "Rêve secret" not in archive.read("donnees.json").decode()


def test_export_skips_missing_files(client: Client, user: Any, dream_with_files: Dream) -> None:
    default_storage.delete(dream_with_files.audio.name)
    client.force_login(user)

    archive = open_export(client.get(reverse("accounts:export")))
    record = json.loads(archive.read("donnees.json"))["reves"][0]

    assert record["fichier_audio"] is None
    assert record["fichier_image"] is not None


# --- Suppression du compte -------------------------------------------------------------------


def test_account_deletion_removes_everything(
    client: Client, user: Any, dream_with_files: Dream
) -> None:
    audio, image = dream_with_files.audio.name, dream_with_files.image.name
    client.force_login(user)

    response = client.post(reverse("accounts:my_data"), {"password": STRONG_PASSWORD}, follow=True)

    assert response.redirect_chain[-1][0] == reverse("core:home")
    assert "toutes vos données ont été supprimés" in response.content.decode()
    assert not get_user_model().objects.filter(username="bob").exists()
    assert not Dream.objects.exists()
    assert not default_storage.exists(audio)
    assert not default_storage.exists(image)
    assert "_auth_user_id" not in client.session


def test_account_deletion_requires_correct_password(
    client: Client, user: Any, dream_with_files: Dream
) -> None:
    client.force_login(user)

    response = client.post(reverse("accounts:my_data"), {"password": "mauvais"})

    assert response.status_code == 200
    assert "Mot de passe incorrect." in response.content.decode()
    assert get_user_model().objects.filter(username="bob").exists()
    assert Dream.objects.exists()


def test_account_deletion_only_deletes_own_account(
    client: Client, user: Any, other_user: Any, make_dream: MakeDream
) -> None:
    make_dream(other_user)
    client.force_login(user)

    client.post(reverse("accounts:my_data"), {"password": STRONG_PASSWORD})

    assert get_user_model().objects.filter(username="eve").exists()
    assert Dream.objects.filter(user=other_user).count() == 1


# --- Confidentialité ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_privacy_page_is_public_and_complete(client: Client) -> None:
    html = client.get(reverse("core:privacy")).content.decode()

    for expected in ("OpenAI", "Render", "Francfort", "Vos droits", "CNIL", "Mes données"):
        assert expected in html


@pytest.mark.django_db
def test_privacy_is_linked_from_footer_and_signup(client: Client) -> None:
    link = reverse("core:privacy")

    assert link in client.get(reverse("core:home")).content.decode()
    assert link in client.get(reverse("accounts:signup")).content.decode()
