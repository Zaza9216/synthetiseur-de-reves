"""Tests de la génération d'image et du plafond budgétaire mensuel."""

import base64
import logging
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import httpx2
import openai
import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from pytest_django.fixtures import Settings

from dreams.ai.budget import (
    BUDGET_EXCEEDED_MESSAGE,
    ensure_budget_available,
    is_budget_exceeded,
    monthly_spend,
)
from dreams.ai.errors import AIServiceError
from dreams.ai.image import (
    EMOTION_MOODS,
    MAX_STORY_CHARS,
    MODERATION_MESSAGE,
    build_image_prompt,
    generate_dream_image,
)
from dreams.ai.pricing import image_cost
from dreams.models import ApiCall, ApiService, Dream, Emotion, Status
from dreams.pipeline import process_dream, retry_dream
from tests.conftest import fake_audio
from tests.test_dreams_create import audio

MakeDream = Callable[..., Dream]
REQUEST = httpx2.Request("POST", "https://api.openai.com/v1/images/generations")
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 fake"


def image_response(data: bytes = WEBP_BYTES) -> Any:
    """Réponse simulée de l'API d'images."""
    return SimpleNamespace(data=[SimpleNamespace(b64_json=base64.b64encode(data).decode())])


def spend(amount: str, days_ago: int = 0) -> ApiCall:
    """Enregistre un appel ayant coûté ``amount`` dollars."""
    call = ApiCall.objects.create(
        service=ApiService.IMAGE,
        model_name="m",
        success=True,
        duration_ms=1,
        cost_usd=Decimal(amount),
    )
    if days_ago:
        ApiCall.objects.filter(pk=call.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
    return call


@pytest.fixture
def fake_client(settings: Settings) -> Any:
    """Remplace le client OpenAI du module d'image."""
    settings.IMAGE_MODEL = "gpt-image-1-mini"
    settings.IMAGE_QUALITY = "medium"
    client = MagicMock()
    with patch("dreams.ai.image.get_openai_client", return_value=client):
        yield client


@pytest.fixture
def dream(user: Any, make_dream: MakeDream) -> Dream:
    """Rêve transcrit et analysé, sans image."""
    return make_dream(
        user, transcription="Je volais au-dessus d'une ville de verre.", emotion="heureux"
    )


# --- Prompt -----------------------------------------------------------------------------


def test_prompt_contains_story_mood_and_no_text_rule(dream: Dream) -> None:
    prompt = build_image_prompt(dream)

    assert "ville de verre" in prompt
    assert EMOTION_MOODS[Emotion.HEUREUX] in prompt
    assert "Aucun texte" in prompt


def test_prompt_without_emotion_uses_neutral_mood(dream: Dream) -> None:
    dream.emotion = ""

    assert EMOTION_MOODS[Emotion.NEUTRE] in build_image_prompt(dream)


def test_every_emotion_has_a_mood() -> None:
    assert set(EMOTION_MOODS) == set(Emotion.values)


def test_prompt_story_is_truncated(dream: Dream) -> None:
    dream.transcription = "§" * (MAX_STORY_CHARS * 2)

    assert build_image_prompt(dream).count("§") == MAX_STORY_CHARS


# --- Coût ------------------------------------------------------------------------------


def test_image_cost() -> None:
    assert image_cost("gpt-image-1-mini", "medium") == Decimal("0.011")
    assert image_cost("gpt-image-1-mini", "inconnue") == Decimal("0.167")
    assert image_cost("modele-inconnu", "low") == Decimal("0.167")


# --- Génération ----------------------------------------------------------------------------


def test_generate_image_returns_webp_and_records_cost(fake_client: Any, dream: Dream) -> None:
    fake_client.images.generate.return_value = image_response()

    image, prompt = generate_dream_image(dream)

    assert image.read() == WEBP_BYTES
    assert image.name == "reve.webp"
    assert "ville de verre" in prompt
    kwargs = fake_client.images.generate.call_args.kwargs
    assert (kwargs["model"], kwargs["quality"], kwargs["output_format"]) == (
        "gpt-image-1-mini",
        "medium",
        "webp",
    )
    call = ApiCall.objects.get()
    assert call.success and call.cost_usd == Decimal("0.011")


def test_moderation_refusal_gives_specific_message(fake_client: Any, dream: Dream) -> None:
    fake_client.images.generate.side_effect = openai.BadRequestError(
        "refusé",
        response=httpx2.Response(400, request=REQUEST),
        body={"code": "moderation_blocked"},
    )

    with pytest.raises(AIServiceError) as excinfo:
        generate_dream_image(dream)

    assert excinfo.value.user_message == MODERATION_MESSAGE
    assert excinfo.value.retryable is False


@pytest.mark.parametrize(
    "error",
    [
        openai.APITimeoutError(request=REQUEST),
        openai.BadRequestError(
            "x", response=httpx2.Response(400, request=REQUEST), body={"code": "autre"}
        ),
    ],
)
def test_other_api_errors_are_translated(fake_client: Any, dream: Dream, error: Exception) -> None:
    fake_client.images.generate.side_effect = error

    with pytest.raises(AIServiceError):
        generate_dream_image(dream)

    assert ApiCall.objects.get().success is False


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(data=[]),
        SimpleNamespace(data=[SimpleNamespace(b64_json="%%% pas du base64 %%%")]),
        image_response(b""),
    ],
)
def test_unusable_image_response_raises(fake_client: Any, dream: Dream, response: Any) -> None:
    fake_client.images.generate.return_value = response

    with pytest.raises(AIServiceError):
        generate_dream_image(dream)


