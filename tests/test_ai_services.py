"""Tests des services d'IA : client, erreurs, coût, journal des appels, transcription.

Aucune requête réseau n'est faite : le client OpenAI est remplacé par un double.
"""

from collections.abc import Callable
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import httpx2
import openai
import pytest
from pytest_django.fixtures import Settings

from dreams.ai.client import get_openai_client
from dreams.ai.errors import AIServiceError, translate_openai_error
from dreams.ai.pricing import transcription_cost
from dreams.ai.tracking import track_api_call
from dreams.ai.transcription import transcribe_dream
from dreams.models import ApiCall, ApiService, Dream
from tests.conftest import fake_audio

MakeDream = Callable[..., Dream]
REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/test")


def status_error(cls: type[openai.APIStatusError], code: int, body: Any = None) -> Exception:
    """Construit une erreur HTTP du SDK OpenAI."""
    return cls("erreur simulée", response=httpx2.Response(code, request=REQUEST), body=body)


@pytest.fixture
def fake_client() -> Any:
    """Remplace le client OpenAI par un double contrôlable."""
    client = MagicMock()
    with patch("dreams.ai.transcription.get_openai_client", return_value=client):
        yield client


# --- Client ------------------------------------------------------------------------


def test_client_without_api_key_raises(settings: Settings) -> None:
    settings.OPENAI_API_KEY = ""

    with pytest.raises(AIServiceError) as excinfo:
        get_openai_client()

    assert excinfo.value.retryable is False


def test_client_is_configured_and_reused(settings: Settings) -> None:
    settings.OPENAI_TIMEOUT = 12.0
    settings.OPENAI_MAX_RETRIES = 3

    client = get_openai_client()

    assert client.timeout == 12.0
    assert client.max_retries == 3
    assert get_openai_client() is client


# --- Traduction des erreurs -----------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "fragment", "retryable"),
    [
        (openai.APITimeoutError(request=REQUEST), "trop de temps", True),
        (openai.APIConnectionError(request=REQUEST), "injoignable", True),
        (status_error(openai.RateLimitError, 429), "très sollicité", True),
        (
            status_error(openai.RateLimitError, 429, {"code": "insufficient_quota"}),
            "limite d'utilisation",
            False,
        ),
        (status_error(openai.AuthenticationError, 401), "mal configuré", False),
        (status_error(openai.PermissionDeniedError, 403), "mal configuré", False),
        (status_error(openai.BadRequestError, 400), "pas pu traiter", False),
        (status_error(openai.InternalServerError, 500), "incident", True),
        (RuntimeError("autre"), "inattendue", True),
    ],
)
def test_translate_openai_error(error: Exception, fragment: str, retryable: bool) -> None:
    translated = translate_openai_error(error)

    assert fragment in translated.user_message
    assert translated.retryable is retryable
    assert str(translated) == translated.user_message


# --- Coût ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("model", "seconds", "expected"),
    [
        ("gpt-4o-mini-transcribe", 60.0, Decimal("0.003000")),
        ("gpt-4o-mini-transcribe", 30.0, Decimal("0.001500")),
        ("gpt-4o-mini-transcribe", None, Decimal("0.003000")),
        ("whisper-1", 120.0, Decimal("0.012000")),
        ("modele-inconnu", 60.0, Decimal("0.006000")),
    ],
)
def test_transcription_cost(model: str, seconds: float | None, expected: Decimal) -> None:
    assert transcription_cost(model, seconds) == expected


# --- Journal des appels ---------------------------------------------------------------


def test_successful_call_is_recorded(user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user)

    with track_api_call(ApiService.TRANSCRIPTION, "modele-x", dream) as call:
        call.cost_usd = Decimal("0.0042")

    record = ApiCall.objects.get()
    assert record.success is True
    assert record.dream == dream
    assert record.cost_usd == Decimal("0.004200")
    assert record.duration_ms >= 0
    assert "OK" in str(record)


@pytest.mark.django_db
def test_failed_call_is_recorded_and_error_reraised() -> None:
    with pytest.raises(ValueError), track_api_call(ApiService.IMAGE, "modele-y"):
        raise ValueError("boum")

    record = ApiCall.objects.get()
    assert record.success is False
    assert record.error_type == "ValueError"
    assert record.cost_usd == 0
    assert "échec (ValueError)" in str(record)


def test_api_calls_are_kept_when_dream_is_deleted(user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user)
    with track_api_call(ApiService.TRANSCRIPTION, "modele-x", dream):
        pass

    dream.delete()

    assert ApiCall.objects.get().dream is None


# --- Transcription -------------------------------------------------------------------


def test_transcription_returns_clean_text_and_records_cost(
    fake_client: Any, user: Any, make_dream: MakeDream, settings: Settings
) -> None:
    settings.TRANSCRIPTION_MODEL = "gpt-4o-mini-transcribe"
    dream = make_dream(user, audio=fake_audio(), audio_duration=90.0, transcription="")
    fake_client.audio.transcriptions.create.return_value = SimpleNamespace(
        text="  Je marchais sur la lune.  "
    )

    text = transcribe_dream(dream)

    assert text == "Je marchais sur la lune."
    kwargs = fake_client.audio.transcriptions.create.call_args.kwargs
    assert kwargs["model"] == "gpt-4o-mini-transcribe"
    assert kwargs["language"] == "fr"
    filename, content = kwargs["file"]
    assert filename.endswith(".webm")
    assert content == b"fake-audio-bytes"
    call = ApiCall.objects.get()
    assert call.success is True
    assert call.cost_usd == Decimal("0.004500")


def test_transcription_without_audio_fails(
    fake_client: Any, user: Any, make_dream: MakeDream
) -> None:
    dream = make_dream(user, transcription="")

    with pytest.raises(AIServiceError) as excinfo:
        transcribe_dream(dream)

    assert excinfo.value.retryable is False
    fake_client.audio.transcriptions.create.assert_not_called()


def test_transcription_of_silence_fails(fake_client: Any, user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user, audio=fake_audio(), transcription="")
    fake_client.audio.transcriptions.create.return_value = SimpleNamespace(text="   ")

    with pytest.raises(AIServiceError) as excinfo:
        transcribe_dream(dream)

    assert "Aucune parole" in excinfo.value.user_message


def test_transcription_api_error_is_translated_and_recorded(
    fake_client: Any, user: Any, make_dream: MakeDream
) -> None:
    dream = make_dream(user, audio=fake_audio(), transcription="")
    fake_client.audio.transcriptions.create.side_effect = openai.APITimeoutError(request=REQUEST)

    with pytest.raises(AIServiceError) as excinfo:
        transcribe_dream(dream)

    assert "trop de temps" in excinfo.value.user_message
    call = ApiCall.objects.get()
    assert call.success is False
    assert call.error_type == "APITimeoutError"
