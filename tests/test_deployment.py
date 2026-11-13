"""Tests liés au déploiement : stockage en base, fichiers protégés, compte administrateur."""

from collections.abc import Callable
from io import StringIO
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from pytest_django.fixtures import Settings

from core.models import StoredFile
from core.storage import DatabaseStorage
from dreams.media import _parse_range
from dreams.models import Dream
from tests.conftest import fake_audio

MakeDream = Callable[..., Dream]
AUDIO = b"fake-audio-bytes"  # contenu de fake_audio()


@pytest.fixture
def database_storage(settings: Settings) -> None:
    """Utilise le stockage en base, comme en production."""
    settings.STORAGES = {
        **settings.STORAGES,
        "default": {"BACKEND": "core.storage.DatabaseStorage"},
    }


@pytest.fixture
def dream(user: Any, make_dream: MakeDream) -> Dream:
    """Rêve avec un audio et une image."""
    dream = make_dream(user, audio=fake_audio())
    dream.image.save("image.webp", ContentFile(b"webp-image"), save=True)
    return dream


# --- Stockage en base ------------------------------------------------------------------


@pytest.mark.django_db
def test_database_storage_full_lifecycle() -> None:
    storage = DatabaseStorage()

    name = storage.save("dreams/audio/test.webm", ContentFile(b"abc"))

    assert storage.exists(name)
    assert storage.size(name) == 3
    with storage.open(name) as file:
        assert file.read() == b"abc"
    assert storage.url(name) == f"/fichiers/{name}"
    storage.delete(name)
    assert not storage.exists(name)
    assert not StoredFile.objects.exists()


@pytest.mark.django_db
def test_database_storage_keeps_names_unique() -> None:
    storage = DatabaseStorage()

    first = storage.save("a/b.webp", ContentFile(b"1"))
    second = storage.save("a/b.webp", ContentFile(b"2"))

    assert first != second
    assert StoredFile.objects.count() == 2


@pytest.mark.django_db
def test_database_storage_missing_file() -> None:
    storage = DatabaseStorage()

    with pytest.raises(FileNotFoundError):
        storage.open("absent.webm")
    with pytest.raises(FileNotFoundError):
        storage.size("absent.webm")
    storage.delete("absent.webm")  # ne lève pas d'erreur
    assert str(StoredFile(name="x.webm")) == "x.webm"


def test_dream_files_are_stored_in_database(
    database_storage: None, user: Any, make_dream: MakeDream
) -> None:
    dream = make_dream(user, audio=fake_audio())
    dream.image.save("image.webp", ContentFile(b"webp"), save=True)

    assert StoredFile.objects.count() == 2
    dream.delete()  # le signal post_delete supprime aussi les fichiers en base
    assert not StoredFile.objects.exists()


# --- Accès protégé aux fichiers ----------------------------------------------------------


def test_owner_can_read_audio_and_image(client: Client, user: Any, dream: Dream) -> None:
    client.force_login(user)

    audio = client.get(dream.audio.url)
    image = client.get(dream.image.url)

    assert dream.audio.url.startswith("/fichiers/dreams/audio/")
    assert (audio.status_code, audio.content, audio["Content-Type"]) == (200, AUDIO, "audio/webm")
    assert audio["Accept-Ranges"] == "bytes"
    assert audio["Cache-Control"] == "private, max-age=3600"
    assert (image.status_code, image["Content-Type"]) == (200, "image/webp")


def test_other_user_gets_404(client: Client, other_user: Any, dream: Dream) -> None:
    client.force_login(other_user)

    assert client.get(dream.audio.url).status_code == 404
    assert client.get(dream.image.url).status_code == 404


def test_anonymous_is_redirected_to_login(client: Client, dream: Dream) -> None:
    response = client.get(dream.audio.url)

    assert response.status_code == 302
    assert "/comptes/connexion/" in response.url


