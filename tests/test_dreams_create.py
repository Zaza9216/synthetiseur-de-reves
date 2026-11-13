"""Tests de la création d'un rêve : validation de l'audio, quota, envoi."""

from collections.abc import Callable
from typing import Any

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django.fixtures import Settings

from dreams.models import Dream, Status
from dreams.quotas import dreams_left_today
from dreams.validators import detect_audio_format, validate_audio_file

MakeDream = Callable[..., Dream]

# Premiers octets réels de chaque format (« signatures »).
WEBM = b"\x1a\x45\xdf\xa3" + b"\x00" * 60
OGG = b"OggS" + b"\x00" * 60
WAV = b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 50
FLAC = b"fLaC" + b"\x00" * 60
MP4 = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 50
MP3_ID3 = b"ID3\x04\x00" + b"\x00" * 60
MP3_FRAME = b"\xff\xfb\x90\x64" + b"\x00" * 60


def audio(content: bytes = WEBM, name: str = "reve.webm") -> SimpleUploadedFile:
    """Construit un fichier audio envoyé."""
    return SimpleUploadedFile(name, content, content_type="audio/webm")


# --- Détection du format ----------------------------------------------------------


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (WEBM, "webm"),
        (OGG, "ogg"),
        (WAV, "wav"),
        (FLAC, "flac"),
        (MP4, "mp4"),
        (MP3_ID3, "mp3"),
        (MP3_FRAME, "mp3"),
        (b"%PDF-1.7 pas du tout de l'audio", None),
        (b"MZ\x90\x00 executable windows", None),
        (b"", None),
    ],
)
def test_detect_audio_format(header: bytes, expected: str | None) -> None:
    assert detect_audio_format(header[:16]) == expected


# --- Validation du fichier --------------------------------------------------------


def test_valid_audio_passes_and_file_is_rewound() -> None:
    file = audio()

    validate_audio_file(file)

    assert file.tell() == 0


@pytest.mark.parametrize(
    ("file", "code"),
    [
        (audio(b"", "vide.webm"), "empty"),
        (audio(WEBM, "notes.txt"), "bad_extension"),
        (audio(WEBM, "sans_extension"), "bad_extension"),
        (audio(b"Ceci est un texte deguise en mp3", "faux.mp3"), "not_audio"),
    ],
)
def test_invalid_audio_is_rejected(file: SimpleUploadedFile, code: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        validate_audio_file(file)

    assert excinfo.value.code == code


def test_too_large_audio_is_rejected(settings: Settings) -> None:
    settings.DREAM_AUDIO_MAX_MB = 1

    with pytest.raises(ValidationError) as excinfo:
        validate_audio_file(audio(WEBM + b"\x00" * (1024 * 1024)))

    assert excinfo.value.code == "too_large"


# --- Quota journalier -------------------------------------------------------------


def test_quota_counts_only_todays_dreams(
    settings: Settings, user: Any, other_user: Any, make_dream: MakeDream
) -> None:
    settings.DREAM_DAILY_LIMIT = 3
    yesterday = make_dream(user)
    Dream.objects.filter(pk=yesterday.pk).update(
        created_at=timezone.now() - timezone.timedelta(days=1)
    )
    make_dream(user)
    make_dream(other_user)

    assert dreams_left_today(user) == 2


def test_quota_is_never_negative(settings: Settings, user: Any, make_dream: MakeDream) -> None:
    settings.DREAM_DAILY_LIMIT = 1
    make_dream(user)
    make_dream(user)

    assert dreams_left_today(user) == 0


# --- Page et envoi -----------------------------------------------------------------


@pytest.mark.django_db
def test_create_page_requires_login(client: Client) -> None:
    response = client.get(reverse("dreams:create"))

    assert response.status_code == 302


def test_create_page_shows_recorder_and_quota(client: Client, user: Any) -> None:
    client.force_login(user)

    html = client.get(reverse("dreams:create")).content.decode()

    assert 'id="recorder"' in html
    assert "js/recorder.js" in html
    assert "Rêves restants aujourd'hui : <strong>10</strong>" in html


def test_upload_via_script_returns_json_and_creates_pending_dream(
    client: Client, user: Any
) -> None:
    client.force_login(user)

    response = client.post(
        reverse("dreams:create"),
        {"audio": audio(), "audio_duration": "42.5"},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 201
    dream = Dream.objects.get()
    assert response.json() == {
        "id": dream.pk,
        "redirect_url": reverse("dreams:detail", args=[dream.pk]),
    }
    assert dream.user == user
    assert dream.status == Status.EN_ATTENTE
    assert dream.audio_duration == 42.5
    assert dream.audio.name.endswith(".webm")
    assert "reve" not in dream.audio.name


def test_upload_without_javascript_redirects_to_detail(client: Client, user: Any) -> None:
    client.force_login(user)

    response = client.post(reverse("dreams:create"), {"audio": audio(WAV, "reve.wav")})

    dream = Dream.objects.get()
    assert response.status_code == 302
    assert response.url == reverse("dreams:detail", args=[dream.pk])


def test_invalid_upload_via_script_returns_json_errors(client: Client, user: Any) -> None:
    client.force_login(user)

    response = client.post(
        reverse("dreams:create"),
        {"audio": audio(b"pas de l'audio", "faux.webm")},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "errors": ["Ce fichier ne semble pas être un enregistrement audio valide."]
    }
    assert not Dream.objects.exists()


def test_invalid_upload_without_javascript_shows_form_errors(client: Client, user: Any) -> None:
    client.force_login(user)

    response = client.post(reverse("dreams:create"), {"audio": audio(WEBM, "notes.txt")})

    assert response.status_code == 400
    assert "Format non pris en charge" in response.content.decode()


def test_missing_file_is_rejected(client: Client, user: Any) -> None:
    client.force_login(user)

    response = client.post(reverse("dreams:create"), {}, headers={"Accept": "application/json"})

    assert response.status_code == 400
    assert not Dream.objects.exists()


def test_too_long_recording_is_rejected(client: Client, user: Any, settings: Settings) -> None:
    settings.DREAM_AUDIO_MAX_SECONDS = 300
    client.force_login(user)

    response = client.post(
        reverse("dreams:create"),
        {"audio": audio(), "audio_duration": "301"},
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 400
    assert "trop long" in response.json()["errors"][0]


def test_quota_reached_blocks_upload_via_script(
    client: Client, user: Any, settings: Settings, make_dream: MakeDream
) -> None:
    settings.DREAM_DAILY_LIMIT = 1
    make_dream(user)
    client.force_login(user)

    response = client.post(
        reverse("dreams:create"), {"audio": audio()}, headers={"Accept": "application/json"}
    )

    assert response.status_code == 429
    assert Dream.objects.count() == 1


def test_quota_reached_without_javascript_redirects_with_message(
    client: Client, user: Any, settings: Settings, make_dream: MakeDream
) -> None:
    settings.DREAM_DAILY_LIMIT = 1
    make_dream(user)
    client.force_login(user)

    response = client.post(reverse("dreams:create"), {"audio": audio()}, follow=True)

    assert "limite de rêves pour aujourd" in response.content.decode()
    assert Dream.objects.count() == 1


def test_quota_reached_hides_recorder(
    client: Client, user: Any, settings: Settings, make_dream: MakeDream
) -> None:
    settings.DREAM_DAILY_LIMIT = 1
    make_dream(user)
    client.force_login(user)

    html = client.get(reverse("dreams:create")).content.decode()

    assert 'id="recorder"' not in html
    assert "js/recorder.js" not in html