def test_no_image_is_generated_when_budget_is_exceeded(
    fake_client: Any, dream: Dream, settings: Settings
) -> None:
    settings.AI_MONTHLY_BUDGET_USD = 1.0
    spend("1.00")

    with pytest.raises(AIServiceError) as excinfo:
        generate_dream_image(dream)

    assert excinfo.value.user_message == BUDGET_EXCEEDED_MESSAGE
    fake_client.images.generate.assert_not_called()


# --- Budget -------------------------------------------------------------------------------


@pytest.mark.django_db
def test_monthly_spend_only_counts_current_month() -> None:
    spend("0.50")
    spend("0.25")
    spend("9.00", days_ago=40)

    assert monthly_spend() == Decimal("0.75")


@pytest.mark.django_db
def test_monthly_spend_is_zero_without_calls() -> None:
    assert monthly_spend() == Decimal("0")


@pytest.mark.django_db
def test_budget_states_and_alerts(settings: Settings, caplog: pytest.LogCaptureFixture) -> None:
    settings.AI_MONTHLY_BUDGET_USD = 10.0
    caplog.set_level(logging.WARNING)

    spend("5.00")
    assert not is_budget_exceeded()
    assert "80 %" not in caplog.text

    spend("3.50")
    assert not is_budget_exceeded()
    assert "80 %" in caplog.text

    spend("1.50")
    assert is_budget_exceeded()
    with pytest.raises(AIServiceError):
        ensure_budget_available()


def test_create_is_refused_when_budget_is_exceeded(
    client: Client, user: Any, settings: Settings
) -> None:
    settings.AI_MONTHLY_BUDGET_USD = 1.0
    spend("2.00")
    client.force_login(user)

    json_response = client.post(
        reverse("dreams:create"), {"audio": audio()}, headers={"Accept": "application/json"}
    )
    page = client.post(reverse("dreams:create"), {"audio": audio()}, follow=True)

    assert json_response.status_code == 503
    assert json_response.json()["errors"] == [BUDGET_EXCEEDED_MESSAGE]
    assert escape(BUDGET_EXCEEDED_MESSAGE) in page.content.decode()
    assert not Dream.objects.exists()


# --- Pipeline -------------------------------------------------------------------------------


@pytest.fixture
def pending(user: Any, make_dream: MakeDream) -> Dream:
    """Rêve transcrit et analysé, en attente de son image."""
    return make_dream(user, audio=fake_audio(), emotion="heureux", status=Status.EN_ATTENTE)


def test_pipeline_saves_generated_image(fake_client: Any, pending: Dream) -> None:
    fake_client.images.generate.return_value = image_response()

    process_dream(pending.pk)

    pending.refresh_from_db()
    assert pending.status == Status.TERMINE
    assert pending.image.name.endswith(".webp")
    assert default_storage.open(pending.image.name).read() == WEBP_BYTES
    assert "ville de verre" in pending.image_prompt
    assert pending.error_message == ""
    assert not pending.can_retry


def test_image_failure_still_completes_dream_with_warning(fake_client: Any, pending: Dream) -> None:
    fake_client.images.generate.side_effect = openai.APITimeoutError(request=REQUEST)

    process_dream(pending.pk)

    pending.refresh_from_db()
    assert pending.status == Status.TERMINE
    assert not pending.image
    assert "trop de temps" in pending.error_message
    assert pending.is_missing_image
    assert pending.can_retry


def test_retry_regenerates_only_the_missing_image(fake_client: Any, pending: Dream) -> None:
    fake_client.images.generate.side_effect = openai.APITimeoutError(request=REQUEST)
    process_dream(pending.pk)
    pending.refresh_from_db()
    fake_client.images.generate.side_effect = None
    fake_client.images.generate.return_value = image_response()

    with patch("dreams.pipeline.enqueue_dream", side_effect=process_dream):
        assert retry_dream(pending) is True

    pending.refresh_from_db()
    assert pending.status == Status.TERMINE
    assert pending.image
    assert pending.error_message == ""


def test_image_of_dream_deleted_during_generation_is_cleaned_up(
    fake_client: Any, pending: Dream
) -> None:
    saved_names: list[str] = []

    def generate_then_delete(dream: Dream) -> tuple[ContentFile, str]:
        Dream.objects.filter(pk=dream.pk).delete()
        return ContentFile(WEBP_BYTES, name="reve.webp"), "prompt"

    original_save = Dream.image.field.attr_class.save

    def tracking_save(self: Any, name: str, content: Any, save: bool = True) -> None:
        original_save(self, name, content, save)
        saved_names.append(self.name)

    with (
        patch("dreams.pipeline.generate_dream_image", side_effect=generate_then_delete),
        patch.object(Dream.image.field.attr_class, "save", tracking_save),
    ):
        process_dream(pending.pk)

    assert not Dream.objects.filter(pk=pending.pk).exists()
    assert saved_names and not default_storage.exists(saved_names[0])


def test_detail_offers_image_regeneration(client: Client, user: Any, make_dream: MakeDream) -> None:
    dream = make_dream(user, error_message="Le service d'IA est très sollicité.")
    client.force_login(user)

    html = client.get(reverse("dreams:detail", args=[dream.pk])).content.decode()

    assert "Régénérer l'image" in html
    assert escape("Le service d'IA est très sollicité.") in html
