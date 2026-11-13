"""Tests des services d'IA simulés (utilisés uniquement pour les tests de charge)."""

from collections.abc import Callable
from typing import Any

from pytest_django.fixtures import Settings

from dreams.ai.fake import FAKE_STORIES, FAKE_WEBP, fake_classify, fake_image, fake_transcribe
from dreams.models import ApiCall, Dream, Emotion, Status
from dreams.pipeline import process_dream
from tests.conftest import fake_audio

MakeDream = Callable[..., Dream]


def test_fake_services_record_calls_without_cost(
    settings: Settings, user: Any, make_dream: MakeDream
) -> None:
    settings.AI_FAKE_LATENCY_SCALE = 0
    dream = make_dream(user)

    assert fake_transcribe(dream) in FAKE_STORIES
    assert fake_classify(dream).emotion in Emotion.values
    image, prompt = fake_image(dream)

    assert image.read() == FAKE_WEBP
    assert prompt == "prompt simulé"
    calls = ApiCall.objects.all()
    assert calls.count() == 3
    assert {c.provider for c in calls} == {"fake"}
    assert sum(c.cost_usd for c in calls) == 0


def test_pipeline_uses_fake_backend(settings: Settings, user: Any, make_dream: MakeDream) -> None:
    settings.AI_BACKEND = "fake"
    settings.AI_FAKE_LATENCY_SCALE = 0
    dream = make_dream(
        user, audio=fake_audio(), transcription="", emotion="", status=Status.EN_ATTENTE
    )

    process_dream(dream.pk)

    dream.refresh_from_db()
    assert dream.status == Status.TERMINE
    assert dream.transcription in FAKE_STORIES
    assert dream.emotion
    assert dream.image