def test_staff_can_read_any_file(client: Client, dream: Dream) -> None:
    admin = get_user_model().objects.create_user("admin", "a@example.com", "x", is_staff=True)
    client.force_login(admin)

    assert client.get(dream.audio.url).status_code == 200


def test_unknown_or_unreferenced_file_gives_404(client: Client, user: Any) -> None:
    default_storage.save("dreams/audio/orphelin.webm", ContentFile(b"x"))
    client.force_login(user)

    assert client.get("/fichiers/dreams/audio/orphelin.webm").status_code == 404
    assert client.get("/fichiers/../../.env").status_code == 404


def test_referenced_file_missing_from_storage_gives_404(
    client: Client, user: Any, dream: Dream
) -> None:
    default_storage.delete(dream.audio.name)
    client.force_login(user)

    assert client.get(dream.audio.url).status_code == 404


def test_range_request_returns_partial_content(client: Client, user: Any, dream: Dream) -> None:
    client.force_login(user)

    response = client.get(dream.audio.url, headers={"Range": "bytes=0-3"})

    assert response.status_code == 206
    assert response.content == AUDIO[:4]
    assert response["Content-Range"] == f"bytes 0-3/{len(AUDIO)}"


def test_unsatisfiable_range_returns_416(client: Client, user: Any, dream: Dream) -> None:
    client.force_login(user)

    response = client.get(dream.audio.url, headers={"Range": "bytes=999-"})

    assert response.status_code == 416
    assert response["Content-Range"] == f"bytes */{len(AUDIO)}"


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("bytes=0-9", (0, 9)),
        ("bytes=10-", (10, 99)),
        ("bytes=-20", (80, 99)),
        ("bytes=90-500", (90, 99)),
        ("bytes=-500", (0, 99)),
        ("bytes=50-10", None),
        ("bytes=100-", None),
        ("bytes=-", None),
        ("octets=0-5", None),
        ("bytes=0-5,10-15", None),
    ],
)
def test_parse_range(header: str, expected: tuple[int, int] | None) -> None:
    assert _parse_range(header, 100) == expected


def test_parse_range_on_empty_file() -> None:
    assert _parse_range("bytes=0-1", 0) is None


def test_files_are_served_from_database_storage(
    database_storage: None, client: Client, user: Any, make_dream: MakeDream
) -> None:
    dream = make_dream(user, audio=fake_audio())
    client.force_login(user)

    response = client.get(dream.audio.url)

    assert response.status_code == 200
    assert response.content == AUDIO


# --- Compte administrateur au démarrage ------------------------------------------------------


@pytest.mark.django_db
def test_ensure_admin_creates_superuser_once(settings: Settings) -> None:
    settings.ADMIN_USERNAME = "othmane"
    settings.ADMIN_EMAIL = "admin@example.com"
    settings.ADMIN_PASSWORD = "Un-Mot-De-Passe-Solide-2026"
    out = StringIO()

    call_command("ensure_admin", stdout=out)
    call_command("ensure_admin", stdout=out)

    admin = get_user_model().objects.get(username="othmane")
    assert admin.is_superuser and admin.is_staff
    assert admin.check_password("Un-Mot-De-Passe-Solide-2026")
    assert "créé" in out.getvalue()
    assert "existe déjà" in out.getvalue()


@pytest.mark.django_db
def test_ensure_admin_does_nothing_without_variables(settings: Settings) -> None:
    settings.ADMIN_USERNAME = ""
    settings.ADMIN_PASSWORD = ""
    out = StringIO()

    call_command("ensure_admin", stdout=out)

    assert not get_user_model().objects.exists()
    assert "rien à faire" in out.getvalue()


@pytest.mark.django_db
def test_ensure_admin_rejects_weak_password(settings: Settings) -> None:
    settings.ADMIN_USERNAME = "admin"
    settings.ADMIN_PASSWORD = "1234"

    with pytest.raises(CommandError, match="trop faible"):
        call_command("ensure_admin", stdout=StringIO())

    assert not get_user_model().objects.exists()
